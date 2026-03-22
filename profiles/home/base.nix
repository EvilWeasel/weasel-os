{
  config,
  pkgs,
  pkgsUnstable,
  host,
  lib,
  username,
  inputs,
  ...
}: let
  inherit (import ../../hosts/${host}/variables.nix) gitEmail gitSigningKey gitUsername;
  repoDefaultPath = "${config.home.homeDirectory}/weasel-os";
  signingEnabled = gitSigningKey != "";
in {
  nixpkgs.config = {
    allowUnfree = true;
    allowUnfreePredicate = _: true;
  };

  home = {
    username = username;
    homeDirectory = "/home/${username}";
    stateVersion = "24.11";
    file = {
      "Pictures/wallpapers" = {
        source = ../../pictures/wallpapers;
        recursive = true;
      };
      "Pictures/face.png".source = ../../pictures/weasel.png;
    };
    packages = [
      (import ../../scripts/emopicker9000.nix {inherit pkgs;})
      (import ../../scripts/squirtle.nix {inherit pkgs;})
      (import ../../scripts/nvidia-offload.nix {inherit pkgs;})
      (import ../../scripts/wallsetter.nix {
        inherit pkgs username;
      })
      (import ../../scripts/weasel-shell-helpers.nix {
        inherit config host pkgs pkgsUnstable;
      })
      (import ../../scripts/weasel-dms-session.nix {inherit pkgs;})
      (import ../../scripts/weasel-collect-session-debug.nix {inherit pkgs;})
      (import ../../scripts/web-search.nix {inherit pkgs;})
      (import ../../scripts/rofi-launcher.nix {inherit pkgs;})
      (import ../../scripts/screenshootin.nix {inherit pkgs;})
      pkgs.adw-gtk3
      pkgs.bibata-cursors
      pkgs.capitaine-cursors
      pkgs.phinger-cursors
      pkgs.papirus-icon-theme
      pkgs.simp1e-cursors
      pkgs.vanilla-dmz
      pkgs.volantes-cursors
      pkgs.kitty
      pkgsUnstable.lmstudio
      pkgsUnstable.zed-editor
    ];
    sessionVariables = {
      WEASEL_OS_HOST = host;
      WEASEL_OS_ROOT = repoDefaultPath;
      WEASEL_DEBUG_HOME = "${config.home.homeDirectory}/weasel-debug";
      WEASEL_DEBUG_STATE = "${config.home.homeDirectory}/.local/state/weasel-debug";
      GTK_THEME = "adw-gtk3-dark";
      QT_STYLE_OVERRIDE = "adwaita-dark";
      QT_QPA_PLATFORMTHEME = "gtk3";
    };
  };

    imports = [
    inputs.dms.homeModules."dank-material-shell"
    ../../programs/emoji.nix
    ../../programs/fastfetch
    ../../programs/matugen.nix
    ../../programs/niri.nix
    ../../programs/neovim.nix
    ../../programs/terminal-stack.nix
    ../../programs/vscode.nix
    ../../programs/rofi/rofi.nix
    ../../programs/rofi/config-emoji.nix
    ../../programs/rofi/config-long.nix
    ../../programs/swaync.nix
  ];

  programs.git = {
    enable = true;
    settings.user =
      lib.optionalAttrs (gitUsername != "") {name = gitUsername;}
      // lib.optionalAttrs (gitEmail != "") {email = gitEmail;};
    signing = lib.mkIf signingEnabled {
      key = gitSigningKey;
      signByDefault = true;
    };
  };

  xdg = {
    userDirs = {
      enable = true;
      createDirectories = true;
    };
    dataFile = {
      "icons/Bibata-Modern-Amber" = {
        source = "${pkgs.bibata-cursors}/share/icons/Bibata-Modern-Amber";
        recursive = true;
      };
      "icons/Bibata-Modern-Classic" = {
        source = "${pkgs.bibata-cursors}/share/icons/Bibata-Modern-Classic";
        recursive = true;
      };
      "icons/Bibata-Modern-Ice" = {
        source = "${pkgs.bibata-cursors}/share/icons/Bibata-Modern-Ice";
        recursive = true;
      };
      "icons/Adwaita" = {
        source = "${pkgs.adwaita-icon-theme}/share/icons/Adwaita";
        recursive = true;
      };
      "icons/capitaine-cursors" = {
        source = "${pkgs.capitaine-cursors}/share/icons/capitaine-cursors";
        recursive = true;
      };
      "icons/capitaine-cursors-white" = {
        source = "${pkgs.capitaine-cursors}/share/icons/capitaine-cursors-white";
        recursive = true;
      };
      "icons/phinger-cursors-dark" = {
        source = "${pkgs.phinger-cursors}/share/icons/phinger-cursors-dark";
        recursive = true;
      };
      "icons/phinger-cursors-light" = {
        source = "${pkgs.phinger-cursors}/share/icons/phinger-cursors-light";
        recursive = true;
      };
      "icons/Papirus" = {
        source = "${pkgs.papirus-icon-theme}/share/icons/Papirus";
        recursive = true;
      };
      "icons/Papirus-Dark" = {
        source = "${pkgs.papirus-icon-theme}/share/icons/Papirus-Dark";
        recursive = true;
      };
      "icons/Papirus-Light" = {
        source = "${pkgs.papirus-icon-theme}/share/icons/Papirus-Light";
        recursive = true;
      };
      "icons/breeze" = {
        source = "${pkgs.kdePackages.breeze-icons}/share/icons/breeze";
        recursive = true;
      };
      "icons/breeze-dark" = {
        source = "${pkgs.kdePackages.breeze-icons}/share/icons/breeze-dark";
        recursive = true;
      };
      "icons/Numix" = {
        source = "${pkgs.numix-icon-theme}/share/icons/Numix";
        recursive = true;
      };
      "icons/Numix-Light" = {
        source = "${pkgs.numix-icon-theme}/share/icons/Numix-Light";
        recursive = true;
      };
      "icons/rose-pine" = {
        source = "${pkgs.rose-pine-icon-theme}/share/icons/rose-pine";
        recursive = true;
      };
      "icons/rose-pine-dawn" = {
        source = "${pkgs.rose-pine-icon-theme}/share/icons/rose-pine-dawn";
        recursive = true;
      };
      "icons/rose-pine-moon" = {
        source = "${pkgs.rose-pine-icon-theme}/share/icons/rose-pine-moon";
        recursive = true;
      };
      "icons/Simp1e" = {
        source = "${pkgs.simp1e-cursors}/share/icons/Simp1e";
        recursive = true;
      };
      "icons/Simp1e-Adw-Dark" = {
        source = "${pkgs.simp1e-cursors}/share/icons/Simp1e-Adw-Dark";
        recursive = true;
      };
      "icons/Simp1e-Rose-Pine-Moon" = {
        source = "${pkgs.simp1e-cursors}/share/icons/Simp1e-Rose-Pine-Moon";
        recursive = true;
      };
      "icons/Simp1e-Tokyo-Night" = {
        source = "${pkgs.simp1e-cursors}/share/icons/Simp1e-Tokyo-Night";
        recursive = true;
      };
      "icons/Tela" = {
        source = "${pkgs.tela-icon-theme}/share/icons/Tela";
        recursive = true;
      };
      "icons/Tela-dark" = {
        source = "${pkgs.tela-icon-theme}/share/icons/Tela-dark";
        recursive = true;
      };
      "icons/Tela-light" = {
        source = "${pkgs.tela-icon-theme}/share/icons/Tela-light";
        recursive = true;
      };
      "icons/Tela-dracula" = {
        source = "${pkgs.tela-icon-theme}/share/icons/Tela-dracula";
        recursive = true;
      };
      "icons/Tela-nord" = {
        source = "${pkgs.tela-icon-theme}/share/icons/Tela-nord";
        recursive = true;
      };
      "icons/Vanilla-DMZ" = {
        source = "${pkgs.vanilla-dmz}/share/icons/DMZ-White";
        recursive = true;
      };
      "icons/Volantes" = {
        source = "${pkgs.volantes-cursors}/share/icons/volantes_cursors";
        recursive = true;
      };
      "icons/Volantes-Light" = {
        source = "${pkgs.volantes-cursors}/share/icons/volantes_light_cursors";
        recursive = true;
      };
    };
    configFile = {
      "mimeapps.list" = {
        source = config.lib.file.mkOutOfStoreSymlink "${repoDefaultPath}/programs/mimeapps.list";
        force = true;
      };
      "DankMaterialShell/settings.json" = {
        source = config.lib.file.mkOutOfStoreSymlink "${repoDefaultPath}/programs/dank-material-shell/settings.json";
        force = true;
      };
      "swappy/config".text = ''
        [Default]
        save_dir=/home/${username}/Pictures/Screenshots
        save_filename_format=swappy-%Y%m%d-%H%M%S.png
        show_panel=false
        line_size=5
        text_size=20
        text_font=Ubuntu
        paint_mode=brush
        early_exit=true
        fill_shape=false
      '';
    };
  };

  home.file = {
    ".config/gtk-3.0/gtk.css" = {
      text = ''
      @import url("dank-colors.css");
      '';
      force = true;
    };
    ".config/gtk-4.0/gtk.css" = {
      text = ''
      @import url("dank-colors.css");
      '';
      force = true;
    };
    ".config/kitty/kitty.conf" = {
      source = config.lib.file.mkOutOfStoreSymlink "${repoDefaultPath}/programs/kitty/kitty.conf";
      force = true;
    };
    ".config/qt5ct/qt5ct.conf" = {
      source = config.lib.file.mkOutOfStoreSymlink "${repoDefaultPath}/programs/qt5ct.conf";
      force = true;
    };
    ".config/qt6ct/qt6ct.conf" = {
      source = config.lib.file.mkOutOfStoreSymlink "${repoDefaultPath}/programs/qt6ct.conf";
      force = true;
    };
  };

  home.file.".local/share/applications/kitty.desktop" = {
    source = config.lib.file.mkOutOfStoreSymlink "${repoDefaultPath}/programs/kitty.desktop";
  };

  dconf.settings = {
    "org/virt-manager/virt-manager/connections" = {
      autoconnect = ["qemu:///system"];
      uris = ["qemu:///system"];
    };
  };

  gtk = {
    theme = {
      name = "adw-gtk3-dark";
      package = pkgs.adw-gtk3;
    };
    iconTheme = {
      name = "Papirus-Dark";
      package = pkgs.papirus-icon-theme;
    };
    gtk3.extraConfig.gtk-application-prefer-dark-theme = 1;
    gtk4.extraConfig.gtk-application-prefer-dark-theme = 1;
  };

  qt = {
    enable = true;
    style.name = lib.mkForce "adwaita-dark";
  };

  systemd.user.sessionVariables = {
    QT_QPA_PLATFORMTHEME = "gtk3";
  };

  programs = {
    gh.enable = true;
    btop = {
      enable = true;
      settings.vim_keys = true;
    };
    home-manager.enable = true;
  };
}
