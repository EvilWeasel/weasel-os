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

  copy_if_exists() {
    local source="$1"

    if [ -e "$source" ]; then
      local target="$bundle_dir/$(${pkgs.coreutils}/bin/basename "$source")"
      ${pkgs.coreutils}/bin/cp -a "$source" "$target"
    fi
  }

  run_bash_capture "system-overview" \
    "${pkgs.coreutils}/bin/uname -a; echo; ${pkgs.nixos-rebuild}/bin/nixos-rebuild --version || true; echo; ${pkgs.nix}/bin/nix --version; echo; ${pkgs.inetutils}/bin/hostname"
  run_capture "systemctl-system-failed" ${pkgs.systemd}/bin/systemctl --failed
  run_capture "systemctl-user-failed" ${pkgs.systemd}/bin/systemctl --user --failed
  run_capture "systemctl-system-display-audio" ${pkgs.systemd}/bin/systemctl status greetd.service display-manager.service systemd-udevd.service dlm.service NetworkManager.service
  run_capture "loginctl-user-status" ${pkgs.systemd}/bin/loginctl user-status "$USER"
  run_capture "loginctl-list-sessions" ${pkgs.systemd}/bin/loginctl list-sessions
  run_capture "journal-user-boot" ${pkgs.systemd}/bin/journalctl --user -b --no-pager
  run_capture "journal-system-boot" ${pkgs.systemd}/bin/journalctl -b --no-pager
  run_capture "journal-kernel-boot" ${pkgs.systemd}/bin/journalctl -k -b --no-pager
  run_capture "journal-greetd-boot" ${pkgs.systemd}/bin/journalctl -u greetd -b --no-pager
  run_capture "journal-dlm-boot" ${pkgs.systemd}/bin/journalctl -u dlm -b --no-pager
  run_capture "journal-udevd-boot" ${pkgs.systemd}/bin/journalctl -u systemd-udevd -b --no-pager
  run_capture "systemctl-user-audio" ${pkgs.systemd}/bin/systemctl --user status pipewire.service pipewire-pulse.service wireplumber.service
  run_capture "journal-user-audio" ${pkgs.systemd}/bin/journalctl --user -b -u pipewire.service -u pipewire-pulse.service -u wireplumber.service --no-pager
  run_capture "lspci-nnk" ${pkgs.pciutils}/bin/lspci -nnk
  run_capture "lsusb" ${pkgs.usbutils}/bin/lsusb
  run_capture "lsusb-tree" ${pkgs.usbutils}/bin/lsusb -t
  run_capture "lsmod" ${pkgs.kmod}/bin/lsmod
  run_capture "ip-address" ${pkgs.iproute2}/bin/ip address
  run_capture "ip-route" ${pkgs.iproute2}/bin/ip route
  run_capture "findmnt" ${pkgs.util-linux}/bin/findmnt -R /
  run_capture "df-h" ${pkgs.coreutils}/bin/df -h
  run_capture "ps-tree" ${pkgs.procps}/bin/ps faux
  run_capture "env-sorted" ${pkgs.coreutils}/bin/env

  run_bash_capture "processes-interesting" \
    "${pkgs.procps}/bin/pgrep -af 'greetd|niri|dms|qs|quickshell|kitty|pipewire|wireplumber|pulse|DisplayLinkManager|Xorg|wayland' || true"
  run_bash_capture "journal-filtered" \
    "${pkgs.systemd}/bin/journalctl -b --no-pager | ${pkgs.ripgrep}/bin/rg -i 'greetd|niri|dms|quickshell|qt|wayland|nvidia|drm|gbm|egl|input|seat|pipewire|wireplumber|pulse|alsa|snd|sof|displaylink|evdi|udl|17e9|usb|thunderbolt' || true"
  run_bash_capture "coredumps-interesting" \
    "${pkgs.systemd}/bin/coredumpctl --no-pager list dms qs quickshell niri pipewire wireplumber pipewire-pulse DisplayLinkManager Xorg || true"
  run_bash_capture "nvidia-smi" \
    "command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi || echo 'nvidia-smi not available'"
  run_bash_capture "modinfo-displaylink" \
    "${pkgs.kmod}/bin/modinfo evdi || true; echo; ${pkgs.kmod}/bin/modinfo udl || true"
  run_bash_capture "displaylink-udev" \
    "${pkgs.systemd}/bin/udevadm info --export-db | ${pkgs.ripgrep}/bin/rg -i 'displaylink|17e9|evdi|udl|thunderbolt|usb' -C 2 || true"
  run_bash_capture "drm-connectors" \
    "for f in /sys/class/drm/*/status; do echo \"== $f ==\"; cat \"$f\"; echo; done"
  run_bash_capture "drm-tree" \
    "${pkgs.findutils}/bin/find /sys/class/drm -maxdepth 3 -mindepth 1 -print 2>/dev/null | ${pkgs.coreutils}/bin/sort || true"
  run_bash_capture "dev-dri" \
    "ls -l /dev/dri 2>/dev/null || echo '/dev/dri missing'"
  run_bash_capture "usb-tree-sysfs" \
    "${pkgs.findutils}/bin/find /sys/bus/usb/devices -maxdepth 2 -mindepth 1 -print 2>/dev/null | ${pkgs.coreutils}/bin/sort || true"
  run_bash_capture "thunderbolt-tree-sysfs" \
    "${pkgs.findutils}/bin/find /sys/bus/thunderbolt/devices -maxdepth 3 -mindepth 1 -print 2>/dev/null | ${pkgs.coreutils}/bin/sort || true"
  run_bash_capture "session-status" \
    "if [ -n \"''${XDG_SESSION_ID:-}\" ]; then ${pkgs.systemd}/bin/loginctl session-status \"$XDG_SESSION_ID\"; else echo 'XDG_SESSION_ID not set'; fi"
  run_bash_capture "niri-outputs" \
    "command -v niri >/dev/null 2>&1 && niri msg outputs || echo 'niri not available or no session'"
  run_bash_capture "niri-workspaces" \
    "command -v niri >/dev/null 2>&1 && niri msg workspaces || echo 'niri not available or no session'"
  run_bash_capture "xrandr-providers" \
    "command -v xrandr >/dev/null 2>&1 && xrandr --listproviders || echo 'xrandr not available'"
  run_bash_capture "xrandr-verbose" \
    "command -v xrandr >/dev/null 2>&1 && xrandr --verbose || echo 'xrandr not available'"
  run_bash_capture "wpctl-status" \
    "command -v wpctl >/dev/null 2>&1 && wpctl status || echo 'wpctl not available'"
  run_bash_capture "wpctl-default-sink" \
    "command -v wpctl >/dev/null 2>&1 && wpctl inspect @DEFAULT_AUDIO_SINK@ || echo 'wpctl not available'"
  run_bash_capture "wpctl-default-source" \
    "command -v wpctl >/dev/null 2>&1 && wpctl inspect @DEFAULT_AUDIO_SOURCE@ || echo 'wpctl not available'"
  run_bash_capture "pactl-info" \
    "command -v pactl >/dev/null 2>&1 && pactl info || echo 'pactl not available'"
  run_bash_capture "pactl-sinks" \
    "command -v pactl >/dev/null 2>&1 && pactl list short sinks || echo 'pactl not available'"
  run_bash_capture "pactl-sources" \
    "command -v pactl >/dev/null 2>&1 && pactl list short sources || echo 'pactl not available'"
  run_bash_capture "pactl-sink-inputs" \
    "command -v pactl >/dev/null 2>&1 && pactl list short sink-inputs || echo 'pactl not available'"
  run_bash_capture "alsa-devices" \
    "command -v aplay >/dev/null 2>&1 && aplay -l || echo 'aplay not available'; echo; command -v arecord >/dev/null 2>&1 && arecord -l || echo 'arecord not available'"
  run_bash_capture "snd-devnodes" \
    "ls -l /dev/snd 2>/dev/null || echo '/dev/snd missing'"
  run_bash_capture "state-tree" \
    "${pkgs.findutils}/bin/find '$debug_state' -maxdepth 3 -mindepth 1 -print 2>/dev/null || true"

  for source in \
    "$debug_state" \
    "$HOME/.config/niri" \
    "$HOME/.local/state/niri" \
    "$HOME/.config/DankMaterialShell" \
    "$HOME/.local/state/DankMaterialShell" \
    "$HOME/.cache/DankMaterialShell" \
    "$HOME/.config/pipewire" \
    "$HOME/.local/state/pipewire" \
    "$HOME/.config/wireplumber" \
    "$HOME/.local/state/wireplumber" \
    "$HOME/.config/pulse"
  do
    copy_if_exists "$source"
  done

  cat >"$bundle_dir/README.txt" <<EOF
  Host: $host
  Created: $timestamp

  Share this entire folder if a boot/session attempt fails.
  Important files:
  - system-overview.txt
  - journal-kernel-boot.txt
  - journal-filtered.txt
  - journal-user-boot.txt
  - journal-user-audio.txt
  - journal-greetd-boot.txt
  - journal-dlm-boot.txt
  - systemctl-system-display-audio.txt
  - processes-interesting.txt
  - coredumps-interesting.txt
  - drm-connectors.txt
  - niri-outputs.txt
  - xrandr-providers.txt
  - lsusb-tree.txt
  - displaylink-udev.txt
  - systemctl-user-audio.txt
  - wpctl-status.txt
  - pactl-info.txt
  EOF

  printf '%s\n' "$bundle_dir"
''
