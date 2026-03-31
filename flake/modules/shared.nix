{inputs, ...}: let
  mkPkgs = nixpkgsInput: system:
    import nixpkgsInput {
      inherit system;
      config.allowUnfree = true;
    };
in {
  _module.args = {
    inherit mkPkgs;
    hostRegistry = import ../../lib/hosts.nix {inherit inputs;};
    mkHost = import ../../lib/mk-host.nix {inherit inputs;};
    mkDevEnvironment = system: let
      pkgsStable = mkPkgs inputs.nixpkgs system;
      pkgsUnstable = mkPkgs inputs.nixpkgs-unstable system;

      devPackages = with pkgsUnstable; [
        alejandra
        atuin
        bash-completion
        bashInteractive
        bat
        bubblewrap
        bun
        carapace
        claude-code
        codex
        csharp-ls
        cargo
        dotnetCorePackages.dotnet_9.sdk
        eza
        coreutils
        fd
        fastfetch
        ffmpegthumbnailer
        fzf
        git
        jq
        glow
        nh
        lua-language-server
        marksman
        mediainfo
        neovim
        nixd
        nodejs_22
        nushell
        pnpm
        pyright
        ripgrep
        rust-analyzer
        rustc
        rustfmt
        python3
        shellcheck
        shfmt
        starship
        taplo
        typescript
        typescript-language-server
        yazi
        yaml-language-server
        zellij
        zoxide
        zsh
        zsh-completions
        zsh-fzf-tab
      ];

      devStarshipConfig = pkgsUnstable.writeText "weasel-dev-starship.toml" ''
        add_newline = false
        format = "$directory$git_branch$git_status$cmd_duration$line_break$character"
        palette = "catppuccin_mocha"

        [cmd_duration]
        min_time = 500
        style = "yellow"

        [character]
        success_symbol = "[❯](green)"
        error_symbol = "[❯](red)"

        [directory]
        style = "lavender"
        truncation_length = 3
        truncate_to_repo = false

        [git_branch]
        style = "mauve"
        symbol = " "

        [git_status]
        style = "peach"

        [palettes.catppuccin_mocha]
        rosewater = "#f5e0dc"
        flamingo = "#f2cdcd"
        pink = "#f5c2e7"
        mauve = "#cba6f7"
        red = "#f38ba8"
        maroon = "#eba0ac"
        peach = "#fab387"
        yellow = "#f9e2af"
        green = "#a6e3a1"
        teal = "#94e2d5"
        sky = "#89dceb"
        sapphire = "#74c7ec"
        blue = "#89b4fa"
        lavender = "#b4befe"
        text = "#cdd6f4"
        subtext1 = "#bac2de"
        subtext0 = "#a6adc8"
        overlay2 = "#9399b2"
        overlay1 = "#7f849c"
        overlay0 = "#6c7086"
        surface2 = "#585b70"
        surface1 = "#45475a"
        surface0 = "#313244"
        base = "#1e1e2e"
        mantle = "#181825"
        crust = "#11111b"
      '';

      devZshDotDir = pkgsUnstable.runCommand "weasel-dev-zdotdir" {} ''
        mkdir -p "$out"
        cat > "$out/.zshenv" <<EOF
        export STARSHIP_CONFIG=${devStarshipConfig}
        EOF
        cat > "$out/.zshrc" <<'EOF'
        if [[ -t 1 ]]; then
          fastfetch || true
        fi

        eval "$(${pkgsUnstable.starship}/bin/starship init zsh)"
        eval "$(${pkgsUnstable.atuin}/bin/atuin init zsh)"
        source <(${pkgsUnstable.carapace}/bin/carapace _carapace zsh)
        eval "$(zoxide init zsh)"

        autoload -Uz compinit && compinit
        zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}' 'r:|[._-]=* r:|=*'
        zstyle ':completion:*' menu select
        bindkey '^R' history-incremental-search-backward
        EOF
      '';

      devBashRc = pkgsUnstable.writeText "weasel-dev-bashrc" ''
        export WEASEL_OS_ROOT="''${WEASEL_OS_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
        export WEASEL_OS_HOST="''${WEASEL_OS_HOST:-''${HOSTNAME:-nixy-laptop}}"
        export STARSHIP_CONFIG=${devStarshipConfig}
        export ZDOTDIR=${devZshDotDir}

        if [[ -t 1 ]]; then
          fastfetch || true
        fi

        bind "set completion-ignore-case on" >/dev/null 2>&1 || true
        bind "set show-all-if-ambiguous on" >/dev/null 2>&1 || true
        shopt -s direxpand

        eval "$(${pkgsUnstable.starship}/bin/starship init bash --print-full-init)"
        eval "$(${pkgsUnstable.atuin}/bin/atuin init bash)"
        source <(${pkgsUnstable.carapace}/bin/carapace _carapace bash)
        eval "$(zoxide init bash)"

        alias sv='sudo nvim'
        alias fr='nh os switch --hostname "$WEASEL_OS_HOST" "$WEASEL_OS_ROOT"'
        alias fu='nh os switch --hostname "$WEASEL_OS_HOST" --update "$WEASEL_OS_ROOT"'
        alias ncg='nix-collect-garbage --delete-old && sudo nix-collect-garbage -d && sudo /run/current-system/bin/switch-to-configuration boot'
        alias v='nvim'
        alias cat='bat'
        alias ls='eza --icons --color=auto'
        alias ll='eza -lh --icons --grid --group-directories-first --color=auto'
        alias la='eza -lah --icons --grid --group-directories-first --color=auto'
        alias '..'='cd ..'
        alias zj='zellij'

        y() {
          local tmp="$(mktemp -t "yazi-cwd.XXXXXX")" cwd
          yazi "$@" --cwd-file="$tmp"
          if cwd="$(command cat -- "$tmp")" && [ -n "$cwd" ] && [ "$cwd" != "$PWD" ]; then
            builtin cd -- "$cwd"
          fi
          rm -f -- "$tmp"
        }
      '';

      devShellLauncher = pkgsUnstable.writeShellApplication {
        name = "weasel-dev-shell";
        runtimeInputs = devPackages;
        text = ''
          export WEASEL_OS_ROOT="''${WEASEL_OS_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
          export WEASEL_OS_HOST="''${WEASEL_OS_HOST:-''${HOSTNAME:-nixy-laptop}}"
          export STARSHIP_CONFIG=${devStarshipConfig}
          export ZDOTDIR=${devZshDotDir}
          exec ${pkgsUnstable.bashInteractive}/bin/bash --noprofile --rcfile ${devBashRc} -i
        '';
      };

      devShell = pkgsUnstable.mkShell {
        packages = devPackages;
        shellHook = ''
          export WEASEL_OS_ROOT="''${WEASEL_OS_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
          export WEASEL_OS_HOST="''${WEASEL_OS_HOST:-''${HOSTNAME:-nixy-laptop}}"
          export STARSHIP_CONFIG=${devStarshipConfig}
          export ZDOTDIR=${devZshDotDir}
          source ${devBashRc}
        '';
      };
    in {
      inherit devShell devShellLauncher pkgsStable pkgsUnstable;
    };
  };
}
