{
  config,
  lib,
  pkgs,
  ...
}:
{
  imports = [
    ../../profiles/system/common.nix
    ../../profiles/system/base.nix
    ../../profiles/system/client.nix
    ../../profiles/system/laptop.nix
    ../../modules/wispr-flow.nix
    # ../../modules/networking/internal-dns.nix
    ./hardware.nix
    ./users.nix
  ];

  hardware.nvidia.package = lib.mkForce config.boot.kernelPackages.nvidiaPackages.production;

  weasel.wispr-flow.enable = true;

  services.netbird = {
    package = pkgs.callPackage ../../packages/netbird-bin.nix { };
    ui.package = pkgs.callPackage ../../packages/netbird-ui-bin.nix {
      daemonSocket = "/var/run/netbird-personal/sock";
    };
    useRoutingFeatures = "none";
    ui.enable = true;
    clients.personal = {
      name = "personal";
      interface = "nb-personal";
      port = 51821;
      hardened = true;
      autoStart = true;
      ui.enable = true;
      environment = {
        NB_MANAGEMENT_URL = "https://netbird.evilweasel.cloud";
        NB_ADMIN_URL = "https://netbird.evilweasel.cloud";
      };
      openFirewall = true;
      openInternalFirewall = true;
    };
  };

  users.users.evilweasel.extraGroups = [ "netbird-personal" ];
}
