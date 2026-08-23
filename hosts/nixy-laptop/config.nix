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

  # NetBird's hardened per-client daemon integrates DNS through systemd-resolved.
  # This avoids an unprivileged daemon mutating openresolv state and lets the
  # module's scoped polkit rule authorize only NetBird's resolved operations.
  services.resolved.enable = true;

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
      # The managed DNS zone uses this loopback listener. Declaring it makes
      # the upstream NixOS module grant only CAP_NET_BIND_SERVICE in addition
      # to the existing WireGuard capabilities.
      dns-resolver.address = "127.0.0.153";
      port = 51821;
      dns-resolver = {
        address = "127.0.0.153";
        port = 53;
      };
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
