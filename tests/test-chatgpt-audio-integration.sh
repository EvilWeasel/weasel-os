#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
package_file="$repo_root/packages/chatgpt/default.nix"

assert_contains() {
  local expected=$1
  rg -F --quiet -- "$expected" "$package_file" || {
    printf 'FAIL: %s does not contain %s\n' "$package_file" "$expected" >&2
    exit 1
  }
}

# Chromium loads libpulse.so dynamically. Without it, the official Electron
# payload silently falls back to ALSA and getUserMedia fails against PipeWire
# with NotReadableError: Could not start audio source.
assert_contains 'version = "26.901.31953";'
assert_contains 'hash = "sha256-6TyfiefNvKjAfCk7TYO6+d7tCrCP6+s4w80TrR3Aidc=";'
assert_contains 'libpulseaudio,'
assert_contains 'libpulseaudio'
assert_contains '--prefix LD_LIBRARY_PATH : ${lib.makeLibraryPath [ libpulseaudio ]}'

if [[ -n ${CHATGPT_PACKAGE:-} ]]; then
  wrapper="$CHATGPT_PACKAGE/bin/chatgpt"
  [[ -x $wrapper ]] || {
    printf 'FAIL: built ChatGPT wrapper is missing or not executable: %s\n' "$wrapper" >&2
    exit 1
  }

  rg -aFq 'LD_LIBRARY_PATH' "$wrapper" || {
    printf 'FAIL: built ChatGPT wrapper does not configure LD_LIBRARY_PATH\n' >&2
    exit 1
  }
  rg -aFq 'libpulseaudio' "$wrapper" || {
    printf 'FAIL: built ChatGPT wrapper does not reference libpulseaudio\n' >&2
    exit 1
  }
  nix-store -qR "$CHATGPT_PACKAGE" | rg -q 'libpulseaudio' || {
    printf 'FAIL: built ChatGPT closure does not contain libpulseaudio\n' >&2
    exit 1
  }
fi

printf 'PASS: ChatGPT package pins current official RPM and exposes PulseAudio to Chromium\n'
