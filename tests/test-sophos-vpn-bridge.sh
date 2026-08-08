#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

vpn_state=$tmpdir/vpn-active
bridge_state=$tmpdir/bridge-active
control_socket=$tmpdir/control
stream_route_state=$tmpdir/stream-route
stream_probe_state=$tmpdir/stream-probe
log=$tmpdir/actions.log

cat > "$tmpdir/nmcli" <<'NMCLI'
#!/usr/bin/env bash
set -euo pipefail
printf 'nmcli %q ' "$@" >> "$FAKE_ACTION_LOG"
printf '\n' >> "$FAKE_ACTION_LOG"

if [[ ${1:-} == "-t" && ${2:-} == "-f" && ${3:-} == "NAME,TYPE" ]]; then
  printf 'Sophos VPN:vpn\n'
  exit 0
fi
if [[ ${1:-} == "-t" && ${2:-} == "-f" && ${3:-} == "NAME,TYPE,DEVICE" ]]; then
  [[ -e $FAKE_VPN_STATE ]] && printf 'Sophos VPN:vpn:tun0\n'
  exit 0
fi
if [[ ${1:-} == "-g" ]]; then
  printf '10.8.0.2/24\n'
  exit 0
fi
if [[ ${1:-} == "--wait" && ${3:-} == "connection" && ${4:-} == "down" ]]; then
  rm -f "$FAKE_VPN_STATE"
  exit 0
fi
exit 1
NMCLI

cat > "$tmpdir/secret-tool" <<'SECRET'
#!/usr/bin/env bash
exit 1
SECRET

cat > "$tmpdir/ss" <<'SS'
#!/usr/bin/env bash
set -euo pipefail
[[ -e $FAKE_BRIDGE_STATE ]] && printf 'LISTEN 0 128 127.0.0.1:13389 0.0.0.0:*\n'
SS

cat > "$tmpdir/ssh" <<'SSH'
#!/usr/bin/env bash
set -euo pipefail
printf 'ssh %q ' "$@" >> "$FAKE_ACTION_LOG"
printf '\n' >> "$FAKE_ACTION_LOG"

if [[ " $* " == *" -O check "* ]]; then
  [[ -e $FAKE_BRIDGE_STATE && -e $FAKE_CONTROL_SOCKET ]]
  exit
fi
if [[ " $* " == *" -O exit "* ]]; then
  rm -f "$FAKE_BRIDGE_STATE" "$FAKE_CONTROL_SOCKET"
  exit 0
fi
if [[ " $* " == *" -fN "* ]]; then
  touch "$FAKE_BRIDGE_STATE" "$FAKE_CONTROL_SOCKET"
  exit 0
fi
exit 1
SSH

cat > "$tmpdir/ip" <<'IP'
#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == "route" && ${2:-} == "get" && ${3:-} == "10.145.5.50" ]]; then
  if [[ -e $FAKE_STREAM_ROUTE_STATE ]]; then
    printf '10.145.5.50 dev tailscale0 src 100.64.0.2\n'
  else
    printf '10.145.5.50 via 192.0.2.1 dev wlan0 src 192.0.2.2\n'
  fi
  exit 0
fi
exit 1
IP

cat > "$tmpdir/timeout" <<'TIMEOUT'
#!/usr/bin/env bash
set -euo pipefail
[[ -e $FAKE_STREAM_PROBE_STATE ]]
TIMEOUT

chmod +x "$tmpdir/nmcli" "$tmpdir/secret-tool" "$tmpdir/ss" "$tmpdir/ssh" "$tmpdir/ip" "$tmpdir/timeout"

run_helper() {
  XDG_RUNTIME_DIR="$tmpdir" \
  NMCLI_BIN="$tmpdir/nmcli" \
  SECRET_TOOL_BIN="$tmpdir/secret-tool" \
  SSH_BIN="$tmpdir/ssh" \
  SS_BIN="$tmpdir/ss" \
  IP_BIN="$tmpdir/ip" \
  TIMEOUT_BIN="$tmpdir/timeout" \
  SOPHOS_VPN_BRIDGE_CONTROL_SOCKET="$control_socket" \
  FAKE_VPN_STATE="$vpn_state" \
  FAKE_BRIDGE_STATE="$bridge_state" \
  FAKE_CONTROL_SOCKET="$control_socket" \
  FAKE_STREAM_ROUTE_STATE="$stream_route_state" \
  FAKE_STREAM_PROBE_STATE="$stream_probe_state" \
  FAKE_ACTION_LOG="$log" \
  bash "$repo_root/scripts/sophos-vpn.sh" "$@"
}

touch "$vpn_state"
output=$(run_helper bridge-connect)
jq -e '
  .ok == true
  and .state == "bridge-connected"
  and .vpn_connected == false
  and .bridge_connected == true
  and .bridge_managed == true
  and .stream_route_ready == false
  and .stream_tcp_reachable == false
  and .stream_udp_verified == false
' <<< "$output" >/dev/null
[[ ! -e $vpn_state ]]
[[ -e $bridge_state ]]

output=$(run_helper bridge-disconnect)
jq -e '
  .ok == true
  and .state == "disconnected"
  and .bridge_connected == false
' <<< "$output" >/dev/null
[[ ! -e $bridge_state ]]

touch "$stream_route_state" "$stream_probe_state"
output=$(run_helper status)
jq -e '
  .stream_host == "10.145.5.50"
  and .stream_route_device == "tailscale0"
  and .stream_route_ready == true
  and .stream_tcp_reachable == true
  and .stream_udp_verified == false
  and .stream_status == "control-reachable"
' <<< "$output" >/dev/null

rm -f "$stream_probe_state"
output=$(run_helper status)
jq -e '
  .stream_route_ready == true
  and .stream_tcp_reachable == false
  and .stream_status == "control-unreachable"
' <<< "$output" >/dev/null

printf 'PASS: RDP bridge lifecycle and direct Moonlight/Sunshine readiness remain separate\n'
