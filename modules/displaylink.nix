{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.features.displaylink;
in
{
  options.features.displaylink = {
    enable = lib.mkEnableOption "DisplayLink dock support";
  };

  config = lib.mkIf cfg.enable {
    boot = {
      extraModulePackages = [ config.boot.kernelPackages.evdi ];
      initrd.kernelModules = [ "evdi" ];
    };

    environment.systemPackages = [ pkgs.displaylink ];

    # Keep the native GPU driver list intact and only prepend the DisplayLink driver.
    services.xserver.videoDrivers = lib.mkBefore [ "displaylink" ];

    systemd.services.dlm.wantedBy = [ "multi-user.target" ];
  };
}
