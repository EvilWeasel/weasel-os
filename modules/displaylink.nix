{
  config,
  lib,
  ...
}:

let
  cfg = config.features.displaylink;
  displaylinkUrl = "https://www.synaptics.com/sites/default/files/exe_files/2026-10/DisplayLink%20USB%20Graphics%20Software%20for%20Ubuntu6.4-EXE.zip";
  displaylinkHash = "sha256-fhqB0hlKQLIN5wTLOEbWbL+x54N+MN4jRVcpuhTwKW0=";
in
{
  options.features.displaylink = {
    enable = lib.mkEnableOption "DisplayLink dock support";
  };

  config = lib.mkIf cfg.enable {
    nixpkgs.overlays = [
      (final: prev: {
        displaylink = prev.displaylink.overrideAttrs (_: {
          version = "6.4.0-22";
          src = final.fetchurl {
            name = "displaylink-640.zip";
            url = displaylinkUrl;
            hash = displaylinkHash;
          };
          unpackPhase = ''
            runHook preUnpack
            unzip -j "$src"
            chmod +x displaylink-driver-6.4.0-22.run
            ./displaylink-driver-6.4.0-22.run --target . --noexec --nodiskspace
            runHook postUnpack
          '';
        });
      })
    ];

    services.xserver.videoDrivers = lib.mkBefore [ "displaylink" ];

    # The upstream NixOS displaylink module defines the service but does not
    # attach it to a target; enable it whenever DisplayLink support is requested.
    systemd.services.dlm.wantedBy = [ "multi-user.target" ];
    # Preserve the running dock until the user chooses its next restart/replug.
    systemd.services.dlm.restartIfChanged = false;
  };
}
