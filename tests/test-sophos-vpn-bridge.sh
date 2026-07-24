#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

vpn_state=$tmpdir/vpn-active
bridge_state=$tmpdir/bridge-active
control_socket=$tmpdir/control
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

chmod +x "$tmpdir/nmcli" "$tmpdir/secret-tool" "$tmpdir/ss" "$tmpdir/ssh"

run_helper() {
  XDG_RUNTIME_DIR="$tmpdir" \
  NMCLI_BIN="$tmpdir/nmcli" \
  SECRET_TOOL_BIN="$tmpdir/secret-tool" \
  SSH_BIN="$tmpdir/ssh" \
  SS_BIN="$tmpdir/ss" \
  SOPHOS_VPN_BRIDGE_CONTROL_SOCKET="$control_socket" \
  FAKE_VPN_STATE="$vpn_state" \
  FAKE_BRIDGE_STATE="$bridge_state" \
  FAKE_CONTROL_SOCKET="$control_socket" \
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

printf 'PASS: OpenVPN and the managed RDP bridge remain mutually exclusive\n'
