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

  # NetBird custom zones require a split-DNS-capable resolver.  openresolv
  # cannot represent match domains and currently fails to install NetBird's
  # DNS configuration, while systemd-resolved supports per-link routing.
  services.resolved.enable = true;

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

  # The hardened client already carries the network capabilities it needs,
  # but its unprivileged local DNS proxy must additionally bind port 53.
  systemd.services.netbird-personal.serviceConfig.AmbientCapabilities = lib.mkAfter [
    "CAP_NET_BIND_SERVICE"
  ];
}
