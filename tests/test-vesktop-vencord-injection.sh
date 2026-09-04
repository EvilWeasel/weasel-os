#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
package_file="$repo_root/packages/vesktop-bin.nix"
patcher_file="$repo_root/scripts/patch-vesktop-wayland-capture.mjs"

require() {
  grep -F -- "$2" "$1" >/dev/null || {
    printf 'missing Vesktop invariant in %s: %s\n' "$1" "$2" >&2
    exit 1
  }
}

require "$package_file" 'version = "1.6.7";'
require "$package_file" 'src = patchedAppimageContents;'
require "$package_file" 'node ${../scripts/patch-vesktop-wayland-capture.mjs} app/dist/js/main.js'
require "$package_file" 'vencordDesktopMain.js'
require "$package_file" 'vencordDesktopPreload.js'
require "$package_file" 'vencordDesktopRenderer.js'
require "$package_file" 'vencordDesktopRenderer.css'
require "$package_file" 'sessionData/vencordFiles'
require "$package_file" 'package.json'
require "$package_file" "grep -Fq 'VoiceMessages'"
require "$package_file" 'install -Dm600'
require "$package_file" 'vesktop-vencord-bootstrap'
require "$patcher_file" 'expected exactly one Vesktop 1.6.7 Wayland capture handler'

if [[ -n ${VESKTOP_PACKAGE:-} ]]; then
  for asset in \
    vencordDesktopMain.js \
    vencordDesktopPreload.js \
    vencordDesktopRenderer.js \
    vencordDesktopRenderer.css; do
    test -s "$VESKTOP_PACKAGE/share/vesktop/vencord/$asset"
  done
  grep -F 'VoiceMessages' \
    "$VESKTOP_PACKAGE/share/vesktop/vencord/vencordDesktopMain.js" >/dev/null
  grep -F 'vesktop-vencord-bootstrap' "$VESKTOP_PACKAGE/bin/vesktop" >/dev/null
  test -f "$VESKTOP_PACKAGE/share/applications/vesktop.desktop"
  grep -Fx 'Exec=vesktop %U' "$VESKTOP_PACKAGE/share/applications/vesktop.desktop" >/dev/null
fi

printf 'PASS: Vesktop preserves Wayland capture and bootstraps Vencord\n'
