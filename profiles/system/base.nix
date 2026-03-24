{
  config,
  pkgs,
  host,
  lib,
  options,
  username,
  inputs,
  ...
}: let
  inherit (import ../../hosts/${host}/variables.nix) consoleKeyMap keyboardLayout;
  commonSystemPackages = with pkgs; [
    protonvpn-gui
    warp-terminal
    code-cursor
    bun
    libreoffice-qt
    hunspell
    hunspellDicts.en_US
    hunspellDicts.de_DE
    dotnetCorePackages.dotnet_9.sdk
    dotnetCorePackages.dotnet_9.runtime
    dotnetCorePackages.dotnet_9.aspnetcore
    virtiofsd
    remmina
    thunderbird
    ouch
    razergenie
    wineWowPackages.staging
    winetricks
    sl
    dxvk_2
    vkd3d-proton
    keymapp
    wally-cli
    alarm-clock-applet
    alacritty
    google-chrome
    zellij
    yazi
    fd
    fzf
    ripgrep
    zoxide
    imagemagick
    poppler
    jq
    p7zip-rar
    ffmpeg
    bottles
    lutris
    heroic
    protonup-ng
    mangohud
    qbittorrent
    meld
    obsidian
    vesktop
    vim
    bubblewrap
    wget
    killall
    docker-compose
    eza
    git
    cmatrix
    lolcat
    htop
    libvirt
    lxqt.lxqt-policykit
    lm_sensors
    unzip
    unrar
    libnotify
    v4l-utils
    ydotool
    duf
    ncdu
    wl-clipboard
    pciutils
    socat
    cowsay
    lshw
    bat
    pkg-config
    meson
    ninja
    brightnessctl
    virt-viewer
    swappy
    appimage-run
    networkmanagerapplet
    yad
    inxi
    playerctl
    nh
    nixfmt-rfc-style
    swww
    matugen
    grim
    slurp
    file-roller
    swaynotificationcenter
    imv
    mpv
    gimp
    pavucontrol
    tree
    spotify
    neovide
    tuigreet
  ];
in {
  imports = [
    inputs.dms.nixosModules.greeter
    ../../modules/canbus.nix
    ../../modules/displaylink.nix
    ../../modules/overrides/linux-zen-preempt-fix.nix
    ../../modules/amd-drivers.nix
    ../../modules/nvidia-drivers.nix
    ../../modules/nvidia-prime-drivers.nix
    ../../modules/intel-drivers.nix
    ../../modules/vm-guest-services.nix
    ../../modules/local-hardware-clock.nix
  ];

  # Keep existing hand-managed Home Manager config files as backups during
  # activation instead of aborting the switch.
  home-manager.backupFileExtension = "hm-backup";

  boot = {
    kernelModules = ["v4l2loopback"];
    extraModulePackages = [config.boot.kernelPackages.v4l2loopback];
    extraModprobeConfig = ''
      options v4l2loopback devices=1 video_nr=1 card_label="OBS Cam" exclusive_caps=1
    '';
    kernel.sysctl = {
      "vm.max_map_count" = 2147483642;
    };
    loader.systemd-boot.enable = true;
    loader.efi.canTouchEfiVariables = true;
    tmp = {
      useTmpfs = false;
      tmpfsSize = "30%";
    };
    binfmt.registrations.appimage = {
      wrapInterpreterInShell = false;
      interpreter = "${pkgs.appimage-run}/bin/appimage-run";
      recognitionType = "magic";
      offset = 0;
      mask = ''\xff\xff\xff\xff\x00\x00\x00\x00\xff\xff\xff'';
      magicOrExtension = ''\x7fELF....AI\x02'';
    };
    plymouth.enable = true;
  };

  vm.guest-services.enable = false;

  networking = {
    hostName = host;
    networkmanager.enable = true;
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

  programs = {
    "dank-material-shell".greeter = {
      enable = true;
      compositor.name = "niri";
      configHome = "/home/${username}";
      configFiles = [
        "/home/${username}/.config/DankMaterialShell/settings.json"
        "/home/${username}/.local/state/DankMaterialShell/session.json"
      ];
      logs = {
        save = true;
        path = "/tmp/dms-greeter-${host}.log";
      };
    };
    nix-ld = {
      enable = true;
      libraries = with pkgs; [
        libcap
        xz
        openssl
        zlib
      ];
    };
    xwayland.enable = true;
    gamescope = {
      enable = true;
      capSysNice = false;
    };
    gamemode = {
      enable = true;
      enableRenice = true;
    };
    niri.enable = true;
    firefox.enable = false;
    starship = {
      enable = true;
      settings = {
        add_newline = false;
        buf.symbol = " ";
        c.symbol = " ";
        directory.read_only = " 󰌾";
        docker_context.symbol = " ";
        fossil_branch.symbol = " ";
        git_branch.symbol = " ";
        golang.symbol = " ";
        hg_branch.symbol = " ";
        hostname.ssh_symbol = " ";
        lua.symbol = " ";
        memory_usage.symbol = "󰍛 ";
        meson.symbol = "󰔷 ";
        nim.symbol = "󰆥 ";
        nix_shell.symbol = " ";
        nodejs.symbol = " ";
        ocaml.symbol = " ";
        package.symbol = "󰏗 ";
        python.symbol = " ";
        rust.symbol = " ";
        swift.symbol = " ";
        zig.symbol = " ";
      };
    };
    dconf.enable = true;
    seahorse.enable = true;
    fuse.userAllowOther = true;
    mtr.enable = true;
    gnupg.agent.enable = true;
    virt-manager.enable = true;
    steam = {
      enable = true;
      remotePlay.openFirewall = true;
    };
    thunar = {
      enable = true;
      plugins = with pkgs.xfce; [
        thunar-archive-plugin
        thunar-volman
      ];
    };
    obs-studio = {
      enable = true;
      package = pkgs.obs-studio.override {
        cudaSupport = true;
      };
    };
  };

  nixpkgs = {
    config = {
      allowUnfree = true;
      permittedInsecurePackages = [
        "ventoy-qt5-${pkgs.ventoy-full-qt.version}"
        "qtwebengine-5.15.19"
      ];
    };
  };

  users.mutableUsers = true;

  environment = {
    systemPackages = commonSystemPackages;
    variables = {
      STEAM_EXTRA_COMPAT_TOOLS_PATHS = "/home/${username}/.steam/root/compatibilitytools.d";
    };
    sessionVariables = {
      DOTNET_ROOT = "${pkgs.dotnetCorePackages.dotnet_9.sdk}";
    };
  };

  fonts = {
    packages = with pkgs; [
      noto-fonts-color-emoji
      noto-fonts-cjk-sans
      font-awesome
      symbola
    material-icons
    monaspace
    nerd-fonts.monaspace
    adwaita-qt
    adwaita-qt6
  ];
    enableDefaultPackages = true;
    fontconfig = {
      enable = true;
      cache32Bit = true;
    };
  };

  services = {
    xserver = {
      enable = false;
      xkb = {
        layout = keyboardLayout;
        variant = "";
      };
    };
    smartd = {
      enable = false;
      autodetect = true;
    };
    libinput.enable = true;
    fstrim.enable = true;
    gvfs.enable = true;
    openssh.enable = true;
    flatpak.enable = true;
    printing.enable = true;
    gnome.gnome-keyring.enable = true;
    avahi = {
      enable = true;
      nssmdns4 = true;
      openFirewall = true;
    };
    ipp-usb.enable = true;
    syncthing = {
      enable = false;
      user = username;
      dataDir = "/home/${username}";
      configDir = "/home/${username}/.config/syncthing";
    };
    pipewire = {
      enable = true;
      alsa.enable = true;
      alsa.support32Bit = true;
      pulse.enable = true;
    };
    rpcbind.enable = false;
    nfs.server.enable = false;
    pulseaudio.enable = false;
  };

  systemd.services.greetd = {
    after = ["systemd-udev-settle.service"];
    wants = ["systemd-udev-settle.service"];
  };
  systemd.services.flatpak-repo = {
    path = [pkgs.flatpak];
    script = ''
      flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
    '';
  };

  hardware = {
    keyboard.zsa.enable = true;
    logitech.wireless.enable = true;
    logitech.wireless.enableGraphical = true;
    graphics = {
      enable = true;
      enable32Bit = true;
    };
  };

  security = {
    rtkit.enable = true;
    polkit = {
      enable = true;
      extraConfig = ''
        polkit.addRule(function(action, subject) {
          if (
            subject.isInGroup("users")
              && (
                action.id == "org.freedesktop.login1.reboot" ||
                action.id == "org.freedesktop.login1.reboot-multiple-sessions" ||
                action.id == "org.freedesktop.login1.power-off" ||
                action.id == "org.freedesktop.login1.power-off-multiple-sessions"
              )
            )
          {
            return polkit.Result.YES;
          }
        })
      '';
    };
  };

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

  virtualisation = {
    libvirtd = {
      enable = true;
      qemu.swtpm.enable = true;
    };
    docker.enable = true;
  };

  console.keyMap = consoleKeyMap;

  system.stateVersion = "24.11";
}
