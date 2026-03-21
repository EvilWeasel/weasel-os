{
  config,
  lib,
  ...
}:

let
  cfg = config.features.displaylink;
  displaylinkUrl = "https://www.synaptics.com/sites/default/files/exe_files/2025-09/DisplayLink%20USB%20Graphics%20Software%20for%20Ubuntu6.2-EXE.zip";
  displaylinkHash = "sha256-JQO7eEz4pdoPkhcn9tIuy5R4KyfsCniuw6eXw/rLaYE=";
in
{
  options.features.displaylink = {
    enable = lib.mkEnableOption "DisplayLink dock support";
  };

  config = lib.mkIf cfg.enable {
    nixpkgs.overlays = [
      (final: prev: {
        displaylink = prev.displaylink.overrideAttrs (_: {
          src = final.fetchurl {
            name = "displaylink-620.zip";
            url = displaylinkUrl;
            hash = displaylinkHash;
          };
        });
      })
    ];

    services.xserver.videoDrivers = lib.mkBefore [ "displaylink" ];

    # The upstream NixOS displaylink module defines the service but does not
    # attach it to a target; enable it whenever DisplayLink support is requested.
    systemd.services.dlm.wantedBy = [ "multi-user.target" ];
  };
}
