{
  config,
  lib,
  pkgs,
  ...
}:
let
  netbirdTailscaleCgnatCompat = pkgs.writeShellApplication {
    name = "netbird-tailscale-cgnat-compat";
    runtimeInputs = with pkgs; [
      coreutils
      gnugrep
      nftables
    ];
    text = builtins.readFile ../../scripts/netbird-tailscale-cgnat-compat.sh;
  };
in
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

  # Tailscale's ts-input anti-spoof chain treats NetBird's 100.96.0.0/16
  # address space as part of its own CGNAT range and otherwise drops replies
  # arriving on nb-personal. Reinstall this narrow exception after every
  # tailscaled start; NetBird policy remains the authorization boundary.
  systemd.services.netbird-tailscale-cgnat-compat = {
    description = "Allow personal NetBird CGNAT before Tailscale anti-spoofing";
    after = [
      "network-online.target"
      "netbird-personal.service"
      "tailscaled.service"
    ];
    wants = [
      "network-online.target"
      "netbird-personal.service"
    ];
    partOf = [ "tailscaled.service" ];
    wantedBy = [
      "multi-user.target"
      "tailscaled.service"
    ];
    unitConfig = {
      StartLimitIntervalSec = "10min";
      StartLimitBurst = 12;
    };
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      Restart = "on-failure";
      RestartSec = "5s";
      ExecStart = lib.getExe netbirdTailscaleCgnatCompat;
    };
  };

  users.users.evilweasel.extraGroups = [ "netbird-personal" ];

  # Only the RPM payload is installed. Its scriptlets would otherwise add an
  # imperative OpenAI DNF repository and updater outside the flake.
  environment.systemPackages = [
    (pkgs.callPackage ../../packages/chatgpt/default.nix { })
  ];
}
