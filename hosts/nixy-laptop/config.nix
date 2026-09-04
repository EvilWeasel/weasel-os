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

  # The AX211 can enumerate on PCI without iwlwifi being auto-loaded on some boots.
  # Request the in-kernel driver explicitly before NetworkManager starts.
  boot.kernelModules = [ "iwlwifi" ];

  # NetBird's hardened per-client daemon integrates DNS through systemd-resolved.
  # This avoids an unprivileged daemon mutating openresolv state and lets the
  # module's scoped polkit rule authorize only NetBird's resolved operations.
  services.resolved.enable = true;

  # NetBird is the laptop's sole overlay. Other hosts may still enable the
  # shared profile's Tailscale service independently.
  services.tailscale.enable = lib.mkForce false;

  weasel.wispr-flow.enable = true;

  services.netbird = {
    package = pkgs.callPackage ../../packages/netbird-bin.nix { };
    ui.package = pkgs.callPackage ../../packages/netbird-ui-bin.nix {
      daemonSocket = "unix:///var/run/netbird-personal/sock";
    };
    useRoutingFeatures = "none";
    ui.enable = true;
    clients.personal = {
      name = "personal";
      interface = "nb-personal";
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

  # Only the RPM payload is installed. Its scriptlets would otherwise add an
  # imperative OpenAI DNF repository and updater outside the flake.
  environment.systemPackages = [
    (pkgs.callPackage ../../packages/chatgpt/default.nix { })
  ];
}
