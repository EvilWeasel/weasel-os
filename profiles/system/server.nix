{
  inputs,
  lib,
  pkgs,
  ...
}: {
  imports = [
    inputs.sops-nix.nixosModules.sops
  ];

  boot = {
    tmp.useTmpfs = false;
  };

  networking = {
    useDHCP = lib.mkDefault true;
    useNetworkd = true;
    nftables.enable = true;
    firewall = {
      enable = true;
      allowPing = false;
      trustedInterfaces = ["tailscale0"];
      interfaces.tailscale0.allowedTCPPorts = [22];
    };
  };

  services = {
    resolved.enable = true;
    openssh = {
      enable = true;
      openFirewall = false;
      settings = {
        PasswordAuthentication = false;
        KbdInteractiveAuthentication = false;
        PermitRootLogin = "no";
        X11Forwarding = false;
      };
    };
    tailscale = {
      enable = true;
      extraSetFlags = ["--ssh"];
    };
  };

  sops.age.keyFile = "/var/lib/sops-nix/keys.txt";

  environment.systemPackages = with pkgs; [
    btop
    fastfetch
    neovim
    tmux
    yazi
  ];

  users.mutableUsers = false;

  security.sudo.wheelNeedsPassword = false;

  programs = {
    mtr.enable = true;
    nix-ld.enable = false;
  };

  systemd.network.wait-online.enable = lib.mkDefault false;
  systemd.services.NetworkManager-wait-online.enable = false;

  virtualisation = {
    docker.enable = false;
    libvirtd.enable = false;
  };

  zramSwap.enable = true;
}
