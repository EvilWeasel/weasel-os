{
  config,
  lib,
  pkgs,
  ...
}:
{
  # Expose only the laptop's loopback MT server to the private Hephaestus
  # connection adapter. Reuse the existing pinned SSH host and identity.
  systemd.user.services.mt-hephaestus-laptop-tunnel = {
    Unit = {
      Description = "Private MT Code laptop route for Hephaestus";
      After = [ "network-online.target" ];
    };
    Service = {
      ExecStart = "${pkgs.openssh}/bin/ssh -NT -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -R 127.0.0.1:3879:127.0.0.1:3773 hephaestus-root";
      Restart = "always";
      RestartSec = "10s";
      UMask = "0077";
    };
    Install.WantedBy = [ "default.target" ];
  };

  # Keep provider read access separate from the user's existing rules. This
  # does not permit billing, monitors, login, or arbitrary Parallel commands.
  home.file.".codex/rules/parallel-search.rules".source = ./parallel-search.rules;
  home.packages = [ (import ../scripts/codex-artifact-run.nix { inherit pkgs; }) ];

  # Electron can overwrite its own desktop ID with a hidden protocol handler.
  # Separate launcher IDs stay visible without changing protocol associations.
  xdg.dataFile."applications/weasel-t3code.desktop" = {
    force = true;
    text = ''
      [Desktop Entry]
      Type=Application
      Name=T3 Code
      Exec=/run/current-system/sw/bin/t3code %U
      Icon=applications-development
      Terminal=false
      Categories=Development;IDE;
    '';
  };
  xdg.dataFile."applications/weasel-mtcode.desktop" = {
    force = true;
    text = ''
      [Desktop Entry]
      Type=Application
      Name=MT Code
      Exec=/run/current-system/sw/bin/mtcode %U
      Icon=mtcode
      Terminal=false
      Categories=Development;IDE;
    '';
  };

  # T3's Codex provider reads the same global instructions as the other Codex
  # clients. Merge only our delimited knowledge bridge into the mutable file.
  home.activation.configureT3SharedContext = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    $DRY_RUN_CMD ${pkgs.python3}/bin/python ${../scripts/configure-t3-context.py} \
      --codex-home ${lib.escapeShellArg "${config.home.homeDirectory}/.codex"}
  '';
}
