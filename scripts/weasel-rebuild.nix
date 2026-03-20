{config, host, pkgs}:
let
  repoDefaultPath = "${config.home.homeDirectory}/weasel-os";
  resolveRoot = ''
    resolve_weasel_os_root() {
      if [ -n "$WEASEL_OS_ROOT" ] && [ -f "$WEASEL_OS_ROOT/flake.nix" ]; then
        printf '%s\n' "$WEASEL_OS_ROOT"
        return 0
      fi

      local git_root=""
      git_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
      if [ -n "$git_root" ] && [ -f "$git_root/flake.nix" ] && [ -d "$git_root/hosts" ] && [ -d "$git_root/programs" ]; then
        printf '%s\n' "$git_root"
        return 0
      fi

      printf '%s\n' "${repoDefaultPath}"
    }
  '';
  mkCommand = {name, update ? false}:
    pkgs.writeShellScriptBin name ''
      set -euo pipefail
      ${resolveRoot}

      repo_root="$(resolve_weasel_os_root)"
      exec ${pkgs.nh}/bin/nh os switch --hostname "${host}" ${if update then "--update " else ""}"$repo_root"
    '';
in
pkgs.symlinkJoin {
  name = "weasel-rebuild";
  paths = [
    (mkCommand {name = "fr";})
    (mkCommand {name = "fu"; update = true;})
  ];
}
