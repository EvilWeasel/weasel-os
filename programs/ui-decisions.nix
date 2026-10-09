{
  config,
  lib,
  pkgs,
  pkgsUnstable,
  ...
}:
let
  cfg = config.weasel.uiDecisions;
  package = pkgs.callPackage ../packages/computer-use-decisions { };
  protonPass = import ../packages/proton-pass-cli.nix { inherit pkgs pkgsUnstable; };
  client = pkgs.writeShellScriptBin "weasel-ui-decisions-mcp-client" ''
    TASK_DECISIONS_RUNTIME_DIR="''${XDG_RUNTIME_DIR:-/run/user/$UID}"
    exec ${package}/bin/weasel-ui-decisions-mcp \
      --socket "$TASK_DECISIONS_RUNTIME_DIR/weasel-ui-decisions/decisions.sock"
  '';
  launch = pkgs.writeShellScript "weasel-ui-decisions-launch" ''
    # Only the pass:// reference is visible here; pass-cli resolves it in its
    # masked child environment. Never use --no-masking or shell tracing.
    export PROTON_PASS_LINUX_KEYRING=dbus
    ${pkgs.python3}/bin/python - ${lib.escapeShellArg cfg.referenceEnvironmentFile} <<'PY'
    import os, stat, sys
    p = sys.argv[1]
    s = os.lstat(p)
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600:
        print("Optional Decisions reference file must be an owned regular mode-0600 file", file=sys.stderr)
        raise SystemExit(1)
    PY
    case "''${OPENAI_API_KEY-}" in
      pass://*) ;;
      *) echo "Optional Decisions requires the selected Proton Pass reference" >&2; exit 1 ;;
    esac
    exec ${protonPass}/bin/pass-cli run -- ${package}/bin/weasel-ui-decisions serve \
      --socket "$XDG_RUNTIME_DIR/weasel-ui-decisions/decisions.sock" \
      --state-dir ${lib.escapeShellArg cfg.stateDirectory} \
      --job-id ${lib.escapeShellArg cfg.jobId} \
      --prior-calls ${toString cfg.priorCalls} \
      --budget-usd ${lib.escapeShellArg cfg.budgetUsd} \
      --max-calls ${toString cfg.maxCalls} \
      ${lib.concatMapStringsSep " " (root: "--image-root ${lib.escapeShellArg root}") cfg.imageRoots}
  '';
in
{
  options.weasel.uiDecisions = {
    enable = lib.mkEnableOption "the optional paid UI evaluator";
    manageMcp = lib.mkEnableOption "an additive optional evaluator entry in Codex/T3's Codex config";
    referenceEnvironmentFile = lib.mkOption {
      type = lib.types.str;
      default = "${config.xdg.stateHome}/weasel-os/computer-use/2026-10-09/decisions/reference.env";
      description = "Owned private mode-0600 EnvironmentFile with ONLY OPENAI_API_KEY=pass://selected-reference; never a resolved key.";
    };
    stateDirectory = lib.mkOption {
      type = lib.types.str;
      default = "${config.xdg.stateHome}/weasel-os/computer-use/2026-10-09/decisions/ledger";
      description = "Existing persistent authorized ledger; never reset or move it to reset the budget.";
    };
    jobId = lib.mkOption {
      type = lib.types.str;
      default = "computer-use-20261009";
      description = "Persistent authorized budget identity; do not reset it on restart.";
    };
    priorCalls = lib.mkOption {
      type = lib.types.ints.unsigned;
      default = 2;
      description = "Already dispatched paid probes before ledger creation; persisted policy cannot change.";
    };
    maxCalls = lib.mkOption {
      type = lib.types.ints.positive;
      default = 200;
    };
    budgetUsd = lib.mkOption {
      type = lib.types.enum [
        "1"
        "5"
        "10"
      ];
      default = "10";
    };
    imageRoots = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Explicit absolute owned private capture/crop directories; empty disables images.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = lib.hasPrefix "/" cfg.referenceEnvironmentFile && lib.hasPrefix "/" cfg.stateDirectory;
        message = "UI Decisions reference EnvironmentFile and existing ledger must use explicit absolute paths.";
      }
      {
        assertion = cfg.maxCalls <= 200 && cfg.priorCalls <= cfg.maxCalls;
        message = "UI Decisions permits at most 200 calls including prior probes.";
      }
      {
        assertion = builtins.match "[A-Za-z0-9_.:-]{1,128}" cfg.jobId != null;
        message = "UI Decisions job identity must be a bounded ASCII identifier.";
      }
      {
        assertion = builtins.all (root: lib.hasPrefix "/" root) cfg.imageRoots;
        message = "UI Decisions capture roots must be explicit absolute paths.";
      }
    ];
    home.packages = [
      package
      client
    ];
    home.activation.configureUiDecisionsMcp = lib.mkIf cfg.manageMcp (
      lib.hm.dag.entryAfter [ "writeBoundary" "configureDesktopMcp" ] ''
        $DRY_RUN_CMD ${pkgs.python3}/bin/python ${../scripts/configure-ui-decisions.py} \
          --codex-home ${lib.escapeShellArg "${config.home.homeDirectory}/.codex"} \
          --command ${lib.escapeShellArg "${client}/bin/weasel-ui-decisions-mcp-client"}
      ''
    );
    systemd.user.services.weasel-ui-decisions = {
      Unit = {
        Description = "Optional UI Decisions evaluator, independent of desktop input";
        After = [ "graphical-session.target" ];
        PartOf = [ "graphical-session.target" ];
      };
      Service = {
        ExecStart = "${launch}";
        EnvironmentFile = cfg.referenceEnvironmentFile;
        Restart = "no";
        UMask = "0077";
        RuntimeDirectory = "weasel-ui-decisions";
        RuntimeDirectoryMode = "0700";
        TimeoutStopSec = "20s";
        KillMode = "control-group";
      };
      # No WantedBy: installation does not start API-capable processing. Start
      # this optional unit explicitly within the existing authorized job budget.
    };
  };
}
