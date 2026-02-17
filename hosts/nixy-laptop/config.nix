{
  config,
  pkgs,
  pkgsUnstable,
  host,
  lib,
  username,
  options,
  inputs,
  ...
}: let
  inherit (import ./variables.nix) keyboardLayout consoleKeyMap;
in {
  imports = [
    inputs.dms.nixosModules.greeter
    ./hardware.nix
    ./users.nix
    ../../modules/amd-drivers.nix
    ../../modules/nvidia-drivers.nix
    ../../modules/nvidia-prime-drivers.nix
    ../../modules/intel-drivers.nix
    ../../modules/vm-guest-services.nix
    ../../modules/local-hardware-clock.nix
  ];

  features.canbus.enable = true;

  boot = {
    # Kernel
    kernelPackages = pkgs.linuxPackages_zen;
    # This is for OBS Virtual Cam Support
    kernelModules = ["v4l2loopback"];
    extraModulePackages = [config.boot.kernelPackages.v4l2loopback];
    extraModprobeConfig = ''
      options v4l2loopback devices=1 video_nr=1 card_label="OBS Cam" exclusive_caps=1
    '';
    # Needed For Some Steam Games
    kernel.sysctl = {
      "vm.max_map_count" = 2147483642;
    };
    # Bootloader.
    loader.systemd-boot.enable = true;
    loader.efi.canTouchEfiVariables = true;
    # Make /tmp a tmpfs
    tmp = {
      useTmpfs = false;
      tmpfsSize = "30%";
    };
    # Appimage Support
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

  # Styling Options
  stylix = {
    enable = true;
    image = ../../pictures/wallpapers/beautifulmountainscape.jpg;
    # base16Scheme = {
    #   base00 = "232136";
    #   base01 = "2a273f";
    #   base02 = "393552";
    #   base03 = "6e6a86";
    #   base04 = "908caa";
    #   base05 = "e0def4";
    #   base06 = "e0def4";
    #   base07 = "56526e";
    #   base08 = "eb6f92";
    #   base09 = "f6c177";
    #   base0A = "ea9a97";
    #   base0B = "3e8fb0";
    #   base0C = "9ccfd8";
    #   base0D = "c4a7e7";
    #   base0E = "f6c177";
    #   base0F = "56526e";
    # };
    polarity = "dark";
    opacity.terminal = 0.8;
    cursor.package = pkgs.bibata-cursors;
    cursor.name = "Bibata-Modern-Ice";
    cursor.size = 24;
    fonts = {
      monospace = {
        package = pkgs.nerd-fonts.monaspace;
        name = "MonaspiceKr Nerd Font Mono";
      };
      sansSerif = {
        package = pkgs.nerd-fonts.monaspace;
        name = "MonaspiceNe Nerd Font";
      };
      serif = {
        package = pkgs.nerd-fonts.monaspace;
        name = "MonaspiceXe Nerd Font";
      };
      sizes = {
        applications = 12;
        terminal = 15;
        desktop = 11;
        popups = 12;
      };
    };
  };

  # Extra Module Options
  # drivers.amdgpu.enable = false;
  # drivers.nvidia.enable = true;
  # hardware.nvidia.open = true;

  # drivers.nvidia-prime = {
  #   enable = false;
  #   intelBusID = "";
  #   nvidiaBusID = "";
  # };
  # drivers.intel.enable = false;
  vm.guest-services.enable = false;
  local.hardware-clock.enable = true;

  # Enable networking
  networking = {
    networkmanager = {
      enable = lib.mkDefault true;
      wifi.backend = lib.mkForce "iwd";
    };
    wireless.iwd.enable = lib.mkForce true;
  };
  networking.hostName = host;
  networking.timeServers = options.networking.timeServers.default ++ ["pool.ntp.org"];

  # Set your time zone.
  time.timeZone = "Europe/Berlin";

  # Select internationalisation properties.
  i18n.defaultLocale = "en_US.UTF-8";

  i18n.extraLocaleSettings = {
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

  programs = {
    # todo
    "dank-material-shell".greeter = {
      enable = true;
      compositor.name = "niri";
      configHome = "/home/yourusername";
      logs = {
        save = true;
        path = "/tmp/dms-greeter.log";
      };
    };
    xwayland.enable = true;
    gamescope = {
      enable = true;
      # not needed when using gamemoderun
      capSysNice = false;
    };
    gamemode = {
      enable = true;
      enableRenice = true;
    };
    hyprland.enable = true; # may be needed for portals???
    niri.enable = true;
    firefox.enable = false;
    starship = {
      enable = true;
      settings = {
        add_newline = false;
        buf = {
          symbol = " ";
        };
        c = {
          symbol = " ";
        };
        directory = {
          read_only = " 󰌾";
        };
        docker_context = {
          symbol = " ";
        };
        fossil_branch = {
          symbol = " ";
        };
        git_branch = {
          symbol = " ";
        };
        golang = {
          symbol = " ";
        };
        hg_branch = {
          symbol = " ";
        };
        hostname = {
          ssh_symbol = " ";
        };
        lua = {
          symbol = " ";
        };
        memory_usage = {
          symbol = "󰍛 ";
        };
        meson = {
          symbol = "󰔷 ";
        };
        nim = {
          symbol = "󰆥 ";
        };
        nix_shell = {
          symbol = " ";
        };
        nodejs = {
          symbol = " ";
        };
        ocaml = {
          symbol = " ";
        };
        package = {
          symbol = "󰏗 ";
        };
        python = {
          symbol = " ";
        };
        rust = {
          symbol = " ";
        };
        swift = {
          symbol = " ";
        };
        zig = {
          symbol = " ";
        };
      };
    };
    dconf.enable = true;
    seahorse.enable = true;
    fuse.userAllowOther = true;
    mtr.enable = true;
    gnupg.agent = {
      enable = true;
      enableSSHSupport = false;
    };
    ssh = {
      startAgent = true;
      extraConfig = ''
        Host *
          AddKeysToAgent yes
      '';
    };
    virt-manager.enable = true;
    steam = {
      enable = true;
      # gamescopeSession.enable = true;
      remotePlay.openFirewall = true;
      # dedicatedServer.openFirewall = true;
    };
    thunar = {
      enable = true;
      plugins = with pkgs.xfce; [
        thunar-archive-plugin
        thunar-volman
      ];
    };
  };

  nixpkgs.config.allowUnfree = true;

  users = {
    mutableUsers = true;
  };

  nixpkgs.config.permittedInsecurePackages = [
    "ventoy-qt5-1.1.07"
    "qtwebengine-5.15.19"
  ];

  environment.systemPackages = with pkgs;
    [
      proton-pass
      azuredatastudio
      teams-for-linux
      slack
      protonmail-desktop
      python3
      python3Packages.pip
      # stable packages
      snapper
      btrfs-progs
      nil
      xwayland-satellite
      # Dank Linux Deps
      cava
      cliphist
      matugen
      helix
      lsfg-vk
      lsfg-vk-ui
      superTuxKart
      libreoffice-qt
      hunspell
      hunspellDicts.en_US
      hunspellDicts.de_DE
      # Minecraft
      prismlauncher
      ftb-app
      firefox
      ventoy-full-qt
      protonvpn-gui
      # stremio
      warp-terminal
      antigravity-fhs
      code-cursor
      bun
      obs-studio
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
      vulkan-tools
      kontroll
      keymapp
      wally-cli
      alarm-clock-applet
      alacritty # fallback term
      google-chrome
      zellij # better tmux
      yazi # tui file manager
      fd # file searching
      fzf # quick file subtree navigation
      ripgrep # file content searching
      zoxide # modern cd replacement
      imagemagick # svg, font, heic and jpeg xl preview in yazi
      poppler # pdf preview
      jq # json preview
      p7zip-rar # archive extraction and preview
      ffmpeg # because the entire world of video runs on ffmpeg
      # wine prefix managers
      bottles
      lutris
      heroic
      protonup-ng # protonGE installer
      protontricks
      mangohud # ingame performance hud
      mangojuice
      qbittorrent # :)
      meld # best diff-tool ever
      obsidian # best markdown editor ever
      vesktop # hopefully this works with hyprland portal lol
      ## some dev stuff
      ## commented out -> try devshells first uwu
      # gcc
      # dotnetCorePackages.dotnet_9.sdk
      # dotnetCorePackages.dotnet_9.runtime
      # rustup
      ## distro
      vim
      wget
      killall
      docker-compose
      eza
      git
      cmatrix
      lolcat
      htop
      brave
      spice
      spice-gtk
      spice-protocol
      virtio-win
      win-spice
      libvirt
      virt-viewer
      adwaita-icon-theme
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
      hyprpicker
      ninja
      brightnessctl
      swappy
      appimage-run
      networkmanagerapplet
      yad
      inxi
      playerctl
      nh
      nixfmt-rfc-style
      libvirt
      swww
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
    ]
    ++ [
      # unstable
      pkgsUnstable.nodejs
      pkgsUnstable.dgop
      pkgsUnstable.dsearch
    ]
    ++ [
      # local packages
      inputs.helium.packages.${pkgs.stdenv.hostPlatform.system}.default
      # inputs.self.packages.${pkgs.stdenv.hostPlatform.system}.frostycli
    ];

  fonts = {
    packages = with pkgs; [
      noto-fonts-color-emoji
      noto-fonts-cjk-sans
      font-awesome
      symbola
      material-icons
    ];
    enableDefaultPackages = true;
    fontconfig = {
      enable = true;
      cache32Bit = true;
    };
  };

  # environment.etc = {
  #   "ovmf/edk2-x86_64-secure-code.fd" = {
  #     source = config.virtualisation.libvirtd.qemu.package + "/share/qemu/edk2-x86_64-secure-code.fd";
  #   };
  #   "ovmf/edk2-i386-vars.fd" = {
  #     source = config.virtualisation.libvirtd.qemu.package + "/share/qemu/edk2-i386-vars.fd";
  #   };
  # };

  environment.variables = {
    # ZANEYOS_VERSION = "2.3";
    # ZANEYOS = "true";
    STEAM_EXTRA_COMPAT_TOOLS_PATHS = "/home/${username}/.steam/root/compatibilitytools.d";
    # let gamescope handle mangohud injection or do so on game-by-game basis
    # MANGOHUD="1";
  };

  environment.sessionVariables = {
    DOTNET_ROOT = "${pkgs.dotnet-sdk}/share/dotnet";
  };

  # Extra Portal Configuration
  xdg.portal = {
    enable = true;
    wlr.enable = true;
    extraPortals = [
      pkgs.xdg-desktop-portal-gtk
      pkgs.xdg-desktop-portal
    ];
    configPackages = [
      pkgs.xdg-desktop-portal-gtk
      pkgs.xdg-desktop-portal-hyprland
      pkgs.xdg-desktop-portal
    ];
  };

  # Services to start
  services = {
    spice-vdagentd.enable = true;
    snapper = {
      # Snapper itself
      snapshotInterval = "daily";
      cleanupInterval = "daily";

      configs.home = {
        SUBVOLUME = "/home";

        # Create snapshots automatically
        TIMELINE_CREATE = true;

        # Cleanup old snapshots automatically
        TIMELINE_CLEANUP = true;

        # Retention policy
        TIMELINE_LIMIT_DAILY = 7;
        TIMELINE_LIMIT_WEEKLY = 0;
        TIMELINE_LIMIT_MONTHLY = 0;
        TIMELINE_LIMIT_YEARLY = 0;

        # Space-aware cleanup
        # allow up to <percentage> of fs if things go sideways
        SPACE_LIMIT = "0.3";
      };
    };
    tlp.enable = false;
    power-profiles-daemon.enable = true;
    xserver = {
      enable = false;
      xkb = {
        layout = "${keyboardLayout}";
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
    printing = {
      enable = true;
      drivers = [
        # pkgs.hplipWithPlugin
      ];
    };
    gnome.gnome-keyring.enable = true;
    gnome.gcr-ssh-agent.enable = false;
    avahi = {
      enable = true;
      nssmdns4 = true;
      openFirewall = true;
    };
    ipp-usb.enable = true;
    syncthing = {
      enable = false;
      user = "${username}";
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
  };
  systemd.services.greetd.after = ["systemd-udev-settle.service"];
  systemd.services.greetd.wants = ["systemd-udev-settle.service"];
  systemd.services.flatpak-repo = {
    path = [pkgs.flatpak];
    script = ''
      flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
    '';
  };
  hardware.sane = {
    enable = true;
    extraBackends = [pkgs.sane-airscan];
    disabledDefaultBackends = ["escl"];
  };

  services.udev = {
    packages = [pkgs.sane-airscan];
    extraRules = ''
      ATTRS{name}=="Sony Interactive Entertainment DualSense Wireless Controller Touchpad", ENV{LIBINPUT_IGNORE_DEVICE}="1"
      ATTRS{name}=="DualSense Wireless Controller Touchpad", ENV{LIBINPUT_IGNORE_DEVICE}="1"
    '';
  };
  # ZSA Keyboard flashing udev rules
  hardware.keyboard.zsa.enable = true;

  # Razor peripherals
  # hardware.openrazer.enable = true;

  # Extra Logitech Support
  hardware.logitech.wireless.enable = true;
  hardware.logitech.wireless.enableGraphical = true;

  # Bluetooth Support
  hardware.bluetooth.enable = true;
  hardware.bluetooth.powerOnBoot = true;
  services.blueman.enable = true;

  # Enable sound with pipewire.
  services.pulseaudio.enable = false;

  # Security / Polkit
  security.rtkit.enable = true;
  security.polkit.enable = true;
  security.polkit.extraConfig = ''
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
  security.pam.services.swaylock = {
    text = ''
      auth include login
    '';
  };

  # Optimization settings and garbage collection automation
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
        "https://hyprland.cachix.org"
        "https://nix-community.cachix.org"
        "https://yazi.cachix.org"
      ];
      trusted-public-keys = [
        "hyprland.cachix.org-1:a7pgxzMz7+chwVL3/pzj6jIBMioiJM7ypFP8PwtkuGc="
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

  # Virtualization / Containers
  virtualisation = {
    libvirtd = {
      enable = true;
      qemu = {
        package = pkgs.qemu_kvm;
        swtpm.enable = true;
      };
    };
    docker.enable = true;
    spiceUSBRedirection.enable = true;
  };

  # OpenGL
  hardware.graphics = {
    enable = true;
    enable32Bit = true;
  };

  console.keyMap = "${consoleKeyMap}";

  # Open ports in the firewall.
  # networking.firewall.allowedTCPPorts = [ ... ];
  # networking.firewall.allowedUDPPorts = [ ... ];
  # Or disable the firewall altogether.
  # networking.firewall.enable = false;

  # This value determines the NixOS release from which the default
  # settings for stateful data, like file locations and database versions
  # on your system were taken. It‘s perfectly fine and recommended to leave
  # this value at the release version of the first install of this system.
  # Before changing this value read the documentation for this option
  # (e.g. man configuration.nix or on https://nixos.org/nixos/options.html).
  system.stateVersion = "24.11"; # Did you read the comment?
}
