{ pkgs, ... }:
let
  scripts = pkgs.linkFarm "weasel-storage-tools" [
    {
      name = "weasel-btrfs-health.py";
      path = ../scripts/weasel-btrfs-health.py;
    }
    {
      name = "weasel-snapshot-excludes.py";
      path = ../scripts/weasel-snapshot-excludes.py;
    }
  ];
  excludes = pkgs.writeShellApplication {
    name = "weasel-snapshot-excludes";
    runtimeInputs = [
      pkgs.python3
      pkgs.btrfs-progs
      pkgs.util-linux
      pkgs.coreutils
      pkgs.git
      pkgs.rsync
    ];
    text = ''exec python3 ${scripts}/weasel-snapshot-excludes.py "$@"'';
  };
  health = pkgs.writeShellApplication {
    name = "weasel-btrfs-health";
    runtimeInputs = [
      pkgs.python3
      pkgs.btrfs-progs
      pkgs.util-linux
    ];
    text = ''exec python3 ${../scripts/weasel-btrfs-health.py} "$@"'';
  };
in
{
  environment.systemPackages = [
    health
    excludes
  ];
  systemd.tmpfiles.rules = [
    "d /var/lib/weasel-storage-health 0700 root root -"
    "d /run/weasel-storage-health 0755 root root -"
  ];
  systemd.services.weasel-btrfs-health = {
    description = "Measure Btrfs allocation reserve and metadata commitments";
    unitConfig.RequiresMountsFor = "/home";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${health}/bin/weasel-btrfs-health record";
      Nice = 19;
      IOSchedulingClass = "idle";
      UMask = "0077";
    };
  };
  systemd.timers.weasel-btrfs-health = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "2min";
      OnUnitActiveSec = "15min";
    };
  };
  systemd.services.weasel-btrfs-reserve = {
    description = "Reclaim a bounded Btrfs data allocation reserve when idle";
    unitConfig.RequiresMountsFor = "/home";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${health}/bin/weasel-btrfs-health maintain";
      Nice = 19;
      IOSchedulingClass = "idle";
      UMask = "0077";
      # The helper bounds individual passes and cancels its own timed-out pass.
      TimeoutStartSec = "10min";
    };
  };
  systemd.timers.weasel-btrfs-reserve = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "10min";
      OnUnitActiveSec = "1h";
      RandomizedDelaySec = "5min";
    };
  };
}
