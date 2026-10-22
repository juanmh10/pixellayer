#!/usr/bin/env bash
set -euo pipefail
package_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
workspace=''
destination=''
cache=${PIXELLAYER_MODELS_CACHE:-}
client=''
existing=''
accept=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace|--destination|--cache-dir|--client|--existing)
      [ "$#" -ge 2 ] || { echo "Missing value for $1" >&2; exit 1; }
      case "$1" in
        --workspace) workspace=$2;; --destination) destination=$2;;
        --cache-dir) cache=$2;; --client) client=$2;; --existing) existing=$2;;
      esac
      shift 2;;
    --accept-download) accept=1; shift;;
    *) echo 'Usage: bash setup.sh --workspace TASK [--destination DIR] [--cache-dir DIR] [--client CLIENT] [--existing JSON] [--accept-download]' >&2; exit 1;;
  esac
done
[ -n "$workspace" ] && [ -d "$workspace" ] || { echo 'Choose an existing image task with --workspace' >&2; exit 1; }
workspace=$(cd -- "$workspace" && pwd -P)
bash "$package_root/verify.sh" >/dev/null
version=$("$package_root/pixellayer" --version)
version=${version#pixellayer }
case "$(uname -s)" in
  Linux)
    default_parent="${XDG_DATA_HOME:-$HOME/.local/share}/pixellayer"
    cache=${cache:-"${XDG_CACHE_HOME:-$HOME/.cache}/pixellayer/models"};;
  Darwin)
    default_parent="$HOME/Library/Application Support/PixelLayer"
    cache=${cache:-"$HOME/Library/Caches/PixelLayer/models"};;
  *) echo 'Use a native Linux/macOS package' >&2; exit 1;;
esac
destination=${destination:-"$default_parent/$version"}
case "$destination" in /*) ;; *) destination="$PWD/$destination";; esac
bash "$package_root/install.sh" "$destination" >&2
args=(--workspace "$workspace" --cache-dir "$cache" setup)
if [ "$accept" -eq 1 ]; then args+=(--accept-download); fi
if [ -n "$client" ]; then args+=(--client "$client"); fi
if [ -n "$existing" ]; then args+=(--existing "$existing"); fi
"$destination/pixellayer" "${args[@]}"
