{
  host,
  options,
  pkgs,
  ...
}: let
  inherit (import ../../hosts/${host}/variables.nix) consoleKeyMap;
in {
  home-manager.backupFileExtension = "hm-backup";

  networking = {
    hostName = host;
    timeServers = options.networking.timeServers.default ++ ["pool.ntp.org"];
  };

  time.timeZone = "Europe/Berlin";

  i18n = {
    defaultLocale = "en_US.UTF-8";
    extraLocaleSettings = {
      LC_ADDRESS = "de_DE.UTF-8";
      LC_IDENTIFICATION = "de_DE.UTF-8";
      LC_MEASUREMENT = "de_DE.UTF-8";
      LC_MONETARY = "de_DE.UTF-8";
      LC_NAME = "de_DE.UTF-8";
      LC_NUMERIC = "de_DE.UTF-8";
      LC_PAPER = "de_DE.UTF-8";
      LC_TELEPHONE = "de_DE.UTF-8";
      LC_TIME = "de_DE.UTF-8";
    };
  };

  environment.systemPackages = with pkgs; [
    bat
    curl
    eza
    fd
    git
    htop
    jq
    nh
    ripgrep
    tree
    vim
    wget
  ];

  services.fstrim.enable = true;

  nixpkgs.config.allowUnfree = true;

  nix = {
    settings = {
      auto-optimise-store = true;
      experimental-features = [
        "nix-command"
        "flakes"
      ];
      substituters = [
        "https://cache.nixos.org?priority=10"
        "https://nyx.chaotic.cx"
        "https://nix-community.cachix.org"
        "https://yazi.cachix.org"
      ];
      trusted-public-keys = [
        "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
        "yazi.cachix.org-1:Dcdz63NZKfvUCbDGngQDAZq6kOroIrFoyO064uvLh8k="
      ];
    };
    gc = {
      automatic = true;
      dates = "weekly";
      options = "--delete-older-than 7d";
    };
  };

  console.keyMap = consoleKeyMap;

  system.stateVersion = "24.11";
}
