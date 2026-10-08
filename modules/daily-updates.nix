{ config, pkgs, ... }:
let
  runfiles = pkgs.runCommand "weasel-update-runfiles" { } ''
    mkdir -p "$out"
    cp ${../scripts/weasel-update-prepare.py} "$out/weasel-update-prepare.py"
    cp ${../scripts/weasel-update-discover.py} "$out/weasel-update-discover.py"
    cp ${../scripts/weasel-update-gates.py} "$out/weasel-update-gates.py"
    cp ${../scripts/weasel-update-activate.py} "$out/weasel-update-activate.py"
    cp ${../scripts/weasel-update-bootstrap.py} "$out/weasel-update-bootstrap.py"
    cp ${../config/update-pins.json} "$out/update-pins.json"
  '';
  runtimeInputs = [
    config.nix.package
    pkgs.git
    pkgs.gh
    pkgs.python3
    pkgs.bash
    pkgs.gnupg
    pkgs.coreutils
    pkgs.util-linux
    pkgs.iproute2
    pkgs.glibc.bin
    pkgs.systemd
    pkgs.snapper
    pkgs.btrfs-progs
    pkgs.bubblewrap
    pkgs.libnotify
    pkgs.xorg.xorgserver
    (pkgs.nodejs_24 or pkgs.nodejs)
  ];
  prepare = pkgs.writeShellApplication {
    name = "weasel-update";
    inherit runtimeInputs;
    text = ''
      exec ${pkgs.python3}/bin/python3 ${runfiles}/weasel-update-prepare.py "$@"
    '';
  };
  activate = pkgs.writeShellApplication {
    name = "weasel-update-activate";
    inherit runtimeInputs;
    text = ''
      exec ${pkgs.python3}/bin/python3 ${runfiles}/weasel-update-activate.py "$@"
    '';
  };
  bootstrap = pkgs.writeShellApplication {
    name = "weasel-update-bootstrap";
    inherit runtimeInputs;
    text = ''
      exec ${pkgs.python3}/bin/python3 ${runfiles}/weasel-update-bootstrap.py "$@"
    '';
  };
in
{
  environment.systemPackages = [
    prepare
    bootstrap
  ];

  # Only the inbox is writable by the model's ordinary user. Sources, durable
  # journals, rollback roots and displaced originals have root-owned parents.
  systemd.tmpfiles.rules = [
    "d /var/lib/weasel-updates-inbox 0700 evilweasel users -"
    "d /var/lib/weasel-updates 0711 root root -"
    "d /var/lib/weasel-updates/runs 0700 root root -"
    "d /var/lib/weasel-updates/requests 0700 root root -"
    "d /var/lib/weasel-updates/sources 0711 root root -"
    "d /var/lib/weasel-updates/workers 0711 root root -"
    "d /var/lib/weasel-updates-status 0755 root root -"
    "d /home/.weasel-update-transactions 0700 root root -"
  ];

  systemd.services.weasel-update-activate = {
    description = "Independently verify, snapshot and activate signed laptop updates";
    wants = [ "network-online.target" ];
    after = [
      "network-online.target"
      "systemd-tmpfiles-setup.service"
    ];
    requires = [ "systemd-tmpfiles-setup.service" ];
    restartIfChanged = false;
    unitConfig = {
      X-StopOnRemoval = false;
      RequiresMountsFor = [
        "/home"
        "/nix/store"
        "/var/lib/weasel-updates"
      ];
      StartLimitIntervalSec = "5min";
      StartLimitBurst = 3;
    };
    serviceConfig = {
      Type = "oneshot";
      User = "root";
      UMask = "0077";
      ExecStart = "${activate}/bin/weasel-update-activate";
      TimeoutStartSec = "3h";
      TimeoutStopSec = "2min";
      Nice = 10;
      IOSchedulingClass = "idle";
    };
  };

  # A fixed path dispatches a schema-checked request, never a caller command.
  # The activator consumes it before processing and serializes with flock.
  systemd.paths.weasel-update-activate = {
    description = "Watch the narrowly scoped laptop update inbox";
    wantedBy = [ "multi-user.target" ];
    after = [ "systemd-tmpfiles-setup.service" ];
    pathConfig = {
      PathExists = "/var/lib/weasel-updates-inbox/request.json";
      Unit = "weasel-update-activate.service";
    };
  };

  home-manager.users.evilweasel.home.file.".codex/rules/weasel-updates.rules".source =
    ../programs/weasel-updates.rules;
}
