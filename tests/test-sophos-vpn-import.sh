#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

profile=$tmpdir/source.ovpn
state=$tmpdir/imported
log=$tmpdir/nmcli.log

cat > "$profile" <<'PROFILE'
client
route remote_host 255.255.255.255 net_gateway
route 10.20.0.0 255.255.0.0
<ca>
redacted-test-data
</ca>
PROFILE

cat > "$tmpdir/nmcli" <<'NMCLI'
#!/usr/bin/env bash
set -euo pipefail
state=${FAKE_NM_STATE:?}
log=${FAKE_NM_LOG:?}
printf '%q ' "$@" >> "$log"
printf '\n' >> "$log"

if [[ ${1:-} == "-t" ]]; then
  [[ -e $state ]] && printf 'test-uuid:vpn\n'
  exit 0
fi

if [[ ${1:-} == "connection" && ${2:-} == "import" ]]; then
  profile=${6:?}
  [[ $profile != "$FAKE_SOURCE_PROFILE" ]]
  ! grep -Eq '^[[:space:]]*route[[:space:]]+remote_host[[:space:]]' "$profile"
  grep -Eq '^[[:space:]]*route[[:space:]]+10\.20\.0\.0[[:space:]]+255\.255\.0\.0' "$profile"
  touch "$state"
  exit 0
fi

if [[ ${1:-} == "connection" && ${2:-} == "modify" ]]; then
  exit 0
fi

exit 1
NMCLI
chmod +x "$tmpdir/nmcli"

cat > "$tmpdir/secret-tool" <<'SECRET'
#!/usr/bin/env bash
exit 1
SECRET
chmod +x "$tmpdir/secret-tool"

output=$(
  XDG_RUNTIME_DIR="$tmpdir" \
  NMCLI_BIN="$tmpdir/nmcli" \
  SECRET_TOOL_BIN="$tmpdir/secret-tool" \
  FAKE_NM_STATE="$state" \
  FAKE_NM_LOG="$log" \
  FAKE_SOURCE_PROFILE="$profile" \
  bash "$repo_root/scripts/sophos-vpn.sh" import "$profile" --name "Sophos VPN" --username "test.user"
)

jq -e '.ok == true and .state == "imported" and .username == "test.user"' <<< "$output" >/dev/null
printf 'PASS: NetworkManager compatibility import preserves the original profile\n'
