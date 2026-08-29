#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
home_config="$repo_root/hosts/nixy-laptop/home.nix"
host_config="$repo_root/hosts/nixy-laptop/config.nix"
ui_package="$repo_root/packages/netbird-ui-bin.nix"

rg -q 'systemd\.user\.services\.netbird-ui' "$home_config"
rg -q 'if \[\[ -S /var/run/netbird-personal/sock \]\]' "$home_config"
rg -q -- '--daemon-addr=unix:///var/run/netbird-personal/sock' "$home_config"
rg -q 'daemonSocket = "unix:///var/run/netbird-personal/sock"' "$host_config" "$home_config"
rg -q 'daemonSocket \? "unix:///var/run/netbird.sock"' "$ui_package"
rg -q 'Restart = "on-failure"' "$home_config"
rg -q 'Hidden=true' "$home_config"
rg -q 'archiveLegacyNetbirdAutostart' "$home_config"
rg -q 'services\.tailscale\.enable = lib\.mkForce false' "$host_config"

if rg -q 'hermes-blain-tunnel|hermes-remote-bridge|netbird-tailscale-cgnat-compat' \
  "$host_config" "$home_config"; then
  echo "Obsolete Tailscale compatibility or blain bridge is still configured" >&2
  exit 1
fi

echo "NetBird UI integration checks passed"
