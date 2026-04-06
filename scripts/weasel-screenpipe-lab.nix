{
  pkgs,
  screenpipeApp,
}:
pkgs.writeShellScriptBin "weasel-screenpipe-lab" ''
    set -euo pipefail

    if [ "$#" -lt 1 ]; then
      cat >&2 <<'EOF'
  usage: weasel-screenpipe-lab <gnome|wlr> [command...]

  Runs the given command in a private D-Bus session with an isolated portal stack.
  If no command is supplied, starts Screenpipe for 45 seconds.
  EOF
      exit 1
    fi

    backend="$1"
    shift || true

    case "$backend" in
      gnome|wlr) ;;
      *)
        echo "unsupported backend: $backend" >&2
        exit 1
        ;;
    esac

    lab_root="$HOME/.local/state/screenpipe-lab"
    timestamp="$(${pkgs.coreutils}/bin/date +%Y%m%d-%H%M%S)"
    workdir="$lab_root/$backend-$timestamp"
    config_root="$workdir/config"
    portal_conf_dir="$config_root/xdg/xdg-desktop-portal"
    log_dir="$workdir/logs"
    command_file="$workdir/command.sh"

    ${pkgs.coreutils}/bin/mkdir -p "$portal_conf_dir" "$log_dir"

    cat >"$portal_conf_dir/niri-portals.conf" <<EOF
  [preferred]
  default=gtk
  org.freedesktop.impl.portal.Access=gtk
  org.freedesktop.impl.portal.Notification=gtk
  org.freedesktop.impl.portal.ScreenCast=$backend
  org.freedesktop.impl.portal.Screenshot=$backend
  EOF

    if [ "$#" -gt 0 ]; then
      cmd=("$@")
    else
      cmd=("${pkgs.coreutils}/bin/timeout" "45s" "${screenpipeApp}/bin/screenpipe")
    fi

    {
      echo "#!${pkgs.bash}/bin/bash"
      echo "set -euo pipefail"
      printf 'exec'
      printf ' %q' "''${cmd[@]}"
      printf '\n'
    } >"$command_file"
    ${pkgs.coreutils}/bin/chmod +x "$command_file"

    echo "screenpipe-lab backend=$backend"
    echo "screenpipe-lab workdir=$workdir"
    echo "screenpipe-lab command=''${cmd[*]}"

    export WEASEL_SCREENPIPE_LAB_DIR="$workdir"

    ${pkgs.dbus}/bin/dbus-run-session -- ${pkgs.bash}/bin/bash -lc '
      set -euo pipefail

      workdir="$WEASEL_SCREENPIPE_LAB_DIR"
      backend="'"$backend"'"
      config_root="$workdir/config"
      log_dir="$workdir/logs"
      command_file="$workdir/command.sh"
      mkdir -p "$log_dir"

      export XDG_CURRENT_DESKTOP=niri
      export XDG_CONFIG_DIRS="$config_root/xdg:''${XDG_CONFIG_DIRS:-/etc/xdg}"
      export XDG_DATA_DIRS="${pkgs.xdg-desktop-portal}/share:${pkgs.xdg-desktop-portal-gtk}/share:${pkgs.xdg-desktop-portal-gnome}/share:${pkgs.xdg-desktop-portal-wlr}/share:''${XDG_DATA_DIRS:-/run/current-system/sw/share:/usr/share}"

      pids=()
      cleanup() {
        for pid in "''${pids[@]:-}"; do
          kill "$pid" >/dev/null 2>&1 || true
        done
        wait >/dev/null 2>&1 || true
      }
      trap cleanup EXIT

      ${pkgs.xdg-desktop-portal-gtk}/libexec/xdg-desktop-portal-gtk >"$log_dir/xdg-desktop-portal-gtk.log" 2>&1 &
      pids+=($!)

      case "$backend" in
        gnome)
          ${pkgs.xdg-desktop-portal-gnome}/libexec/xdg-desktop-portal-gnome >"$log_dir/xdg-desktop-portal-gnome.log" 2>&1 &
          portal_bus="org.freedesktop.impl.portal.desktop.gnome"
          ;;
        wlr)
          ${pkgs.xdg-desktop-portal-wlr}/libexec/xdg-desktop-portal-wlr >"$log_dir/xdg-desktop-portal-wlr.log" 2>&1 &
          portal_bus="org.freedesktop.impl.portal.desktop.wlr"
          ;;
      esac
      pids+=($!)

      ${pkgs.xdg-desktop-portal}/libexec/xdg-desktop-portal >"$log_dir/xdg-desktop-portal.log" 2>&1 &
      pids+=($!)

      ${pkgs.coreutils}/bin/sleep 2
      ${pkgs.glib}/bin/gdbus wait --session org.freedesktop.portal.Desktop >/dev/null
      ${pkgs.glib}/bin/gdbus wait --session "$portal_bus" >/dev/null

      "$command_file"
    '

    echo "screenpipe-lab logs:"
    ${pkgs.findutils}/bin/find "$log_dir" -maxdepth 1 -type f | ${pkgs.coreutils}/bin/sort
''
