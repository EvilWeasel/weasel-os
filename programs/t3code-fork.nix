{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.weasel.t3Fork;
  recipeRevision = "18729368e840543aa1375948da849b184ddd95bd";
  installer = pkgs.fetchurl {
    url = "https://raw.githubusercontent.com/morrowbyte/t3code/${recipeRevision}/packaging/nixos/install.sh";
    hash = "sha256-xgE1hyKti5HPHnq9vRKGPosxxG4zdgtO9Jww9YUVznE=";
  };
  updater = pkgs.writeShellApplication {
    name = "t3code-weasel-update";
    runtimeInputs = with pkgs; [
      bash
      curl
      jq
      coreutils
      util-linux
      nix
      zstd
    ];
    text = ''
      export T3_WEASEL_REPOSITORY=${lib.escapeShellArg cfg.repository}
      export T3_WEASEL_CHANNEL=${lib.escapeShellArg cfg.channel}
      export T3_WEASEL_DATA_DIR=${lib.escapeShellArg cfg.dataDirectory}
      export T3_WEASEL_MANAGED=1
      # Import the release closure built on Namespace. The helper also exposes
      # separate --prepare/--activate verbs for the desktop updater.
      exec bash ${installer} "$@"
    '';
  };
  launcher = pkgs.writeShellApplication {
    name = "t3code-weasel";
    runtimeInputs = [ pkgs.coreutils ];
    text = ''
      # Preserve the user's existing account/transcription launcher when present.
      legacy="$HOME/.local/bin/t3code-weasel"
      if [[ -x "$legacy" && "$(readlink -f "$legacy")" != "$(readlink -f "$0")" ]]; then
        exec "$legacy" "$@"
      fi
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
    xdg.desktopEntries.t3code-weasel = {
      name = "T3 Code · Morrowbyte";
      exec = "${launcher}/bin/t3code-weasel %U";
      icon = "${../pictures/t3code-fork.svg}";
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
