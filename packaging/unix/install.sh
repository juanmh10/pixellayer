#!/usr/bin/env bash
set -euo pipefail
package_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
bash "$package_root/verify.sh" >/dev/null
version=$("$package_root/pixellayer" --version)
version=${version#pixellayer }
case "$version" in ''|*[!0-9A-Za-z.+-]*) echo 'Invalid executable version' >&2; exit 1;; esac
case "$(uname -s)" in
  Linux) default_parent="${XDG_DATA_HOME:-$HOME/.local/share}/pixellayer";;
  Darwin) default_parent="$HOME/Library/Application Support/PixelLayer";;
  *) echo 'Use a native Linux/macOS package' >&2; exit 1;;
esac
destination=${1:-"$default_parent/$version"}
case "$destination" in /*) ;; *) destination="$PWD/$destination";; esac
if [ -e "$destination" ] || [ -L "$destination" ]; then
  [ -d "$destination" ] && [ ! -L "$destination" ] || { echo 'Destination must be a regular directory' >&2; exit 1; }
  cmp "$package_root/SHA256SUMS" "$destination/SHA256SUMS" >/dev/null || { echo 'Different build: choose a new destination' >&2; exit 1; }
  (cd "$destination"; if command -v sha256sum >/dev/null; then sha256sum -c SHA256SUMS; else shasum -a 256 -c SHA256SUMS; fi) >/dev/null
  "$destination/pixellayer" --version
  echo "Already installed and verified at $destination"
  exit 0
fi
parent=$(dirname -- "$destination")
mkdir -p -- "$parent"
staging=$(mktemp -d "$parent/.pixellayer-install.XXXXXXXX")
trap 'rm -rf -- "$staging"' EXIT
cp -R "$package_root/." "$staging/"
bash "$staging/verify.sh" >/dev/null
"$staging/pixellayer" --version
# Rename within the same filesystem. Do not merge into a concurrent destination.
if [ -e "$destination" ] || [ -L "$destination" ]; then echo 'Destination appeared during installation; retry' >&2; exit 1; fi
mv -- "$staging" "$destination"
trap - EXIT
echo "Installed at $destination"
echo 'Cache, PATH and agent settings are unchanged. Use doctor and configure for this task.'
