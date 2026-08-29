#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
package_file="$repo_root/packages/vesktop-bin.nix"
patcher_file="$repo_root/scripts/patch-vesktop-wayland-capture.mjs"
portal_file="$repo_root/profiles/system/laptop.nix"

assert_contains() {
  local file=$1
  local expected=$2
  grep -F -- "$expected" "$file" >/dev/null || {
    printf 'FAIL: %s does not contain %s\n' "$file" "$expected" >&2
    exit 1
  }
}

assert_contains "$package_file" 'version = "1.6.7";'
assert_contains "$package_file" 'patchedAppimageContents ='
assert_contains "$package_file" 'runCommand "${pname}-${version}-wayland-patched"'
assert_contains "$package_file" 'node ${../scripts/patch-vesktop-wayland-capture.mjs} app/dist/js/main.js'
assert_contains "$package_file" "asar pack app \"\$out/resources/app.asar\" --unpack '**/*.node'"
assert_contains "$package_file" '"$out/share/applications/vesktop.desktop"'
assert_contains "$package_file" "--replace-fail 'Exec=AppRun --no-sandbox %U' 'Exec=vesktop %U'"
assert_contains "$package_file" 'cp -r ${patchedAppimageContents}/usr/share/icons "$out/share/"'
assert_contains "$patcher_file" 'const brokenWaylandHandler ='
assert_contains "$patcher_file" 'const directWaylandCapture ='
assert_contains "$patcher_file" 'expected exactly one Vesktop 1.6.7 Wayland capture handler'

# Niri exposes its supported screencast interface through the GNOME portal.
# The wlr backend cannot enumerate Niri outputs and must not own ScreenCast.
assert_contains "$portal_file" 'xdg-desktop-portal-gnome'
assert_contains "$portal_file" '"org.freedesktop.impl.portal.ScreenCast" = [ "gnome" ];'
assert_contains "$portal_file" '"org.freedesktop.impl.portal.Screenshot" = [ "gnome" ];'
if grep -F -- 'xdg-desktop-portal-wlr' "$portal_file" >/dev/null; then
  printf 'FAIL: %s enables the unsupported Niri wlr portal path\n' "$portal_file" >&2
  exit 1
fi

if [[ -n ${VESKTOP_PACKAGE:-} ]]; then
  desktop="$VESKTOP_PACKAGE/share/applications/vesktop.desktop"
  [[ -f $desktop ]]
  grep -Fx 'Exec=vesktop %U' "$desktop" >/dev/null
  [[ -d $VESKTOP_PACKAGE/share/icons ]]
fi

printf 'PASS: Vesktop desktop integration and Niri portal routing are declarative\n'
