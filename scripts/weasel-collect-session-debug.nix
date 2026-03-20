{pkgs}:
pkgs.writeShellScriptBin "weasel-collect-session-debug" ''
  set -euo pipefail

  host="''${WEASEL_OS_HOST:-$(${pkgs.inetutils}/bin/hostname)}"
  debug_home="''${WEASEL_DEBUG_HOME:-$HOME/weasel-debug}"
  debug_state="''${WEASEL_DEBUG_STATE:-''${XDG_STATE_HOME:-$HOME/.local/state}/weasel-debug}"
  timestamp="$(${pkgs.coreutils}/bin/date +%Y%m%d-%H%M%S)"
  bundle_dir="$debug_home/''${host}-''${timestamp}"

  ${pkgs.coreutils}/bin/mkdir -p "$bundle_dir"

  run_capture() {
    local name="$1"
    shift
    {
      printf '$'
      printf ' %q' "$@"
      printf '\n\n'
      "$@"
    } >"$bundle_dir/$name.txt" 2>&1 || true
  }

  run_bash_capture() {
    local name="$1"
    shift
    {
      printf '$ %s\n\n' "$*"
      ${pkgs.bash}/bin/bash -lc "$*"
    } >"$bundle_dir/$name.txt" 2>&1 || true
  }

  run_capture "systemctl-user-failed" ${pkgs.systemd}/bin/systemctl --user --failed
  run_capture "loginctl-user-status" ${pkgs.systemd}/bin/loginctl user-status "$USER"
  run_capture "journal-user-boot" ${pkgs.systemd}/bin/journalctl --user -b --no-pager
  run_capture "journal-greetd-boot" ${pkgs.systemd}/bin/journalctl -u greetd -b --no-pager
  run_capture "lspci-k" ${pkgs.pciutils}/bin/lspci -k
  run_capture "ps-tree" ${pkgs.procps}/bin/ps faux
  run_capture "env-sorted" ${pkgs.coreutils}/bin/env

  run_bash_capture "processes-interesting" \
    "${pkgs.procps}/bin/pgrep -af 'greetd|niri|dms|qs|quickshell|kitty' || true"
  run_bash_capture "journal-filtered" \
    "${pkgs.systemd}/bin/journalctl -b --no-pager | ${pkgs.ripgrep}/bin/rg -i 'greetd|niri|dms|quickshell|qt|wayland|nvidia|drm|gbm|egl|input|seat' || true"
  run_bash_capture "coredumps-interesting" \
    "${pkgs.systemd}/bin/coredumpctl --no-pager list dms qs quickshell niri || true"
  run_bash_capture "nvidia-smi" \
    "command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi || echo 'nvidia-smi not available'"
  run_bash_capture "state-tree" \
    "${pkgs.findutils}/bin/find '$debug_state' -maxdepth 3 -mindepth 1 -print 2>/dev/null || true"

  for source in \
    "$debug_state" \
    "$HOME/.config/niri" \
    "$HOME/.config/DankMaterialShell" \
    "$HOME/.local/state/DankMaterialShell" \
    "$HOME/.cache/DankMaterialShell"
  do
    if [ -e "$source" ]; then
      target="$bundle_dir/$(${pkgs.coreutils}/bin/basename "$source")"
      ${pkgs.coreutils}/bin/cp -a "$source" "$target"
    fi
  done

  cat >"$bundle_dir/README.txt" <<EOF
  Host: $host
  Created: $timestamp

  Share this entire folder if a boot/session attempt fails.
  Important files:
  - journal-filtered.txt
  - journal-user-boot.txt
  - journal-greetd-boot.txt
  - processes-interesting.txt
  - coredumps-interesting.txt
  EOF

  printf '%s\n' "$bundle_dir"
''
