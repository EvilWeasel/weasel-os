{ lib, pkgs, ... }:
let
  retention = pkgs.writeShellApplication {
    name = "weasel-storage-retention";
    runtimeInputs = [
      pkgs.python3
      pkgs.snapper
      pkgs.nix
      pkgs.systemd
    ];
    text = ''exec python3 ${../scripts/weasel-storage-retention.py} "$@"'';
  };
  systemExport = pkgs.writeShellApplication {
    name = "weasel-system-state-export";
    runtimeInputs = [
      pkgs.python3
      pkgs.restic
      pkgs.util-linux
      pkgs.btrfs-progs
    ];
    text = ''
      exec python3 ${../scripts/weasel-backup-system.py} "$@" --restic ${pkgs.restic}/bin/restic
    '';
  };
in
{
  # Store GC never deletes build directories. Rooted project closures remain.
  # Preserve derivations of live outputs to retain incremental Nix build reuse.
  nix.settings.keep-derivations = true;
  nix.gc.automatic = lib.mkForce false;
  boot.loader.systemd-boot.configurationLimit = 5;
  environment.systemPackages = [
    retention
    systemExport
  ];
  systemd.services.weasel-storage-retention = {
    description = "Keep a small protected set of local recovery points";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${retention}/bin/weasel-storage-retention --apply";
      Nice = 19;
      IOSchedulingClass = "idle";
    };
  };
  systemd.timers.weasel-storage-retention = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnCalendar = "daily";
      Persistent = true;
      RandomizedDelaySec = "15m";
    };
  };
  systemd.services.weasel-system-state-export = {
    description = "Export mutable system state for encrypted Proton Drive backup";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${systemExport}/bin/weasel-system-state-export snapshot";
      UMask = "0077";
      Nice = 19;
      IOSchedulingClass = "idle";
    };
  };
  systemd.services.weasel-storage-gc = {
    description = "Bounded collection of unreferenced Nix store objects";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${retention}/bin/weasel-storage-retention --apply --gc";
      Nice = 19;
      IOSchedulingClass = "idle";
    };
  };
  systemd.timers.weasel-storage-gc = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnCalendar = "Sat *-*-* 12:00:00";
      Persistent = true;
      RandomizedDelaySec = "30m";
    };
  };
  systemd.timers.weasel-system-state-export = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnCalendar = "*-*-* 02:30:00";
      Persistent = true;
    };
  };
}
