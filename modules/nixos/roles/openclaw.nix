{
  config,
  inputs,
  lib,
  pkgs,
  ...
}: let
  cfg = config.weasel.roles.openclaw;
in {
  options.weasel.roles.openclaw = {
    enable = lib.mkEnableOption "OpenClaw server role";
    gatewayTokenFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = "Optional token file for the OpenClaw gateway scaffold.";
    };
    documents = lib.mkOption {
      type = lib.types.path;
      default = ../../../openclaw/documents;
      description = "Pinned OpenClaw documents directory.";
    };
  };

  config = lib.mkIf cfg.enable {
    users.groups.openclaw = {};
    users.users.openclaw = {
      isNormalUser = true;
      description = "OpenClaw service user";
      group = "openclaw";
      home = "/var/lib/openclaw";
      createHome = true;
      linger = true;
    };

    systemd.tmpfiles.rules = [
      "d /var/lib/openclaw 0750 openclaw openclaw -"
      "d /var/lib/openclaw/.openclaw 0750 openclaw openclaw -"
      "d /var/lib/openclaw/workspace 0750 openclaw openclaw -"
    ];

    home-manager.users.openclaw = {
      imports = [inputs.nix-openclaw.homeManagerModules.openclaw];

      home = {
        username = "openclaw";
        homeDirectory = "/var/lib/openclaw";
        stateVersion = "24.11";
      };

      programs.home-manager.enable = true;
      programs.openclaw = {
        enable = true;
        package = inputs.nix-openclaw.packages.${pkgs.stdenv.hostPlatform.system}.openclaw;
        documents = cfg.documents;
        installApp = false;
        systemd.enable = false;
        launchd.enable = false;
        stateDir = "/var/lib/openclaw/.openclaw";
        workspaceDir = "/var/lib/openclaw/workspace";
        config =
          {
            gateway.mode = "local";
          }
          // lib.optionalAttrs (cfg.gatewayTokenFile != null) {
            gateway.auth.tokenFile = cfg.gatewayTokenFile;
          };
      };
    };
  };
}
