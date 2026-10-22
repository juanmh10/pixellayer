#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ -f ./uninstall.sh && ! -L ./uninstall.sh ]] || { echo 'Required uninstaller is missing or not a regular file.' >&2; exit 1; }
grep -Fq '"path": "uninstall.sh"' manifest.json || { echo 'Uninstaller is absent from the package manifest.' >&2; exit 1; }
awk '$2 == "uninstall.sh" { found=1 } END { exit !found }' SHA256SUMS || { echo 'Uninstaller is absent from SHA256SUMS.' >&2; exit 1; }
if command -v sha256sum >/dev/null; then
  sha256sum --check SHA256SUMS
else
  shasum -a 256 --check SHA256SUMS
fi
