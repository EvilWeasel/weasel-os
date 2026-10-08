{
  config,
  lib,
  pkgs,
  ...
}:
{
  # Keep provider read access separate from the user's existing rules. This
  # does not permit billing, monitors, login, or arbitrary Parallel commands.
  home.file.".codex/rules/parallel-search.rules".source = ./parallel-search.rules;
  home.packages = [ (import ../scripts/codex-artifact-run.nix { inherit pkgs; }) ];

  # T3's Codex provider reads the same global instructions as the other Codex
  # clients. Merge only our delimited knowledge bridge into the mutable file.
  home.activation.configureT3SharedContext = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    $DRY_RUN_CMD ${pkgs.python3}/bin/python ${../scripts/configure-t3-context.py} \
      --codex-home ${lib.escapeShellArg "${config.home.homeDirectory}/.codex"}
  '';
}
