{pkgs}:
pkgs.writeShellScriptBin "weasel-dms-session" ''
  set -euo pipefail

  host="''${WEASEL_OS_HOST:-$(${pkgs.inetutils}/bin/hostname)}"
  debug_home="''${WEASEL_DEBUG_HOME:-$HOME/weasel-debug}"
  debug_state="''${WEASEL_DEBUG_STATE:-''${XDG_STATE_HOME:-$HOME/.local/state}/weasel-debug}"
  dms_log_dir="$debug_state/dms"
  timestamp="$(${pkgs.coreutils}/bin/date +%Y%m%d-%H%M%S)"
  log_file="$dms_log_dir/''${host}-''${timestamp}.log"
  env_file="$dms_log_dir/''${host}-''${timestamp}.env"

  ${pkgs.coreutils}/bin/mkdir -p "$debug_home" "$dms_log_dir"

  {
    printf 'timestamp=%s\n' "$timestamp"
    printf 'host=%s\n' "$host"
    printf 'user=%s\n' "$USER"
    printf 'pwd=%s\n' "$PWD"
    printf 'wayland_display=%s\n' "''${WAYLAND_DISPLAY:-}"
    printf 'xdg_runtime_dir=%s\n' "''${XDG_RUNTIME_DIR:-}"
    printf 'dms=%s\n' "$(${pkgs.coreutils}/bin/realpath "$(${pkgs.coreutils}/bin/readlink -f "$(${pkgs.which}/bin/which dms)")" 2>/dev/null || ${pkgs.which}/bin/which dms || true)"
    printf 'qs=%s\n' "$(${pkgs.coreutils}/bin/realpath "$(${pkgs.coreutils}/bin/readlink -f "$(${pkgs.which}/bin/which qs)")" 2>/dev/null || ${pkgs.which}/bin/which qs || true)"
    printf '\n'
    ${pkgs.coreutils}/bin/env | ${pkgs.coreutils}/bin/sort
  } >"$env_file"

  ${pkgs.coreutils}/bin/ln -sfn "$env_file" "$dms_log_dir/latest.env"
  ${pkgs.coreutils}/bin/ln -sfn "$log_file" "$dms_log_dir/latest.log"

  # Quickshell/DMS hangs before QML loading when Home Manager exports
  # `QT_QPA_PLATFORMTHEME=qt5ct`; keep the style override but drop the
  # platform theme for this session.
  unset QT_QPA_PLATFORMTHEME

  exec dms run --session >>"$log_file" 2>&1
''
