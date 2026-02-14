# modules/llama-cpp.nix
{
  config,
  lib,
  pkgs,
  utils,
  ...
}:
let
  cfg = config.services.llama-cpp;

  # Optional: convert a Nix attrset to an INI file for llama-server router presets.
  # This matches how newer nixpkgs master implements presets. (Backport pattern.)
  modelsPresetFile =
    if cfg.modelsPreset != null then
      pkgs.writeText "llama-models.ini" (lib.generators.toINI { } cfg.modelsPreset)
    else
      null;

  # Build a single ExecStart with proper shell escaping.
  # We intentionally do NOT force --log-disable here; add it via extraFlags if you want it.
  execStart =
    let
      baseArgs = [
        "--host"
        cfg.host
        "--port"
        (toString cfg.port)
      ];

      modelArgs = lib.optionals (cfg.model != null) [
        "-m"
        cfg.model
      ];

      routerArgs =
        (lib.optionals (cfg.modelsDir != null) [
          "--models-dir"
          cfg.modelsDir
        ])
        ++ (lib.optionals (cfg.modelsPreset != null) [
          "--models-preset"
          modelsPresetFile
        ]);

      args = baseArgs ++ modelArgs ++ routerArgs ++ cfg.extraFlags;
    in
    "${cfg.package}/bin/llama-server ${utils.escapeSystemdExecArgs args}";
in
{
  # Replace the built-in stable module with this one.
  # This is the documented NixOS mechanism for module replacement.
  disabledModules = [ "services/misc/llama-cpp.nix" ];

  options.services.llama-cpp = {
    enable = lib.mkEnableOption "llama.cpp llama-server (OpenAI-compatible HTTP server)";
    autoStart = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Whether to automatically start the llama-cpp service.";
    };

    restartPolicy = lib.mkOption {
      type = lib.types.enum [
        "on-failure"
        "no"
      ];
      default = "on-failure";
      description = "The restart policy for the llama-cpp service.";
    };

    package = lib.mkPackageOption pkgs "llama-cpp" { };

    # Use string/path-like values; avoid Nix path literals for huge GGUFs.
    model = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      example = "/var/lib/llama-cpp/models/qwen2.5-3b-instruct-q4_k_m.gguf";
      description = "Path to a GGUF model. If null, llama-server runs in router mode.";
    };

    # Router mode helpers (optional). llama-server supports --models-dir and --models-preset.
    modelsDir = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      example = "/var/lib/llama-cpp/models";
      description = "Directory to load models from in router mode (llama-server --models-dir).";
    };

    modelsPreset = lib.mkOption {
      type = lib.types.nullOr (lib.types.attrsOf lib.types.attrs);
      default = null;
      description = ''
        Attrset converted to an INI file and passed as --models-preset.
        Useful for declarative multi-model setups later.
      '';
      example = lib.literalExpression ''
        {
          "qwen3b" = {
            model = "/var/lib/llama-cpp/models/qwen2.5-3b-instruct-q4_k_m.gguf";
            jinja = "on";
            n-gpu-layers = "auto";
            c = "4096";
          };
        }
      '';
    };

    extraFlags = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Extra CLI flags passed to llama-server.";
      example = [
        "--jinja"
        "-c"
        "4096"
        "-ngl"
        "auto"
      ];
    };

    host = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
      description = "Listen address.";
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 8080;
      description = "Listen port.";
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Open the port in the firewall.";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd = {
      tmpfiles.rules = [
        "d /var/lib/llama-cpp/models 0770 root llama -"
      ];
      services.llama-cpp = {
        description = "llama.cpp llama-server";
        after = [ "network.target" ];
        wantedBy = lib.optionals cfg.autoStart [ "multi-user.target" ];

        serviceConfig = {
          Type = "idle";
          KillSignal = "SIGINT";
          ExecStart = execStart;

          Restart = cfg.restartPolicy;
          RestartSec = 10;

          SupplementaryGroups = [ "llama" ];
          UMask = "0007";

          # Make it usable for GPU acceleration (NixOS upstream uses this for lock-down + GPU access).
          PrivateDevices = false;

          # These dirs fix common “no writable cache/home” problems and match newer upstream design.
          StateDirectory = "llama-cpp";
          CacheDirectory = "llama-cpp";
          WorkingDirectory = "/var/lib/llama-cpp";

          # llama-server uses LLAMA_CACHE to control cached models (router mode).
          Environment = [
            "LLAMA_CACHE=/var/cache/llama-cpp"
            "HOME=/var/lib/llama-cpp"
            "XDG_CACHE_HOME=/var/cache/llama-cpp"
          ];

          # Hardening baseline (copied from stable nixos-25.11 module).
          DynamicUser = true;
          CapabilityBoundingSet = "";
          RestrictAddressFamilies = [
            "AF_INET"
            "AF_INET6"
            "AF_UNIX"
          ];
          NoNewPrivileges = true;
          PrivateMounts = true;
          PrivateTmp = true;
          PrivateUsers = true;
          ProtectClock = true;
          ProtectControlGroups = true;
          ProtectHome = true;
          ProtectKernelLogs = true;
          ProtectKernelModules = true;
          ProtectKernelTunables = true;
          ProtectSystem = "strict";
          MemoryDenyWriteExecute = true;
          LockPersonality = true;
          RemoveIPC = true;
          RestrictNamespaces = true;
          RestrictRealtime = true;
          RestrictSUIDSGID = true;
          SystemCallArchitectures = "native";
          SystemCallFilter = [
            "@system-service"
            "~@privileged"
          ];
          SystemCallErrorNumber = "EPERM";
          ProtectProc = "invisible";
          ProtectHostname = true;
          ProcSubset = "pid";
        };
      };
    };

    networking.firewall = lib.mkIf cfg.openFirewall {
      allowedTCPPorts = [ cfg.port ];
    };
  };
}
