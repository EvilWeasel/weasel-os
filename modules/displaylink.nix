{
  config,
  lib,
  ...
}:

let
  cfg = config.features.displaylink;
in
{
  options.features.displaylink = {
    enable = lib.mkEnableOption "DisplayLink dock support";
    proprietaryUserspace.enable = lib.mkEnableOption ''
      proprietary DisplayLink userspace support that requires the Synaptics
      driver archive to be prefetched locally to satisfy the DisplayLink EULA
    '';
  };

  config = lib.mkMerge [
    (lib.mkIf cfg.enable {
      boot = {
        extraModulePackages = [ config.boot.kernelPackages.evdi ];
        initrd.kernelModules = [ "evdi" ];
      };
    })

    (lib.mkIf cfg.proprietaryUserspace.enable {
      # Keep the native GPU driver list intact and only prepend the DisplayLink driver.
      services.xserver.videoDrivers = lib.mkBefore [ "displaylink" ];
      systemd.services.dlm.wantedBy = [ "multi-user.target" ];
    })
  ];
}
