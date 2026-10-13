{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.weasel.t3Fork;
  recipeRevision = "a37df4a04247fea01340b2546e99bb4c4f6ffb1b";
  installer = pkgs.fetchurl {
    url = "https://raw.githubusercontent.com/morrowbyte/t3code/${recipeRevision}/packaging/nixos/install.sh";
    hash = "sha256-vWrvJyvrF8bwSzNZ1qX2B+KOZ7I0mOR9QmirT7hqH1c=";
  };
  recipe = pkgs.fetchurl {
    url = "https://raw.githubusercontent.com/morrowbyte/t3code/${recipeRevision}/packaging/nixos/flake.nix";
    hash = "sha256-YNJM5sEHIHS2G9cPS5jc6L/HhCp0PH8eQq6XMDFnjUc=";
  };
  bundle = pkgs.runCommand "t3code-fork-updater-source" { } ''
    mkdir -p "$out"
    cp ${installer} "$out/install.sh"
    cp ${recipe} "$out/flake.nix"
  '';
  updater = pkgs.writeShellApplication {
    name = "t3code-weasel-update";
    runtimeInputs = with pkgs; [
      bash
      curl
      jq
      coreutils
      util-linux
      nix
    ];
    text = ''
      export T3_WEASEL_REPOSITORY=${lib.escapeShellArg cfg.repository}
      export T3_WEASEL_CHANNEL=${lib.escapeShellArg cfg.channel}
      export T3_WEASEL_DATA_DIR=${lib.escapeShellArg cfg.dataDirectory}
      export T3_WEASEL_MANAGED=1
      exec bash ${bundle}/install.sh "$@"
    '';
  };
  launcher = pkgs.writeShellApplication {
    name = "t3code-weasel";
    text = ''
      export T3CODE_HOME=${lib.escapeShellArg cfg.dataDirectory}
      if [[ ! -x "$T3CODE_HOME/current/bin/t3code-weasel" ]]; then
        echo 'Fork not prepared yet. Run t3code-weasel-update, then launch again.' >&2
        exit 1
      fi
      exec "$T3CODE_HOME/current/bin/t3code-weasel" "$@"
    '';
  };
in
{
  options.weasel.t3Fork = {
    enable = lib.mkEnableOption "the independently updated T3 Code fork";
    repository = lib.mkOption {
      type = lib.types.str;
      default = "morrowbyte/t3code";
    };
    channel = lib.mkOption {
      type = lib.types.enum [
        "nightly"
        "stable"
      ];
      default = "nightly";
    };
    dataDirectory = lib.mkOption {
      type = lib.types.str;
      default = "${config.home.homeDirectory}/.local/share/t3code-weasel";
      description = "Existing fork profile and version roots; keep fixed to preserve identity.";
    };
    autoUpdate = lib.mkOption {
      type = lib.types.bool;
      default = true;
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = pkgs.stdenv.hostPlatform.system == "x86_64-linux";
        message = "The fork updater currently supports x86_64 Linux only.";
      }
    ];
    home.packages = [
      launcher
      updater
    ];
    xdg.desktopEntries.t3code-fork = {
      name = "T3 Code Fork";
      exec = "${launcher}/bin/t3code-weasel %U";
      icon = "applications-development";
      terminal = false;
      categories = [
        "Development"
        "IDE"
      ];
    };
    systemd.user.services.t3code-fork-update = lib.mkIf cfg.autoUpdate {
      Unit.Description = "Prepare the next T3 Code fork release without restarting sessions";
      Service = {
        Type = "oneshot";
        ExecStart = "${updater}/bin/t3code-weasel-update --update";
        UMask = "0077";
        TimeoutStartSec = "20min";
      };
    };
    systemd.user.timers.t3code-fork-update = lib.mkIf cfg.autoUpdate {
      Unit.Description = "Check the T3 Code fork release channel hourly";
      Timer = {
        OnCalendar = "hourly";
        OnBootSec = "2min";
        RandomizedDelaySec = "5min";
        Persistent = true;
      };
      Install.WantedBy = [ "timers.target" ];
    };
  };
}
