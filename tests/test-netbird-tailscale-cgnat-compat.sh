#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
helper="$repo_root/scripts/netbird-tailscale-cgnat-compat.sh"
config="$repo_root/hosts/nixy-laptop/config.nix"
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

[[ -x $helper ]] || {
  printf 'FAIL: compatibility helper is missing or not executable: %s\n' "$helper" >&2
  exit 1
}

grep -Fq 'partOf = [ "tailscaled.service" ];' "$config"
grep -A3 -F 'wantedBy = [' "$config" | grep -Fq '"tailscaled.service"'
grep -Fq 'Restart = "on-failure";' "$config"
grep -Fq 'RestartSec = "5s";' "$config"
grep -Fq 'ExecStart = lib.getExe netbirdTailscaleCgnatCompat;' "$config"
grep -Fq 'StartLimitIntervalSec = "10min";' "$config"
grep -Fq 'StartLimitBurst = 12;' "$config"

ready="$tmpdir/chain-ready"
installed="$tmpdir/rule-installed"
insert_count="$tmpdir/insert-count"
printf '0\n' > "$insert_count"

cat > "$tmpdir/nft" <<'NFT'
#!/usr/bin/env bash
set -euo pipefail

if [[ $* == 'list chain ip filter ts-input' ]]; then
  [[ -e $FAKE_CHAIN_READY ]] || exit 1
  printf 'chain ts-input {\n'
  if [[ -e $FAKE_RULE_INSTALLED ]]; then
    printf '  iifname "nb-personal" ip saddr 100.96.0.0/16 counter accept comment "weasel-netbird-cgnat-compat"\n'
  fi
  printf '  ip saddr 100.64.0.0/10 iifname != "tailscale0" counter drop\n'
  printf '}\n'
  exit 0
fi

if [[ ${1:-} == insert && ${2:-} == rule ]]; then
  expected='insert rule ip filter ts-input iifname nb-personal ip saddr 100.96.0.0/16 counter accept comment weasel-netbird-cgnat-compat'
  [[ $* == "$expected" ]] || {
    printf 'unexpected insert command: %s\n' "$*" >&2
    exit 1
  }
  count=$(<"$FAKE_INSERT_COUNT")
  printf '%s\n' "$((count + 1))" > "$FAKE_INSERT_COUNT"
  touch "$FAKE_RULE_INSTALLED"
  exit 0
fi

printf 'unexpected nft command: %s\n' "$*" >&2
exit 1
NFT

cat > "$tmpdir/sleep" <<'SLEEP'
#!/usr/bin/env bash
exit 0
SLEEP
chmod +x "$tmpdir/nft" "$tmpdir/sleep"

run_helper() {
  NFT_BIN="$tmpdir/nft" \
  SLEEP_BIN="$tmpdir/sleep" \
  MAX_ATTEMPTS=2 \
  RETRY_DELAY_SECONDS=0 \
  FAKE_CHAIN_READY="$ready" \
  FAKE_RULE_INSTALLED="$installed" \
  FAKE_INSERT_COUNT="$insert_count" \
  "$helper"
}

# The first bounded service attempt must fail when tailscaled has not created
# ts-input yet. systemd's on-failure policy will schedule the next attempt.
if run_helper; then
  printf 'FAIL: helper succeeded before ts-input existed\n' >&2
  exit 1
fi

# A later service attempt must recover, install the exact narrow exception
# before the CGNAT drop, and remain idempotent on subsequent starts.
touch "$ready"
run_helper
run_helper
[[ $(<"$insert_count") == 1 ]]

rules=$(NFT_BIN="$tmpdir/nft" \
  FAKE_CHAIN_READY="$ready" \
  FAKE_RULE_INSTALLED="$installed" \
  FAKE_INSERT_COUNT="$insert_count" \
  "$tmpdir/nft" list chain ip filter ts-input)
accept_line=$(grep -nF 'iifname "nb-personal" ip saddr 100.96.0.0/16' <<< "$rules" | cut -d: -f1)
drop_line=$(grep -nF 'ip saddr 100.64.0.0/10 iifname != "tailscale0"' <<< "$rules" | cut -d: -f1)
[[ $accept_line -lt $drop_line ]]

printf 'PASS: delayed ts-input creation recovers with one narrow, ordered rule\n'
