#!/usr/bin/env bash
set -euo pipefail

nft_bin=${NFT_BIN:-nft}
grep_bin=${GREP_BIN:-grep}
sleep_bin=${SLEEP_BIN:-sleep}
max_attempts=${MAX_ATTEMPTS:-30}
retry_delay_seconds=${RETRY_DELAY_SECONDS:-1}
marker=weasel-netbird-cgnat-compat

for ((attempt = 1; attempt <= max_attempts; attempt++)); do
  if "$nft_bin" list chain ip filter ts-input >/dev/null 2>&1; then
    if "$nft_bin" list chain ip filter ts-input | "$grep_bin" --fixed-strings --quiet "$marker"; then
      exit 0
    fi

    "$nft_bin" insert rule ip filter ts-input \
      iifname nb-personal \
      ip saddr 100.96.0.0/16 \
      counter accept \
      comment "$marker"

    "$nft_bin" list chain ip filter ts-input \
      | "$grep_bin" --fixed-strings --quiet "$marker"
    exit 0
  fi

  if ((attempt < max_attempts)); then
    "$sleep_bin" "$retry_delay_seconds"
  fi
done

printf 'Tailscale ts-input chain did not appear after %s attempts\n' "$max_attempts" >&2
exit 1
