#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

require() {
  grep -F -- "$2" "$1" >/dev/null || {
    printf 'missing laptop executor invariant in %s: %s\n' "$1" "$2" >&2
    exit 1
  }
}

home="$root/hosts/nixy-laptop/home.nix"
laptop="$root/profiles/system/laptop.nix"
executor="$root/scripts/weasel-laptop-executor.nix"
cua="$root/packages/cua-driver-bin.nix"
codex="$root/packages/codex-bin.nix"

require "$cua" 'version = "0.23.2";'
require "$cua" 'sha256-Ab+DOewSnMAPS0ssYFbvGnxbUt85/4OtF8mxaBiuxQA='
require "$codex" 'version = "0.153.3";'
require "$codex" 'sha256-UFktUtFpRhX5zPPKUEMrtFIal8vJOqLDl2j6ZZ24FbU='
require "$home" 'systemd.user.services.cua-driver'
require "$home" 'cua-driver serve --permission-mode standard'
require "$home" 'cua-driver telemetry disable'
require "$home" 'CUA_DRIVER_RS_ENABLE_WAYLAND=1'
require "$laptop" 'services.gnome.at-spi2-core.enable = true;'
require "$home" 'package = codexLatest;'
require "$executor" "-c 'mcp_servers={}'"
require "$executor" '--sandbox workspace-write'
require "$executor" 'systemd-run --user --collect'
require "$executor" 'prompt must be under'
require "$executor" 'workdir is outside the approved laptop repositories'

if grep -F -- '--dangerously-bypass-approvals' "$home" "$executor" >/dev/null; then
  echo 'executor must not bypass approvals/sandbox' >&2
  exit 1
fi
if grep -F -- '--grant existing-profile' "$home" >/dev/null; then
  echo 'CUA must not attach to existing browser profiles' >&2
  exit 1
fi

printf 'PASS: local CUA and task-bound Codex executor stay scoped\n'
