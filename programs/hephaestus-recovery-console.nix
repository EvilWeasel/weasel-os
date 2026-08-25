{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.weasel.hephaestusRecoveryConsole;
  recoveryLauncher = pkgs.writeShellScriptBin "codex-recovery" ''
    exec ${pkgs.bash}/bin/bash "$HOME/recovery/hephaestus-codex/bin/codex-recovery" "$@"
  '';
in
{
  options.weasel.hephaestusRecoveryConsole = {
    enable = lib.mkEnableOption "the human-invoked hephaestus Codex recovery console";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.codex;
      description = "Pinned Codex CLI from this flake's locked nixpkgs input.";
    };
  };

  config = lib.mkIf cfg.enable {
    # This is an immutable, reviewed prompt/runbook bundle. It is deliberately
    # not a credential source, SSH configuration, NetBird policy, or actuator.
    home.file."recovery/hephaestus-codex" = {
      source = ../recovery/hephaestus-codex;
      recursive = true;
    };

    home.packages = [
      cfg.package
      pkgs.git
      pkgs.openssh
      recoveryLauncher
    ];

    # This identity has no SSH configuration or authorized-key deployment in
    # this module. Its public half is handed to the future Iris forced-command
    # broker separately; keeping generation here prevents private-key material
    # from ever entering the Nix store or Git.
    home.activation.ensureIrisRecoveryKey = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      key_path="$HOME/.ssh/id_ed25519_iris_recovery"
      public_key_path="$key_path.pub"

      if test -e "$key_path" && ! test -f "$key_path"; then
        echo "Refusing non-regular recovery key path: $key_path" >&2
        exit 1
      fi
      if test -L "$key_path"; then
        echo "Refusing symlinked recovery key path: $key_path" >&2
        exit 1
      fi

      ${pkgs.coreutils}/bin/mkdir -p -m 0700 "$HOME/.ssh"
      if ! test -e "$key_path"; then
        umask 077
        ${pkgs.openssh}/bin/ssh-keygen -q -t ed25519 -N "" -C "nixy-laptop-iris-recovery" -f "$key_path"
      fi
      ${pkgs.coreutils}/bin/chmod 0600 "$key_path"

      if ! test -e "$public_key_path"; then
        public_key_tmp="$public_key_path.tmp.$$"
        ${pkgs.openssh}/bin/ssh-keygen -y -f "$key_path" > "$public_key_tmp"
        ${pkgs.coreutils}/bin/chmod 0644 "$public_key_tmp"
        ${pkgs.coreutils}/bin/mv "$public_key_tmp" "$public_key_path"
      fi
    '';
  };
}
