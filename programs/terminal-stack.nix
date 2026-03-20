{
  config,
  lib,
  pkgsUnstable,
  ...
}: let
  repoDefaultPath = "${config.home.homeDirectory}/weasel-os";

  shellCommon = ''
    export XDG_DATA_DIRS=$XDG_DATA_DIRS:/usr/share:/var/lib/flatpak/exports/share:$HOME/.local/share/flatpak/exports/share

    weasel_os_root() {
      if [ -n "$WEASEL_OS_ROOT" ] && [ -f "$WEASEL_OS_ROOT/flake.nix" ]; then
        printf '%s\n' "$WEASEL_OS_ROOT"
        return 0
      fi

      local git_root=""
      git_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
      if [ -n "$git_root" ] && [ -f "$git_root/flake.nix" ] && [ -d "$git_root/hosts" ] && [ -d "$git_root/programs" ]; then
        printf '%s\n' "$git_root"
        return 0
      fi

      printf '%s\n' "${repoDefaultPath}"
    }
  '';
in {
  home.sessionVariables = {
    EDITOR = "nvim";
    VISUAL = "nvim";
  };

  programs = {
    starship = {
      enable = true;
      package = pkgsUnstable.starship;
      enableBashIntegration = true;
      enableNushellIntegration = true;
      enableZshIntegration = true;
      settings = {
        add_newline = false;
        format = "$directory$git_branch$git_status$cmd_duration$line_break$character";
        cmd_duration = {
          min_time = 500;
          style = "#f9e2af";
        };
        character = {
          success_symbol = "[❯](#a6e3a1)";
          error_symbol = "[❯](#f38ba8)";
        };
        directory = {
          style = "#b4befe";
          truncation_length = 3;
          truncate_to_repo = false;
        };
        git_branch = {
          style = "#cba6f7";
          symbol = " ";
        };
        git_status = {
          style = "#fab387";
        };
      };
    };

    atuin = {
      enable = true;
      package = pkgsUnstable.atuin;
      enableBashIntegration = true;
      enableNushellIntegration = true;
      enableZshIntegration = true;
      settings = {
        search_mode = "fuzzy";
      };
    };

    carapace = {
      enable = true;
      package = pkgsUnstable.carapace;
      enableBashIntegration = true;
      enableNushellIntegration = true;
      enableZshIntegration = true;
    };

    fzf = {
      enable = true;
      package = pkgsUnstable.fzf;
      enableBashIntegration = true;
      enableZshIntegration = true;
      defaultCommand = "fd --hidden --follow --exclude .git";
      defaultOptions = [
        "--border"
        "--height 40%"
        "--info=inline"
        "--layout=reverse"
      ];
      fileWidgetCommand = "fd --type f --hidden --follow --exclude .git";
      changeDirWidgetCommand = "fd --type d --hidden --follow --exclude .git";
      historyWidgetOptions = [
        "--exact"
        "--sort"
      ];
      colors = lib.mkForce {
        bg = "#1e1e2e";
        "bg+" = "#313244";
        fg = "#cdd6f4";
        "fg+" = "#f5e0dc";
        hl = "#89b4fa";
        "hl+" = "#b4befe";
        info = "#94e2d5";
        prompt = "#fab387";
        pointer = "#f38ba8";
        marker = "#a6e3a1";
        spinner = "#f5c2e7";
        header = "#cba6f7";
      };
    };

    yazi = {
      enable = true;
      package = pkgsUnstable.yazi;
      shellWrapperName = "y";
      enableBashIntegration = true;
      enableNushellIntegration = true;
      enableZshIntegration = true;
      extraPackages = with pkgsUnstable; [
        fd
        fzf
        ffmpegthumbnailer
        glow
        mediainfo
        ripgrep
        zoxide
      ];
      plugins = {
        compress = pkgsUnstable.yaziPlugins.compress;
        diff = pkgsUnstable.yaziPlugins.diff;
        "full-border" = pkgsUnstable.yaziPlugins."full-border";
        git = pkgsUnstable.yaziPlugins.git;
        glow = pkgsUnstable.yaziPlugins.glow;
        "jump-to-char" = pkgsUnstable.yaziPlugins."jump-to-char";
        "mime-ext" = pkgsUnstable.yaziPlugins."mime-ext";
        "no-status" = pkgsUnstable.yaziPlugins."no-status";
        piper = pkgsUnstable.yaziPlugins.piper;
        projects = pkgsUnstable.yaziPlugins.projects;
        "recycle-bin" = pkgsUnstable.yaziPlugins."recycle-bin";
        "relative-motions" = pkgsUnstable.yaziPlugins."relative-motions";
        restore = pkgsUnstable.yaziPlugins.restore;
        "rich-preview" = pkgsUnstable.yaziPlugins."rich-preview";
        "smart-enter" = pkgsUnstable.yaziPlugins."smart-enter";
        "smart-filter" = pkgsUnstable.yaziPlugins."smart-filter";
        "vcs-files" = pkgsUnstable.yaziPlugins."vcs-files";
        yatline = pkgsUnstable.yaziPlugins.yatline;
        "yatline-catppuccin" = pkgsUnstable.yaziPlugins."yatline-catppuccin";
      };
      settings = {
        log.enabled = false;
        mgr = {
          show_hidden = true;
          sort_by = "mtime";
          sort_dir_first = true;
          sort_reverse = true;
        };
      };
      keymap = {
        input.prepend_keymap = [
          {
            run = "close";
            on = ["<C-q>"];
          }
          {
            run = "close --submit";
            on = ["<Enter>"];
          }
          {
            run = "escape";
            on = ["<Esc>"];
          }
          {
            run = "backspace";
            on = ["<Backspace>"];
          }
        ];
        manager.prepend_keymap = [
          {
            run = "escape";
            on = ["<Esc>"];
          }
          {
            run = "quit";
            on = ["q"];
          }
          {
            run = "close";
            on = ["<C-q>"];
          }
        ];
      };
      theme = {
        filetype.rules = [
          {
            fg = "#89b4fa";
            mime = "application/javascript";
          }
          {
            fg = "#89b4fa";
            mime = "text/javascript";
          }
          {
            fg = "#89b4fa";
            mime = "text/x-typescript";
          }
          {
            fg = "#74c7ec";
            mime = "text/x-csharp";
          }
          {
            fg = "#fab387";
            mime = "text/x-rust";
          }
          {
            fg = "#a6e3a1";
            mime = "text/x-python";
          }
          {
            fg = "#94e2d5";
            mime = "text/x-shellscript";
          }
          {
            fg = "#b4befe";
            mime = "text/markdown";
          }
          {
            fg = "#cba6f7";
            mime = "application/x-nix";
          }
        ];
      };
    };

    zellij = {
      enable = true;
      package = pkgsUnstable.zellij;
      settings = {
        theme = "catppuccin-mocha";
      };
    };

    nushell = {
      enable = true;
      package = pkgsUnstable.nushell;
      shellAliases.zj = "zellij";
      settings = {
        show_banner = false;
        history.file_format = "sqlite";
      };
    };

    bash = {
      enable = true;
      enableCompletion = true;
      shellAliases.zj = "zellij";
      initExtra = lib.mkAfter ''
        ${shellCommon}
        if [[ -t 1 ]]; then
          fastfetch || true
        fi

        bind "set completion-ignore-case on"
        bind "set show-all-if-ambiguous on"
        shopt -s direxpand
      '';
    };

    zsh = {
      enable = true;
      enableCompletion = true;
      defaultKeymap = "viins";
      shellAliases.zj = "zellij";
      autosuggestion.enable = true;
      syntaxHighlighting = {
        enable = true;
        highlighters = [
          "main"
          "brackets"
          "cursor"
          "root"
          "line"
        ];
      };
      initContent = lib.mkAfter ''
        ${shellCommon}
        if [[ -t 1 ]]; then
          fastfetch || true
        fi

        bindkey '^R' history-incremental-search-backward
        zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}' 'r:|[._-]=* r:|=*'
        zstyle ':completion:*' menu select
      '';
      plugins = [
        {
          name = "fzf-tab";
          src = pkgsUnstable.zsh-fzf-tab;
          file = "share/fzf-tab/fzf-tab.plugin.zsh";
        }
      ];
    };
  };
}
