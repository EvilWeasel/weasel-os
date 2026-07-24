#!/usr/bin/env bash
set -euo pipefail

umask 077
ulimit -S -c 0 2>/dev/null || true

CONNECTION_NAME=${SOPHOS_VPN_CONNECTION_NAME:-Sophos VPN}
SECRET_SERVICE=${SOPHOS_VPN_SECRET_SERVICE:-sophos-vpn}
SECRET_ACCOUNT=${SOPHOS_VPN_SECRET_ACCOUNT:-default}
DEFAULT_IMPORT_USERNAME=${SOPHOS_VPN_USERNAME:-}
NMCLI_BIN=${NMCLI_BIN:-nmcli}
SECRET_TOOL_BIN=${SECRET_TOOL_BIN:-secret-tool}

usage() {
  cat <<'EOF'
Usage:
  sophos-vpn status
  sophos-vpn connect
  sophos-vpn disconnect
  sophos-vpn import <profile.ovpn> [--name <connection-name>] [--username <vpn-username>]
  sophos-vpn store-password

Notes:
  - connect reads the 6-digit TOTP from stdin when stdin is not a TTY.
  - otherwise connect prompts on /dev/tty without echo.
  - the base password lives in Secret Service under:
      service=sophos-vpn account=default kind=base-password
EOF
}

json_output() {
  jq -n "$@"
}

json_status() {
  local state=$1
  local connected=$2
  local has_secret=$3
  local device=$4
  local ip4=$5
  local message=$6
  local bar_text detail_text severity

  case "$state" in
    connected)
      bar_text="VPN ON"
      detail_text=${ip4:+$device $ip4}
      detail_text=${detail_text:-Connected}
      severity="ok"
      ;;
    connecting)
      bar_text="VPN ..."
      detail_text="Connecting"
      severity="warn"
      ;;
    missing)
      bar_text="VPN !"
      detail_text="Connection missing"
      severity="error"
      ;;
    error)
      bar_text="VPN !"
      detail_text=${message:-Error}
      severity="error"
      ;;
    *)
      bar_text="VPN OFF"
      detail_text="Disconnected"
      severity="inactive"
      ;;
  esac

  # shellcheck disable=SC2016
  json_output \
    --arg connection "$CONNECTION_NAME" \
    --arg state "$state" \
    --arg device "$device" \
    --arg ip4 "$ip4" \
    --arg message "$message" \
    --arg bar_text "$bar_text" \
    --arg detail_text "$detail_text" \
    --arg severity "$severity" \
    --argjson connected "$connected" \
    --argjson has_secret "$has_secret" \
    '{
      ok: ($state != "error"),
      connection: $connection,
      connected: $connected,
      state: $state,
      device: $device,
      ip4: $ip4,
      has_base_password: $has_secret,
      bar_text: $bar_text,
      detail_text: $detail_text,
      severity: $severity,
      message: $message,
      available_actions: (if $connected then ["disconnect","status"] else ["connect","status"] end)
    }'
}

json_error() {
  local action=$1
  local message=$2
  # shellcheck disable=SC2016
  json_output \
    --arg action "$action" \
    --arg message "$message" \
    --arg connection "$CONNECTION_NAME" \
    '{ok:false, action:$action, connection:$connection, state:"error", message:$message, bar_text:"VPN !", severity:"error"}'
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

require_bins() {
  command_exists "$NMCLI_BIN" || {
    json_error "bootstrap" "nmcli not found" >&2
    exit 127
  }
  command_exists "$SECRET_TOOL_BIN" || {
    json_error "bootstrap" "secret-tool not found" >&2
    exit 127
  }
  command_exists jq || {
    printf '%s\n' '{"ok":false,"action":"bootstrap","state":"error","message":"jq not found"}' >&2
    exit 127
  }
}

secret_lookup() {
  "$SECRET_TOOL_BIN" lookup service "$SECRET_SERVICE" account "$SECRET_ACCOUNT" kind base-password 2>/dev/null || true
}

has_secret() {
  [[ -n $(secret_lookup) ]]
}

read_hidden_line() {
  local prompt=$1
  local value=
  if [[ -t 0 ]]; then
    printf '%s' "$prompt" > /dev/tty
    IFS= read -r -s value < /dev/tty || true
    printf '\n' > /dev/tty
  else
    IFS= read -r value || true
  fi
  printf '%s' "$value"
}

ensure_connection_exists() {
  "$NMCLI_BIN" -t -f NAME,TYPE connection show 2>/dev/null | grep -Fxq "$CONNECTION_NAME:vpn"
}

active_device() {
  "$NMCLI_BIN" -t -f NAME,TYPE,DEVICE connection show --active 2>/dev/null | awk -F: -v target="$CONNECTION_NAME" '$1 == target && $2 == "vpn" { print $3; exit }'
}

active_ip4() {
  local device=$1
  [[ -n $device ]] || return 0
  "$NMCLI_BIN" -g IP4.ADDRESS device show "$device" 2>/dev/null | paste -sd, - | sed 's#/.*##g'
}

print_status() {
  local device ip4
  local secret_present=false
  if has_secret; then
    secret_present=true
  fi

  if ! ensure_connection_exists; then
    json_status missing false "$secret_present" "" "" "connection not imported"
    return 0
  fi

  device=$(active_device)
  if [[ -n $device ]]; then
    ip4=$(active_ip4 "$device")
    json_status connected true "$secret_present" "$device" "$ip4" ""
    return 0
  fi

  json_status disconnected false "$secret_present" "" "" ""
}

store_password() {
  local password
  password=$(read_hidden_line "Base VPN password: ")
  if [[ -z $password ]]; then
    json_error store-password "empty password"
    return 1
  fi

  if printf '%s' "$password" | "$SECRET_TOOL_BIN" store --label="$CONNECTION_NAME base password" service "$SECRET_SERVICE" account "$SECRET_ACCOUNT" kind base-password >/dev/null; then
    # shellcheck disable=SC2016
    json_output --arg action "store-password" --arg connection "$CONNECTION_NAME" '{ok:true, action:$action, connection:$connection, message:"base password stored", severity:"ok"}'
    return 0
  fi

  json_error store-password "failed to store password"
  return 1
}

connect_vpn() {
  local base_password totp combined
  local tmpdir passwd_file stderr_file

  if ! ensure_connection_exists; then
    json_error connect "connection not imported"
    return 1
  fi

  base_password=$(secret_lookup)
  if [[ -z $base_password ]]; then
    json_error connect "base password missing in Secret Service"
    return 1
  fi

  totp=$(read_hidden_line "TOTP (6 digits): ")
  if [[ ! $totp =~ ^[0-9]{6}$ ]]; then
    json_error connect "TOTP must be exactly 6 digits"
    return 1
  fi

  combined=${base_password}${totp}
  tmpdir=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/sophos-vpn.XXXXXX")
  passwd_file=$tmpdir/passwd
  stderr_file=$tmpdir/nmcli.stderr
  trap 'rm -rf -- "${tmpdir:-}"' RETURN

  printf 'vpn.secrets.password:%s\n' "$combined" > "$passwd_file"

  if "$NMCLI_BIN" --wait 45 connection up id "$CONNECTION_NAME" passwd-file "$passwd_file" > /dev/null 2>"$stderr_file"; then
    print_status | jq '. + {action:"connect", message:"connected"}'
    return 0
  fi

  print_status >/dev/null 2>&1 || true
  local safe_error
  safe_error=$(tail -n 1 "$stderr_file" | tr -d '\r' | sed 's/[[:space:]]\+/ /g')
  safe_error=${safe_error:-connection failed}
  json_error connect "$safe_error"
  return 1
}

disconnect_vpn() {
  if ! ensure_connection_exists; then
    json_error disconnect "connection not imported"
    return 1
  fi

  if [[ -z $(active_device) ]]; then
    # shellcheck disable=SC2016
    json_output --arg action "disconnect" --arg connection "$CONNECTION_NAME" '{ok:true, action:$action, connection:$connection, connected:false, state:"disconnected", message:"already disconnected", severity:"inactive"}'
    return 0
  fi

  if "$NMCLI_BIN" --wait 30 connection down id "$CONNECTION_NAME" > /dev/null 2>&1; then
    # shellcheck disable=SC2016
    json_output --arg action "disconnect" --arg connection "$CONNECTION_NAME" '{ok:true, action:$action, connection:$connection, connected:false, state:"disconnected", message:"disconnected", bar_text:"VPN OFF", severity:"inactive"}'
    return 0
  fi

  json_error disconnect "disconnect failed"
  return 1
}

import_profile() {
  local profile_path=${1:-}
  local import_name=$CONNECTION_NAME
  local import_username=$DEFAULT_IMPORT_USERNAME
  local before_file after_file stderr_file tmpdir import_profile_path new_uuid imported_uuid_count

  [[ -n $profile_path ]] || {
    json_error import "missing .ovpn path"
    return 1
  }
  [[ -f $profile_path ]] || {
    json_error import "profile not found"
    return 1
  }

  shift || true
  while (($#)); do
    case $1 in
      --name)
        import_name=${2:-}
        shift 2
        ;;
      --username)
        import_username=${2:-}
        shift 2
        ;;
      *)
        json_error import "unknown argument: $1"
        return 1
        ;;
    esac
  done

  tmpdir=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/sophos-vpn-import.XXXXXX")
  before_file=$tmpdir/before
  after_file=$tmpdir/after
  stderr_file=$tmpdir/nmcli.stderr
  import_profile_path=$tmpdir/profile.ovpn
  trap 'rm -rf -- "${tmpdir:-}"' RETURN

  # NetworkManager rejects OpenVPN's remote_host route placeholder. It already
  # keeps the VPN server reachable through the pre-tunnel gateway itself.
  awk '
    {
      normalized = $0
      sub(/^[[:space:]]+/, "", normalized)
      count = split(normalized, field, /[[:space:]]+/)
      if (count == 4 && field[1] == "route" && field[2] == "remote_host" && field[4] == "net_gateway") {
        next
      }
      print
    }
  ' "$profile_path" > "$import_profile_path"

  "$NMCLI_BIN" -t -f UUID,TYPE connection show 2>/dev/null | awk -F: '$2 == "vpn" { print $1 }' | sort > "$before_file"

  if ! "$NMCLI_BIN" connection import type openvpn file "$import_profile_path" > /dev/null 2>"$stderr_file"; then
    json_error import "$(tail -n 1 "$stderr_file" | tr -d '\r')"
    return 1
  fi

  "$NMCLI_BIN" -t -f UUID,TYPE connection show 2>/dev/null | awk -F: '$2 == "vpn" { print $1 }' | sort > "$after_file"
  new_uuid=$(comm -13 "$before_file" "$after_file" | head -n 1)
  imported_uuid_count=$(comm -13 "$before_file" "$after_file" | wc -l | tr -d ' ')

  if [[ -z $new_uuid || $imported_uuid_count != 1 ]]; then
    json_error import "could not identify imported connection; inspect nmcli connection show"
    return 1
  fi

  "$NMCLI_BIN" connection modify uuid "$new_uuid" connection.id "$import_name" connection.autoconnect no ipv4.never-default yes ipv6.never-default yes >/dev/null
  if [[ -n $import_username ]]; then
    "$NMCLI_BIN" connection modify id "$import_name" vpn.user-name "$import_username" >/dev/null
  fi

  # shellcheck disable=SC2016
  json_output \
    --arg action "import" \
    --arg connection "$import_name" \
    --arg username "$import_username" \
    '{
      ok:true,
      action:$action,
      connection:$connection,
      state:"imported",
      username: $username,
      message:"profile imported; base password remains external",
      severity:"ok"
    }'
}

main() {
  require_bins
  local cmd=${1:-status}
  case "$cmd" in
    status)
      shift
      print_status
      ;;
    connect)
      shift
      connect_vpn "$@"
      ;;
    disconnect)
      shift
      disconnect_vpn "$@"
      ;;
    import)
      shift
      import_profile "$@"
      ;;
    store-password)
      shift
      store_password
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      usage >&2
      return 2
      ;;
  esac
}

main "$@"
