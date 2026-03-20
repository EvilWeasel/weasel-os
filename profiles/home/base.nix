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
      (import ../../scripts/web-search.nix {inherit pkgs;})
      (import ../../scripts/rofi-launcher.nix {inherit pkgs;})
      (import ../../scripts/screenshootin.nix {inherit pkgs;})
      pkgsUnstable.lmstudio
      pkgsUnstable.zed-editor
    ];
    sessionVariables = {
      WEASEL_OS_HOST = host;
      WEASEL_OS_ROOT = repoDefaultPath;
    };
  };

  imports = [
    inputs.dms.homeModules."dank-material-shell"
    ../../programs/emoji.nix
    ../../programs/fastfetch
    ../../programs/niri.nix
    ../../programs/neovim.nix
    ../../programs/terminal-stack.nix
    ../../programs/vscode.nix
    ../../programs/rofi/rofi.nix
    ../../programs/rofi/config-emoji.nix
    ../../programs/rofi/config-long.nix
    ../../programs/swaync.nix
    ../../programs/wlogout.nix
  ];

  programs.git = {
    enable = true;
    settings.user = {
      name = gitUsername;
      email = gitEmail;
    };
    signing = {
      key = gitSigningKey;
      signByDefault = true;
    };
  };

  xdg = {
    userDirs = {
      enable = true;
      createDirectories = true;
    };
    configFile = {
      "wlogout/icons" = {
        source = ../../pictures/wlogout;
        recursive = true;
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

  dconf.settings = {
    "org/virt-manager/virt-manager/connections" = {
      autoconnect = ["qemu:///system"];
      uris = ["qemu:///system"];
    };
  };

  stylix.targets = {
    vscode.enable = false;
    rofi.enable = false;
    vesktop.enable = false;
  };

  gtk = {
    iconTheme = {
      name = "Papirus-Dark";
      package = pkgs.papirus-icon-theme;
    };
    gtk3.extraConfig.gtk-application-prefer-dark-theme = 1;
    gtk4.extraConfig.gtk-application-prefer-dark-theme = 1;
  };

  qt = {
    enable = true;
    style.name = lib.mkForce "kvantum";
  };

  services.hypridle = {
    enable = true;
    settings = {
      general = {
        after_sleep_cmd = "hyprctl dispatch dpms on";
        ignore_dbus_inhibit = false;
        lock_cmd = "hyprlock";
      };
      listener = [
        {
          timeout = 900;
          on-timeout = "hyprlock";
        }
        {
          timeout = 1200;
          on-timeout = "hyprctl dispatch dpms off";
          on-resume = "hyprctl dispatch dpms on";
        }
      ];
    };
  };

  programs = {
    gh.enable = true;
    btop = {
      enable = true;
      settings.vim_keys = true;
    };
    kitty = {
      enable = true;
      package = pkgs.kitty;
      settings = {
        scrollback_lines = 2000;
        wheel_scroll_min_lines = 1;
        window_padding_width = 4;
        confirm_os_window_close = 0;
      };
      extraConfig = ''
        tab_bar_style fade
        tab_fade 1
        active_tab_font_style   bold
        inactive_tab_font_style bold
      '';
    };
    home-manager.enable = true;
    hyprlock = {
      enable = true;
      settings = {
        general = {
          disable_loading_bar = true;
          grace = 10;
          hide_cursor = true;
          no_fade_in = false;
        };
        lib.mkPrio.background = [
          {
            path = "/home/${username}/Pictures/wallpapers/beautifulmountainscape.jpg";
            blur_passes = 3;
            blur_size = 8;
          }
        ];
        image = [
          {
            path = "/home/${username}/Pictures/face.png";
            size = 150;
            border_size = 4;
            border_color = "rgb(0C96F9)";
            rounding = -1;
            position = "0, 200";
            halign = "center";
            valign = "center";
          }
        ];
        lib.mkPrio.input-field = [
          {
            size = "200, 50";
            position = "0, -80";
            monitor = "";
            dots_center = true;
            fade_on_empty = false;
            font_color = "rgb(CFE6F4)";
            inner_color = "rgb(657DC2)";
            outer_color = "rgb(0D0E15)";
            outline_thickness = 5;
            placeholder_text = "Password...";
            shadow_passes = 2;
          }
        ];
      };
    };
  };
}
