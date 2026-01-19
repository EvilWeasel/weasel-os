{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.features.canbus;
in
{
  options.features.canbus = {
    enable = lib.mkEnableOption "CAN bus support (vcan + socketcan tooling)";
  };

  config = lib.mkIf cfg.enable {

    boot.kernelModules = [
      "can"
      "can_raw"
      "can_dev"
      "vcan"
    ];

    environment.systemPackages = with pkgs; [
      can-utils
    ];

    systemd.services.vcan0 = {
      description = "Virtual CAN interface vcan0";
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      script = ''
        ${pkgs.iproute2}/bin/ip link add dev vcan0 type vcan || true
        ${pkgs.iproute2}/bin/ip link set up vcan0
      '';
    };
  };
}
