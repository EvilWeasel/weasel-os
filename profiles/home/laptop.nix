{
  config,
  pkgs,
  pkgsUnstable,
  ...
}: let
  sshInitKeysCmd = "systemctl --user start ssh-agent.service >/dev/null 2>&1; export SSH_AUTH_SOCK=/run/user/$UID/ssh-agent; find \"$HOME/.ssh\" -maxdepth 1 -type f ! -name '*.pub' ! -name 'authorized_keys*' ! -name 'known_hosts*' ! -name 'config' -exec sh -c 'for key do ssh-keygen -yf \"$key\" >/dev/null 2>&1 && ssh-add \"$key\"; done' sh {} +";
in {
  home = {
    file.".npmrc".text = ''
      prefix=${config.home.homeDirectory}/.npm-global
    '';
    packages = [
      pkgs.mcp-nixos
      pkgs.playwright-driver
    ];
    sessionPath = [
      "${config.home.homeDirectory}/.npm-global/bin"
    ];
    sessionVariables = {
      PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
      PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1";
    };
  };

  programs = {
    "dank-material-shell" = {
      enable = true;
      systemd = {
        enable = false;
        restartIfChanged = true;
      };
      enableSystemMonitoring = true;
      dgop.package = pkgsUnstable.dgop;
      enableVPN = true;
      enableDynamicTheming = false;
      enableAudioWavelength = true;
      enableCalendarEvents = true;
      plugins = {
        DockerManager.src = pkgs.fetchFromGitHub {
          owner = "LuckShiba";
          repo = "DmsDockerManager";
          rev = "v1.2.0";
          sha256 = "sha256-VoJCaygWnKpv0s0pqTOmzZnPM922qPDMHk4EPcgVnaU=";
        };
        WebSearch.src = pkgs.fetchFromGitHub {
          owner = "devnullvoid";
          repo = "dms-web-search";
          rev = "81ccd9f";
          sha256 = "sha256-mKbmROijhYhy/IPbVxYbKyggXesqVGnS/AfAEyeQVhg=";
        };
        CommandRunner.src = pkgs.fetchFromGitHub {
          owner = "devnullvoid";
          repo = "dms-command-runner";
          rev = "d89a094";
          sha256 = "sha256-tXqDRVp1VhyD1WylW83mO4aYFmVg/NV6Z/toHmb5Tn8=";
        };
        EmojiLauncher.src = pkgs.fetchFromGitHub {
          owner = "devnullvoid";
          repo = "dms-emoji-launcher";
          rev = "2951ec7";
          sha256 = "sha256-aub5pXRMlMs7dxiv5P+/Rz/dA4weojr+SGZAItmbOvo=";
        };
        Calculator.src = pkgs.fetchFromGitHub {
          owner = "rochacbruno";
          repo = "DankCalculator";
          rev = "de6dbd5";
          sha256 = "sha256-Vq+E2F2Ym5JdzjpCusRMDXd6uuAhhjAehyD/tO3omdY=";
        };
        NiriWindows.src = pkgs.fetchFromGitHub {
          owner = "rochacbruno";
          repo = "DankNiriWindows";
          rev = "b845277";
          sha256 = "sha256-rdZAnkRyfycI2a2wjSiepQwRI49zKbwoRzpz1+c6ZJA=";
        };
      };
    };
    vscode = {
      enable = true;
      package = pkgsUnstable.vscode.fhs;
    };
    direnv = {
      enable = true;
      nix-direnv.enable = true;
    };
    zsh.shellAliases = {
      codex-gpg-warmup = ''
        export GPG_TTY="$(tty)"; \
        gpg-connect-agent updatestartuptty /bye >/dev/null; \
        echo "codex warmup $(date -Is)" | gpg --clearsign >/dev/null; \
        echo "GPG cache warmed"
      '';
      shader-log = "tail -f ~/.steam/root/logs/shader_log.txt";
      ssh-initkeys = sshInitKeysCmd;
    };
    bash.shellAliases = {
      codex-gpg-warmup = ''
        export GPG_TTY="$(tty)"; \
        gpg-connect-agent updatestartuptty /bye >/dev/null; \
        echo "codex warmup $(date -Is)" | gpg --clearsign >/dev/null; \
        echo "GPG cache warmed"
      '';
      shader-log = "tail -f ~/.steam/root/logs/shader_log.txt";
      ssh-initkeys = sshInitKeysCmd;
    };
  };
}
