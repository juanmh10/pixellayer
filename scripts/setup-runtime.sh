#!/usr/bin/env bash
# Download the pinned native CPU runtime. Does not download models or change PATH.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
case "$(uname -s):$(uname -m)" in
  Linux:x86_64) platform=linux-x64 ;;
  Linux:aarch64|Linux:arm64) platform=linux-aarch64 ;;
  Darwin:x86_64) platform=osx-x86_64 ;;
  Darwin:arm64) platform=osx-arm64 ;;
  *) echo 'Unsupported host. Use native Linux glibc or macOS x64/ARM64; Windows uses package-windows.ps1.' >&2; exit 1 ;;
esac
for tool in curl tar awk; do
  command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done
if command -v sha256sum >/dev/null; then hash=(sha256sum)
elif command -v shasum >/dev/null; then hash=(shasum -a 256)
else echo 'Install sha256sum or shasum.' >&2; exit 1
fi
destination=${1:-"$root/.local/runtime"}
mkdir -p -- "$destination"
destination=$(cd -- "$destination" && pwd)
name="onnxruntime-$platform-1.22.0"
expected=$(awk -v p="$platform" '$1 == p { print $2 }' "$root/packaging/onnxruntime.tsv")
[[ ${#expected} == 64 ]] || { echo 'Missing runtime checksum.' >&2; exit 1; }
if [[ -e "$destination/$name" || -L "$destination/$name" ]]; then
  echo "Destination already exists: $destination/$name. Reuse it or choose another parent directory." >&2
  exit 1
fi
staging=$(mktemp -d "$destination/.download.XXXXXX")
trap 'rm -rf -- "$staging"' EXIT
curl --proto '=https' --tlsv1.2 --fail --location --retry 3 \
  "https://github.com/microsoft/onnxruntime/releases/download/v1.22.0/$name.tgz" \
  -o "$staging/runtime.tgz"
actual=$("${hash[@]}" "$staging/runtime.tgz" | awk '{ print $1 }')
[[ "$actual" == "$expected" ]] || { echo 'Runtime SHA-256 mismatch.' >&2; exit 1; }
tar -xzf "$staging/runtime.tgz" -C "$staging"
mv -- "$staging/$name" "$destination/$name"
echo "Runtime extracted: $destination/$name"
echo 'Pass the absolute lib/libonnxruntime.so (Linux) or lib/libonnxruntime.dylib (macOS) path with --ort-dylib.'
