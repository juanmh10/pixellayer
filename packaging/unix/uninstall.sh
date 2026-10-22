#!/usr/bin/env bash
set -euo pipefail

dry_run=0
if [ "${1:-}" = '--dry-run' ]; then
  dry_run=1
  shift
fi
if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  echo 'Usage: bash uninstall.sh [--dry-run] DESTINATION' >&2
  exit 2
fi

raw_destination=$1
case "$raw_destination" in *$'\n'*|*$'\r'*) echo 'Newlines are not supported in the destination path.' >&2; exit 2;; esac
fail() { echo "PixelLayer uninstall: $*" >&2; exit 1; }

# Normalize an explicit path component by component, refusing symlinks before
# traversing them. The destination's parent must already exist.
physical_path_without_links() {
  local input=$1 absolute current component parent
  case "$input" in
    /*) absolute=$input;;
    *) absolute="$(pwd -P)/$input";;
  esac
  current='/'
  local -a components
  IFS='/' read -r -a components <<< "$absolute"
  for component in "${components[@]}"; do
    case "$component" in
      ''|.) continue;;
      ..) current=${current%/*}; [ -n "$current" ] || current='/';;
      *)
        if [ "$current" = '/' ]; then parent="/$component"; else parent="$current/$component"; fi
        [ ! -L "$parent" ] || fail "refusing symlink in path: $parent"
        current=$parent
        ;;
    esac
  done
  [ "$current" != '/' ] || fail 'refusing a filesystem root as the destination'
  printf '%s\n' "$current"
}

script_path=${BASH_SOURCE[0]}
case "$script_path" in /*) ;; *) script_path="$(pwd -P)/$script_path";; esac
[ ! -L "$script_path" ] || fail 'run uninstall.sh from a regular package file, not a symlink'
package_root=$(physical_path_without_links "${script_path%/*}")
destination=$(physical_path_without_links "$raw_destination")

manifest_path="$package_root/manifest.json"
sums_path="$package_root/SHA256SUMS"
[ -f "$manifest_path" ] && [ ! -L "$manifest_path" ] || fail 'source package has no regular manifest.json'
[ -f "$sums_path" ] && [ ! -L "$sums_path" ] || fail 'source package has no regular SHA256SUMS'

hash_file() {
  local output
  if command -v sha256sum >/dev/null 2>&1; then
    output=$(sha256sum -- "$1")
  elif command -v shasum >/dev/null 2>&1; then
    output=$(shasum -a 256 "$1")
  else
    fail 'sha256sum or shasum is required for package integrity checks'
  fi
  printf '%s\n' "${output%% *}"
}

temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/pixellayer-uninstall.XXXXXXXX") || fail 'could not create a private preflight directory'
trap 'rm -rf -- "$temporary_root"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# The package builder emits this stable, intentionally narrow JSON layout. This
# AWK parser needs no Python, Node or jq and rejects unsafe paths/duplicate rows.
manifest_rows="$temporary_root/manifest.tsv"
if ! LC_ALL=C awk '
function bad(message) { print "PixelLayer uninstall: malformed manifest: " message > "/dev/stderr"; exit 1 }
BEGIN { state="header"; have_name=0; have_version=0; have_target=0; count=0 }
NR == 1 { if ($0 != "{") bad("opening object expected"); next }
state == "header" {
  if ($0 ~ /^  "name": ".*",$/) { value=$0; sub(/^  "name": "/, "", value); sub(/",$/, "", value); if (have_name++ || value != "pixellayer") bad("invalid name"); next }
  if ($0 ~ /^  "version": ".*",$/) { value=$0; sub(/^  "version": "/, "", value); sub(/",$/, "", value); if (have_version++ || value !~ /^[0-9]+\.[0-9]+\.[0-9]+([+-][A-Za-z0-9.-]+)?$/) bad("invalid version"); next }
  if ($0 ~ /^  "target": ".*",$/) { value=$0; sub(/^  "target": "/, "", value); sub(/",$/, "", value); if (have_target++ || (value != "x86_64-unknown-linux-gnu" && value != "aarch64-unknown-linux-gnu" && value != "x86_64-apple-darwin" && value != "aarch64-apple-darwin")) bad("unsupported target"); next }
  if ($0 == "  \"files\": [") { if (have_name != 1 || have_version != 1 || have_target != 1) bad("identity fields missing"); state="array"; next }
  next
}
state == "array" {
  if ($0 == "  ]") { state="end"; next }
  if ($0 != "    {") bad("file object expected")
  state="path"; path=""; size=""; digest=""; next
}
state == "path" {
  if ($0 !~ /^      "path": "[A-Za-z0-9._/-]+",$/) bad("unsafe file path")
  path=$0; sub(/^      "path": "/, "", path); sub(/",$/, "", path)
  if (path ~ /^\// || path ~ /^-/ || path ~ /\/$/ || index(path, "//") || path ~ /(^|\/)\.\.?($|\/)/ || path == "manifest.json" || path == "SHA256SUMS") bad("unsafe or reserved file path")
  if (seen[path]++) bad("duplicate file path")
  state="size"; next
}
state == "size" {
  if ($0 !~ /^      "size_bytes": [0-9]+,$/) bad("invalid file size")
  size=$0; sub(/^      "size_bytes": /, "", size); sub(/,$/, "", size)
  state="sha"; next
}
state == "sha" {
  digest=$0; sub(/^      "sha256": "/, "", digest); sub(/"$/, "", digest)
  if (digest == $0 || length(digest) != 64 || digest !~ /^[0-9a-f]+$/) bad("invalid file digest")
  if ($0 != "      \"sha256\": \"" digest "\"") bad("invalid file digest field")
  printf "%s\t%s\t%s\n", path, size, digest
  count++; state="close"; next
}
state == "close" {
  if ($0 != "    }," && $0 != "    }") bad("file object terminator expected")
  state="array"; next
}
state == "end" {
  if ($0 != "}") bad("manifest terminator expected")
  state="done"; next
}
state == "done" { bad("unexpected trailing data") }
END {
  if (state != "done" || count < 1) bad("incomplete or empty file list")
}
' "$manifest_path" > "$manifest_rows"; then
  fail 'cannot parse the package manifest'
fi

manifest_map="$temporary_root/manifest-map"
expected_map="$temporary_root/expected-map"
sums_map="$temporary_root/sums-map"
expected_paths="$temporary_root/expected-paths"
expected_directories="$temporary_root/expected-directories"
tab=$(printf '\t')
awk -F '\t' '{ print $1 "\t" $3 }' "$manifest_rows" > "$manifest_map"
manifest_hash=$(hash_file "$manifest_path")
source_sums_hash=$(hash_file "$sums_path")
printf 'manifest.json\t%s\n' "$manifest_hash" >> "$manifest_map"
sort -t "$tab" -k 1,1 "$manifest_map" > "$expected_map"
awk -F '\t' '{ print $1 }' "$manifest_rows" > "$expected_paths"
printf 'manifest.json\nSHA256SUMS\n' >> "$expected_paths"
sort -u "$expected_paths" -o "$expected_paths"
awk -F '\t' '
{
  n=split($1, part, "/")
  path=""
  for (i=1; i<n; i++) {
    path=(path == "" ? part[i] : path "/" part[i])
    print path
  }
}' "$manifest_rows" | sort -u > "$expected_directories"

for required in pixellayer verify.sh uninstall.sh README.md; do
  grep -F -x -q "$required" "$expected_paths" || fail "required package file missing from manifest: $required"
done

while IFS= read -r line || [ -n "$line" ]; do
  [ "${#line}" -ge 67 ] || fail 'SHA256SUMS has a malformed row'
  digest=${line:0:64}
  [ "${line:64:2}" = '  ' ] || fail 'SHA256SUMS has a malformed row'
  relative=${line:66}
  [[ "$digest" =~ ^[0-9a-f]+$ && ${#digest} -eq 64 ]] || fail 'SHA256SUMS has a malformed digest'
  [[ "$relative" =~ ^[A-Za-z0-9._/-]+$ ]] || fail 'SHA256SUMS has an unsafe path'
  [[ "$relative" != /* && "$relative" != */ && "$relative" != *//* && ! "$relative" =~ (^|/)\.\.?(/|$) ]] || fail "unsafe SHA256SUMS path: $relative"
  printf '%s\t%s\n' "$relative" "$digest" >> "$sums_map"
done < "$sums_path"
[ -f "$sums_map" ] || : > "$sums_map"
sort -t "$tab" -k 1,1 "$sums_map" -o "$sums_map"
cmp "$expected_map" "$sums_map" >/dev/null || fail 'SHA256SUMS inventory or hashes do not match manifest.json'

verify_files() {
  local root=$1 relative size digest actual actual_size
  while IFS=$'\t' read -r relative size digest; do
    [ -f "$root/$relative" ] && [ ! -L "$root/$relative" ] || fail "missing or non-regular package file: $relative"
    actual=$(hash_file "$root/$relative")
    [ "$actual" = "$digest" ] || fail "package checksum mismatch: $relative"
    actual_size=$(wc -c < "$root/$relative" | tr -d '[:space:]')
    [ "$actual_size" = "$size" ] || fail "package size mismatch: $relative"
  done < "$manifest_rows"
  actual=$(hash_file "$root/manifest.json")
  [ "$actual" = "$manifest_hash" ] || fail 'manifest checksum mismatch'
  actual=$(hash_file "$root/SHA256SUMS")
  [ "$actual" = "$source_sums_hash" ] || fail 'SHA256SUMS checksum mismatch'
}

assert_no_link_parents() {
  local relative=$1 parent component current="$destination"
  parent=${relative%/*}
  [ "$parent" != "$relative" ] || return 0
  local old_ifs=$IFS
  IFS=/
  for component in $parent; do
    current="$current/$component"
    [ -d "$current" ] && [ ! -L "$current" ] || fail "package directory changed during removal: $current"
  done
  IFS=$old_ifs
}
verify_files "$package_root"

if [ ! -e "$destination" ]; then
  echo "PixelLayer installation is already absent: $destination"
  exit 0
fi
[ -d "$destination" ] && [ ! -L "$destination" ] || fail 'destination is not a regular installation directory'
[ -f "$destination/manifest.json" ] && [ ! -L "$destination/manifest.json" ] || fail 'destination has no regular PixelLayer manifest'
[ -f "$destination/SHA256SUMS" ] && [ ! -L "$destination/SHA256SUMS" ] || fail 'destination has no regular package checksum inventory'
cmp "$manifest_path" "$destination/manifest.json" >/dev/null || fail 'destination is a different build; nothing was removed'
cmp "$sums_path" "$destination/SHA256SUMS" >/dev/null || fail 'destination checksum inventory differs from this package; nothing was removed'

# Match every file and directory exactly. Extra data causes a full refusal.
find "$destination" -print0 > "$temporary_root/actual-paths" || fail 'cannot enumerate destination contents'
while IFS= read -r -d '' path; do
  [ "$path" != "$destination" ] || continue
  [ ! -L "$path" ] || fail "refusing destination symlink: $path"
  relative=${path#"$destination"/}
  case "$relative" in *$'\n'*|*$'\r'*) fail 'refusing a filename with a newline';; esac
  if [ -d "$path" ]; then
    grep -F -x -q "$relative" "$expected_directories" || fail "refusing unlisted directory: $relative"
  elif [ -f "$path" ]; then
    grep -F -x -q "$relative" "$expected_paths" || fail "refusing unlisted file: $relative"
  else
    fail "refusing non-regular package entry: $relative"
  fi
done < "$temporary_root/actual-paths"
while IFS= read -r relative; do
  [ -f "$destination/$relative" ] && [ ! -L "$destination/$relative" ] || fail "missing or non-regular package file: $relative"
done < "$expected_paths"
while IFS= read -r relative; do
  [ -d "$destination/$relative" ] && [ ! -L "$destination/$relative" ] || fail "missing or non-regular package directory: $relative"
done < "$expected_directories"
verify_files "$destination"

assert_no_active_server() {
  local exe="$destination/pixellayer" pid running_path module_path found identified listing proc_exe proc_dir process_name
  if [ "$(uname -s)" = Linux ] && [ -d /proc ]; then
    for proc_dir in /proc/[0-9]*; do
      [ -d "$proc_dir" ] || continue
      process_name=$(cat "$proc_dir/comm" 2>/dev/null || true)
      [ "$process_name" = pixellayer ] || continue
      proc_exe="$proc_dir/exe"
      running_path=$(readlink "$proc_exe" 2>/dev/null || true)
      [ -n "$running_path" ] || fail "cannot identify active PixelLayer process at $proc_dir; stop it and retry."
      running_path=${running_path% (deleted)}
      [ "$running_path" != "$exe" ] || fail 'PixelLayer is running from this installation. Disconnect the MCP client, stop the server, and retry.'
    done
    return
  fi
  command -v pgrep >/dev/null 2>&1 || fail 'cannot check for an active PixelLayer process on this host'
  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    command -v lsof >/dev/null 2>&1 || fail "PixelLayer process $pid is active and its installation cannot be confirmed; stop PixelLayer and retry."
    listing=$(lsof -a -p "$pid" -d txt -Fn 2>/dev/null | sed -n 's/^n//p' || true)
    [ -n "$listing" ] || fail "cannot identify the executable path for PixelLayer process $pid; stop it and retry."
    found=0
    identified=0
    while IFS= read -r module_path; do
      if [ "$module_path" = "$exe" ]; then found=1; fi
      [ "${module_path##*/}" = pixellayer ] && identified=1
    done <<EOF_PATHS
$listing
EOF_PATHS
    [ "$identified" -eq 1 ] || fail "cannot confirm the executable path for PixelLayer process $pid; stop it and retry."
    [ "$found" -eq 0 ] || fail "PixelLayer is running from this installation (PID $pid). Disconnect the MCP client, stop the server, and retry."
  done < <(pgrep -x pixellayer || true)
}
assert_no_active_server

if [ "$dry_run" -eq 1 ]; then
  echo "Would remove verified PixelLayer installation: $destination"
  echo 'Model cache, MCP configuration and separately installed skill would remain unchanged.'
  exit 0
fi

# Delete only files named in the verified manifest. Never recurse over unknown
# data; rmdir below refuses a folder if anything appeared after preflight.
assert_no_active_server
while IFS=$'\t' read -r relative size digest; do
  file="$destination/$relative"
  [ -f "$file" ] && [ ! -L "$file" ] || fail "package entry changed during removal; preserved: $file"
  assert_no_link_parents "$relative"
  actual=$(hash_file "$file")
  [ "$actual" = "$digest" ] || fail "package entry changed during removal; preserved: $file"
  assert_no_link_parents "$relative"
  [ ! -L "$file" ] || fail "package entry became a symlink during removal; preserved: $file"
  rm "$file" || fail "could not remove verified package file: $file"
done < "$manifest_rows"
for relative in manifest.json SHA256SUMS; do
  file="$destination/$relative"
  [ -f "$file" ] && [ ! -L "$file" ] || fail "package entry changed during removal; preserved: $file"
  if [ "$relative" = manifest.json ]; then expected_hash=$manifest_hash; else expected_hash=$source_sums_hash; fi
  actual=$(hash_file "$file")
  [ "$actual" = "$expected_hash" ] || fail "package entry changed during removal; preserved: $file"
  rm "$file" || fail "could not remove verified package file: $file"
done
directory_rows="$temporary_root/directories"
awk -F/ '{ print NF "\t" $0 }' "$expected_directories" | sort -rn | cut -f2- > "$directory_rows"
while IFS= read -r relative; do
  [ -n "$relative" ] || continue
  directory="$destination/$relative"
  [ -d "$directory" ] && [ ! -L "$directory" ] || fail "package directory changed during removal; preserved: $directory"
  rmdir "$directory" || fail "directory contains new or unlisted data; preserved: $directory"
done < "$directory_rows"
rmdir "$destination" || fail "installation directory contains new or unlisted data; preserved: $destination"
[ ! -e "$destination" ] && [ ! -L "$destination" ] || fail "removal did not complete; files remain at: $destination"
echo "Removed verified PixelLayer installation: $destination"
echo 'Model cache, MCP configuration and separately installed skill were left unchanged.'
