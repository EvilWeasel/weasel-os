{
  config,
  pkgs,
  pkgsUnstable,
  ...
}:
let
  repoDefaultPath = "${config.home.homeDirectory}/weasel-os";
  sshInitKeysCmd = "systemctl --user start ssh-agent.service >/dev/null 2>&1; export SSH_AUTH_SOCK=/run/user/$UID/ssh-agent; find \"$HOME/.ssh\" -maxdepth 1 -type f ! -name '*.pub' ! -name 'authorized_keys*' ! -name 'known_hosts*' ! -name 'config' -exec sh -c 'for key do ssh-keygen -yf \"$key\" >/dev/null 2>&1 && ssh-add \"$key\"; done' sh {} +";
in
{
  home = {
    file.".npmrc".text = ''
      prefix=${config.home.homeDirectory}/.npm-global
    '';
    packages = [
      pkgs.mcp-nixos
      pkgs.playwright-driver
      pkgs.sweethome3d.application
      pkgsUnstable.ratty
      pkgsUnstable.dgop
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
      enableSystemMonitoring = true;
      enableVPN = true;
      enableAudioWavelength = true;
      enableCalendarEvents = true;
      plugins = {
        DockerManager.src = pkgs.fetchFromGitHub {
          owner = "LuckShiba";
          repo = "DmsDockerManager";
          rev = "f6f7d94c84510da098980a2bb733137e90f98fd8";
          sha256 = "sha256-KEj0d1K0+ZOxbQ9FLzapWZ82i31hbpEHUAOZfJF8IGs=";
        };
        WebSearch.src = pkgs.fetchFromGitHub {
          owner = "devnullvoid";
          repo = "dms-web-search";
          rev = "821f5b437ea96739ce1cbc85ce324fb55e8884bb";
          sha256 = "sha256-UqFgAjW2A75dtlvOZkq4Vv/v/DROoc/ouCXBaVlksPI=";
        };
        CommandRunner.src = pkgs.fetchFromGitHub {
          owner = "devnullvoid";
          repo = "dms-command-runner";
          rev = "ea59490eede60d7dc87697b670f1eccc6ad54593";
          sha256 = "sha256-EmYYvPvSwG7ELTgRS6tcVEqFgyk8uYiB491Gp7nkPvs=";
        };
        EmojiLauncher.src = pkgs.fetchFromGitHub {
          owner = "devnullvoid";
          repo = "dms-emoji-launcher";
          rev = "8ff394e3ddfcb2fd755ed2e7b4c6f01f3e26e596";
          sha256 = "sha256-fmIddCvACwO8wbAtLBMtDnEXXQJjb7+o2s4jW3f8VIU=";
        };
        Calculator.src = pkgs.fetchFromGitHub {
          owner = "rochacbruno";
          repo = "DankCalculator";
          rev = "c9fbbe921e9afeb92f4e92390e9fc05f006f0373";
          sha256 = "sha256-dqFTvNogWsqK82EhgMIbJB70R5TgcRiA3Elx1LkSia8=";
        };
        NiriWindows.src = pkgs.fetchFromGitHub {
          owner = "rochacbruno";
          repo = "DankNiriWindows";
          rev = "411d5ee9f7707029f4c12c824ec3b24ca6756a0d";
          sha256 = "sha256-+Ju8cbw1yWWW2K2Gpl7nTdkjINqXBD4ktl5g8OhuIEg=";
        };
      };
    };
    vscode.package = pkgsUnstable.vscode.fhs;
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

  # Preserve the existing active paused actors across this release migration.
  # sd-switch reads this policy from Unit, not Service. Review 2026-10-11;
  # adopting new running actor binaries requires separate pause-safe coordination.
  systemd.user.services = {
    weasel-computer-use.Unit.X-SwitchMethod = "keep-old";
    cua-driver.Unit.X-SwitchMethod = "keep-old";
    weasel-ui-decisions.Unit.X-SwitchMethod = "keep-old";
  };

  xdg.configFile."ratty/ratty.toml" = {
    source = config.lib.file.mkOutOfStoreSymlink "${repoDefaultPath}/programs/ratty/ratty.toml";
    force = true;
  };
}
