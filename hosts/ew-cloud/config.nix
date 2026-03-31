{
  config,
  inputs,
  lib,
  ...
}: let
  secretFile = ../../secrets/hosts/ew-cloud/secrets.yaml;
  hasSecrets = builtins.pathExists secretFile;
in {
  imports = [
    ../../profiles/system/common.nix
    ../../profiles/system/server.nix
    inputs.disko.nixosModules.disko
    ../../modules/nixos/roles/openclaw.nix
    ./hardware.nix
    ./disko.nix
    ./users.nix
  ];

  weasel.roles.openclaw.enable = true;

  boot.loader.systemd-boot.configurationLimit = 10;

  sops = lib.mkIf hasSecrets {
    defaultSopsFile = secretFile;
    validateSopsFiles = false;
    secrets = {
      tailscale-auth-key = {
        key = "tailscale.auth_key";
        owner = "root";
        mode = "0400";
        restartUnits = [
          "tailscaled-autoconnect.service"
          "tailscaled-set.service"
        ];
      };
      openclaw-gateway-token = {
        key = "openclaw.gateway_token";
        owner = "openclaw";
        group = "openclaw";
        mode = "0400";
      };
    };
  };

  services.tailscale = lib.mkIf hasSecrets {
    authKeyFile = config.sops.secrets.tailscale-auth-key.path;
  };

  weasel.roles.openclaw.gatewayTokenFile = lib.mkIf hasSecrets config.sops.secrets.openclaw-gateway-token.path;
}
