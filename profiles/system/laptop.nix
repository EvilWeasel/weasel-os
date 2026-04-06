{
  config,
  host,
  pkgs,
  pkgsUnstable,
  inputs,
  lib,
  username,
  ...
}: {
  features.canbus.enable = true;
  features.displaylink.enable = true;
  services.xserver.videoDrivers = lib.mkIf (host == "nixy-laptop") [ "nvidia" ];

  xdg.portal = {
    enable = true;
    xdgOpenUsePortal = true;
    extraPortals = with pkgs; [
      xdg-desktop-portal-gnome
      xdg-desktop-portal-gtk
    ];
    config.niri = {
      default = [
        "gnome"
        "gtk"
      ];
      "org.freedesktop.impl.portal.Access" = [ "gtk" ];
      "org.freedesktop.impl.portal.Notification" = [ "gtk" ];
      "org.freedesktop.impl.portal.ScreenCast" = [ "gnome" ];
      "org.freedesktop.impl.portal.Screenshot" = [ "gnome" ];
      "org.freedesktop.impl.portal.Secret" = [ "gnome-keyring" ];
    };
  };

  local.hardware-clock.enable = true;

  networking = {
    networkmanager.wifi.backend = lib.mkForce "iwd";
    wireless.iwd.enable = lib.mkForce true;
  };

  programs = {
    gnupg.agent.enableSSHSupport = false;
    steam.gamescopeSession.enable = false;
    ssh = {
      startAgent = true;
      extraConfig = ''
        Host *
          AddKeysToAgent yes
      '';
    };
  };

  environment.systemPackages =
    (with pkgs; [
      bubblewrap
      claude-code
      openssl
      proton-pass
      azuredatastudio
      teams-for-linux
      slack
      protonmail-desktop
      python3
      python3Packages.pip
      snapper
      btrfs-progs
      nil
      xwayland-satellite
      cava
      cliphist
      helix
      lsfg-vk
      lsfg-vk-ui
      superTuxKart
      prismlauncher
      ftb-app
      firefox
      ventoy-full-qt
      antigravity-fhs
      obs-studio
      kontroll
      protontricks
      mangojuice
      spice
      spice-gtk
      spice-protocol
      virtio-win
      win-spice
    ])
    ++ [
      pkgsUnstable.nodejs
      pkgsUnstable.dgop
      pkgsUnstable.dsearch
      inputs.helium.packages.${pkgs.stdenv.hostPlatform.system}.default
      inputs.self.packages.${pkgs.stdenv.hostPlatform.system}.t3code
      inputs.handy.packages.${pkgs.stdenv.hostPlatform.system}.handy
    ];

  services = {
    snapper = {
      snapshotInterval = "daily";
      cleanupInterval = "daily";

      configs.home = {
        SUBVOLUME = "/home";
        TIMELINE_CREATE = true;
        TIMELINE_CLEANUP = true;
        TIMELINE_LIMIT_DAILY = 7;
        TIMELINE_LIMIT_WEEKLY = 0;
        TIMELINE_LIMIT_MONTHLY = 0;
        TIMELINE_LIMIT_YEARLY = 0;
        SPACE_LIMIT = "0.3";
      };
    };
    tlp.enable = false;
    power-profiles-daemon.enable = true;
    upower.enable = true;
    gnome.gcr-ssh-agent.enable = false;
    blueman.enable = true;
  };

  hardware = {
    sane = {
      enable = true;
      extraBackends = [pkgs.sane-airscan];
      disabledDefaultBackends = ["escl"];
    };
    bluetooth = {
      enable = true;
      powerOnBoot = true;
    };
  };

  services.udev = {
    packages = [pkgs.sane-airscan];
    extraRules = ''
      ATTRS{name}=="Sony Interactive Entertainment DualSense Wireless Controller Touchpad", ENV{LIBINPUT_IGNORE_DEVICE}="1"
      ATTRS{name}=="DualSense Wireless Controller Touchpad", ENV{LIBINPUT_IGNORE_DEVICE}="1"
    '';
  };

  virtualisation = {
    libvirtd.qemu.package = pkgs.qemu_kvm;
    spiceUSBRedirection.enable = true;
  };

  boot.kernel.sysctl = {
    "net.bridge.bridge-nf-call-iptables" = 0;
    "net.bridge.bridge-nf-call-ip6tables" = 0;
    "net.bridge.bridge-nf-call-arptables" = 0;
  };
}
