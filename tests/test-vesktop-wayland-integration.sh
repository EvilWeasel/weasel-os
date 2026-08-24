#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
package_file="$repo_root/packages/vesktop-bin.nix"
portal_file="$repo_root/profiles/system/laptop.nix"

assert_contains() {
  local file=$1
  local expected=$2
  if ! grep -F -- "$expected" "$file" >/dev/null; then
    printf 'FAIL: %s does not contain %q\n' "$file" "$expected" >&2
    return 1
  fi
}

# The package must export a launcher-visible desktop entry rather than only a
# command-line wrapper.
assert_contains "$package_file" '"$out/share/applications/vesktop.desktop"'
assert_contains "$package_file" "--replace-fail 'Exec=AppRun --no-sandbox %U' 'Exec=vesktop %U'"
assert_contains "$package_file" 'cp -r ${appimageContents}/usr/share/icons "$out/share/"'

# Niri's supported screencast backend is xdg-desktop-portal-gnome. Do not
# route ScreenCast through xdp-wlr: on this Niri session its slurp chooser
# exits without a valid output and xdp-wlr reports `no output found`.
assert_contains "$portal_file" '"org.freedesktop.impl.portal.ScreenCast" = [ "gnome" ];'
assert_contains "$portal_file" '"org.freedesktop.impl.portal.Screenshot" = [ "gnome" ];'
if grep -F -- 'xdg-desktop-portal-wlr' "$portal_file" >/dev/null; then
  printf 'FAIL: %s must not enable the unsupported Niri wlr portal path\n' "$portal_file" >&2
  exit 1
fi

# Optional built-artifact checks. These make the same test useful against the
# evaluated Vesktop package before activation.
if [[ -n ${VESKTOP_PACKAGE:-} ]]; then
  desktop="$VESKTOP_PACKAGE/share/applications/vesktop.desktop"
  [[ -f $desktop ]]
  grep -Fx 'Exec=vesktop %U' "$desktop" >/dev/null
  [[ -d $VESKTOP_PACKAGE/share/icons ]]
fi

printf 'PASS: Vesktop launcher and supported Niri GNOME portal path are declarative\n'
