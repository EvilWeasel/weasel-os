{ pkgs, ... }:
{
  # Bootstrap installs this exact task-owned unit before the next OS switch.
  xdg.configFile."systemd/user/proton-mail-bridge.service".force = true;

  systemd.user.services.proton-mail-bridge = {
    Unit = {
      Description = "Proton Mail Bridge for local mail clients";
      After = [ "dbus.socket" ];
      Wants = [ "dbus.socket" ];
    };
    Service = {
      Type = "simple";
      ExecStart = "${pkgs.protonmail-bridge-gui}/lib/bridge --noninteractive";
      Environment = [
        "XDG_RUNTIME_DIR=%t"
        "DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus"
      ];
      UMask = "0077";
      NoNewPrivileges = true;
      Restart = "on-failure";
      RestartSec = 15;
    };
    Install.WantedBy = [ "default.target" ];
  };
}
