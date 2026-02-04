{
  pkgs,
  pkgsUnstable,
  username,
  host,
  config,
  lib,
  inputs,
  ...
}:
let
  inherit (import ./variables.nix) gitUsername gitEmail gitSigningKey;
in
{
  nixpkgs = {
    config = {
      allowUnfree = true;
      allowUnfreePredicate = (_: true);
    };
  };
  # Home Manager Settings
  home.username = "${username}";
  home.homeDirectory = "/home/${username}";
  home.stateVersion = "24.11";

  # Import Program Configurations
  imports = [
    inputs.dms.homeModules.dank-material-shell

    ../../programs/emoji.nix
    ../../programs/fastfetch
    ../../programs/hyprland.nix
    ../../programs/neovim.nix
    ../../programs/rofi/rofi.nix
    ../../programs/rofi/config-emoji.nix
    ../../programs/rofi/config-long.nix
    ../../programs/swaync.nix
    ../../programs/waybar.nix
    ../../programs/wlogout.nix
  ];

  # Place Files Inside Home Directory
  home.file = {
    "Pictures/wallpapers" = {
      source = ../../pictures/wallpapers;
      recursive = true;
    };
    "Pictures/face.png".source = ../../pictures/weasel.png;
  };

  # Install & Configure Git
  programs.git = {
    enable = true;
    settings = {
      user = {
        name = "${gitUsername}";
        email = "${gitEmail}";
      };
    };
    signing = {
      key = "${gitSigningKey}";
      signByDefault = true;
    };
  };

  # Create XDG Dirs
  xdg = {
    userDirs = {
      enable = true;
      createDirectories = true;
    };
    configFile = {
      "hypr" = {
        source = ../../.config/hypr;
        recursive = true;
      };
      "wlogout/icons" = {
        source = ../../pictures/wlogout;
        recursive = true;
      };
      # Swappy config
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
      autoconnect = [ "qemu:///system" ];
      uris = [ "qemu:///system" ];
    };
  };

  # Styling Options
  stylix.targets.vscode.enable = false;
  stylix.targets.waybar.enable = false;
  stylix.targets.rofi.enable = false;
  stylix.targets.hyprland.enable = false;
  stylix.targets.vesktop.enable = false;
  gtk = {
    iconTheme = {
      name = "Papirus-Dark";
      package = pkgs.papirus-icon-theme;
    };
    gtk3.extraConfig = {
      gtk-application-prefer-dark-theme = 1;
    };
    gtk4.extraConfig = {
      gtk-application-prefer-dark-theme = 1;
    };
  };
  qt = {
    enable = true;
    style.name = "kvantum";
  };

  # Scripts
  home.packages = [
    (import ../../scripts/emopicker9000.nix { inherit pkgs; })
    (import ../../scripts/task-waybar.nix { inherit pkgs; })
    (import ../../scripts/squirtle.nix { inherit pkgs; })
    (import ../../scripts/nvidia-offload.nix { inherit pkgs; })
    (import ../../scripts/wallsetter.nix {
      inherit pkgs;
      inherit username;
    })
    (import ../../scripts/web-search.nix { inherit pkgs; })
    (import ../../scripts/rofi-launcher.nix { inherit pkgs; })
    (import ../../scripts/screenshootin.nix { inherit pkgs; })
    (import ../../scripts/list-hypr-bindings.nix {
      inherit pkgs;
      inherit host;
    })
  ];

  services = {
    hypridle = {
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
  };

  programs = {
    dankMaterialShell = {
      enable = true;
      systemd = {
        enable = true;
        restartIfChanged = true;
      };
      # Core features
      enableSystemMonitoring = true; # System monitoring widgets (dgop)
      dgop.package = pkgsUnstable.dgop;
      # enableClipboard = true; # Clipboard history manager
      enableVPN = true; # VPN management widget
      enableDynamicTheming = false; # Wallpaper-based theming (matugen)
      enableAudioWavelength = true; # Audio visualizer (cava)
      enableCalendarEvents = true; # Calendar integration (khal)
      plugins = {
        DockerManager = {
          src = pkgs.fetchFromGitHub {
            owner = "LuckShiba";
            repo = "DmsDockerManager";
            rev = "v1.2.0";
            sha256 = "sha256-VoJCaygWnKpv0s0pqTOmzZnPM922qPDMHk4EPcgVnaU=";
          };
        };
        WebSearch = {
          src = pkgs.fetchFromGitHub {
            owner = "devnullvoid";
            repo = "dms-web-search";
            rev = "81ccd9f";
            sha256 = "sha256-mKbmROijhYhy/IPbVxYbKyggXesqVGnS/AfAEyeQVhg=";
          };
        };
        CommandRunner = {
          src = pkgs.fetchFromGitHub {
            owner = "devnullvoid";
            repo = "dms-command-runner";
            rev = "d89a094";
            sha256 = "sha256-tXqDRVp1VhyD1WylW83mO4aYFmVg/NV6Z/toHmb5Tn8=";
          };
        };
        EmojiLauncher = {
          src = pkgs.fetchFromGitHub {
            owner = "devnullvoid";
            repo = "dms-emoji-launcher";
            rev = "2951ec7";
            sha256 = "sha256-aub5pXRMlMs7dxiv5P+/Rz/dA4weojr+SGZAItmbOvo=";
          };
        };
        Calculator = {
          src = pkgs.fetchFromGitHub {
            owner = "rochacbruno";
            repo = "DankCalculator";
            rev = "de6dbd5";
            sha256 = "sha256-Vq+E2F2Ym5JdzjpCusRMDXd6uuAhhjAehyD/tO3omdY=";
          };
        };
        NiriWindows = {
          src = pkgs.fetchFromGitHub {
            owner = "rochacbruno";
            repo = "DankNiriWindows";
            rev = "b845277";
            sha256 = "sha256-rdZAnkRyfycI2a2wjSiepQwRI49zKbwoRzpz1+c6ZJA=";
          };
        };
      };
    };
    vscode = {
      enable = true;
      package = pkgsUnstable.vscode.fhs;
    };
    gh.enable = true;
    btop = {
      enable = true;
      settings = {
        vim_keys = true;
      };
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
    starship = {
      enable = true;
      package = pkgs.starship;
    };
    zsh = {
      enable = true;
      enableCompletion = true;
      profileExtra = ''
        export XDG_DATA_DIRS=$XDG_DATA_DIRS:/usr/share:/var/lib/flatpak/exports/share:$HOME/.local/share/flatpak/exports/share
        #if [ -z "$DISPLAY" ] && [ "$XDG_VTNR" = 1 ]; then
        #  exec Hyprland
        #fi
      '';
      initContent = ''
        fastfetch
        if [ -f $HOME/.zshrc-personal ]; then
          source $HOME/.zshrc-personal
        fi
        bindkey -v
        bindkey '^R' history-incremental-search-backward
        eval "$(zoxide init zsh)"
        function y() {
        	local tmp="$(mktemp -t "yazi-cwd.XXXXXX")" cwd
        	yazi "$@" --cwd-file="$tmp"
        	if cwd="$(command cat -- "$tmp")" && [ -n "$cwd" ] && [ "$cwd" != "$PWD" ]; then
        		builtin cd -- "$cwd"
        	fi
        	rm -f -- "$tmp"
        }
      '';
      shellAliases = {
        shader-log = "tail -f ~/.steam/root/logs/shader_log.txt";
        sv = "sudo nvim";
        fr = "nh os switch --hostname ${host} /home/${username}/weasel-os";
        fu = "nh os switch --hostname ${host} --update /home/${username}/weasel-os";
        ncg = "nix-collect-garbage --delete-old && sudo nix-collect-garbage -d && sudo /run/current-system/bin/switch-to-configuration boot";
        v = "nvim";
        cat = "bat";
        ls = "eza --icons";
        ll = "eza -lh --icons --grid --group-directories-first";
        la = "eza -lah --icons --grid --group-directories-first";
        ".." = "cd ..";
      };
      syntaxHighlighting = {
        enable = true;
        highlighters = [
          "brackets"
          "cursor"
          "root"
          "line"
        ];
      };
    };
    bash = {
      enable = true;
      enableCompletion = true;
      profileExtra = ''
        export XDG_DATA_DIRS=$XDG_DATA_DIRS:/usr/share:/var/lib/flatpak/exports/share:$HOME/.local/share/flatpak/exports/share
        #if [ -z "$DISPLAY" ] && [ "$XDG_VTNR" = 1 ]; then
        #  exec Hyprland
        #fi
      '';
      initExtra = ''
        fastfetch
        if [ -f $HOME/.bashrc-personal ]; then
          source $HOME/.bashrc-personal
        fi
        eval "$(zoxide init bash)"
        function y() {
        	local tmp="$(mktemp -t "yazi-cwd.XXXXXX")" cwd
        	yazi "$@" --cwd-file="$tmp"
        	if cwd="$(command cat -- "$tmp")" && [ -n "$cwd" ] && [ "$cwd" != "$PWD" ]; then
        		builtin cd -- "$cwd"
        	fi
        	rm -f -- "$tmp"
        }
      '';
      shellAliases = {
        shader-log = "tail -f ~/.steam/root/logs/shader_log.txt";
        sv = "sudo nvim";
        fr = "nh os switch --hostname ${host} /home/${username}/weasel-os";
        fu = "nh os switch --hostname ${host} --update /home/${username}/weasel-os";
        ncg = "nix-collect-garbage --delete-old && sudo nix-collect-garbage -d && sudo /run/current-system/bin/switch-to-configuration boot";
        v = "nvim";
        cat = "bat";
        ls = "eza --icons";
        ll = "eza -lh --icons --grid --group-directories-first";
        la = "eza -lah --icons --grid --group-directories-first";
        ".." = "cd ..";
      };
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
            path = "/home/${username}/pictures/wallpapers/beautifulmountainscape.jpg";
            blur_passes = 3;
            blur_size = 8;
          }
        ];
        image = [
          {
            path = "/home/${username}/pictures/weasel.png";
            size = 150;
            border_size = 4;
            border_color = "rgb(0C96F9)";
            rounding = -1; # Negative means circle
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
