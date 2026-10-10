{ lib, pkgs, ... }:
let
  notifier = pkgs.writeShellApplication {
    name = "weasel-storage-notify";
    runtimeInputs = [
      pkgs.python3
      pkgs.libnotify
    ];
    text = "exec python3 ${../scripts/weasel-btrfs-health.py} notify";
  };
in
{
  systemd.user.services.weasel-storage-notify = {
    Unit.Description = "Notify on persistent Btrfs allocation pressure";
    Service = {
      Type = "oneshot";
      ExecStart = "${notifier}/bin/weasel-storage-notify";
    };
  };
  systemd.user.timers.weasel-storage-notify = {
    Unit.Description = "Check the current Btrfs health receipt";
    Timer = {
      OnStartupSec = "3min";
      OnUnitActiveSec = "5min";
    };
    Install.WantedBy = [ "timers.target" ];
  };
  # Keep the old files for recovery, but retire only the known obsolete timer.
  # The paused Factorio Companion source remains untouched.
  home.activation.retireLegacyStorageNotifier = lib.hm.dag.entryAfter [ "reloadSystemd" ] ''
    legacy="$HOME/.config/systemd/user/development-storage-watch.service"
    if [[ -f "$legacy" ]] && ${pkgs.gnugrep}/bin/grep -Fq \
      '/factorio-coop-agent-plan/tools/storage-maintenance.py" check --notify' "$legacy"; then
      $DRY_RUN_CMD ${pkgs.systemd}/bin/systemctl --user disable --now development-storage-watch.timer
    fi
  '';
}
