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

assert_matches() {
  local pattern=$1
  rg --pcre2 --quiet -- "$pattern" "$package_file" || {
    printf 'FAIL: %s does not match %s\n' "$package_file" "$pattern" >&2
    exit 1
  }
}

# Chromium loads libpulse.so dynamically. Without it, the official Electron
# payload silently falls back to ALSA and getUserMedia fails against PipeWire
# with NotReadableError: Could not start audio source.
# The exact version and hash intentionally change on every upstream update.
# Assert that both pins exist and retain Nix's expected SRI SHA-256 shape.
assert_matches '^  version = "[0-9]+\.[0-9]+\.[0-9]+";$'
assert_matches '^    hash = "sha256-[A-Za-z0-9+/]{43}=";$'
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
