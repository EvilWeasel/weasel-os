{
  config,
  pkgs,
  pkgsUnstable,
  host,
  lib,
  username,
  ...
}: let
  inherit (import ../../hosts/${host}/variables.nix) gitEmail gitSigningKey gitUsername;
  repoDefaultPath = "${config.home.homeDirectory}/weasel-os";
  signingEnabled = gitSigningKey != "";
in {
  nixpkgs.config = {
    allowUnfree = true;
    allowUnfreePredicate = _: true;
  };

  home = {
    username = username;
    homeDirectory = "/home/${username}";
    stateVersion = "24.11";
    packages = [
      (import ../../scripts/weasel-shell-helpers.nix {
        inherit config host pkgs pkgsUnstable;
      })
      (import ../../scripts/web-search.nix {inherit pkgs;})
      pkgs.age
      pkgs.sops
    ];
    sessionVariables = {
      WEASEL_OS_HOST = host;
      WEASEL_OS_ROOT = repoDefaultPath;
      WEASEL_DEBUG_HOME = "${config.home.homeDirectory}/weasel-debug";
      WEASEL_DEBUG_STATE = "${config.home.homeDirectory}/.local/state/weasel-debug";
    };
  };

  programs.git = {
    enable = true;
    settings.user =
      lib.optionalAttrs (gitUsername != "") {name = gitUsername;}
      // lib.optionalAttrs (gitEmail != "") {email = gitEmail;};
    signing = lib.mkIf signingEnabled {
      key = gitSigningKey;
      signByDefault = true;
    };
  };

  programs = {
    gh.enable = true;
    btop = {
      enable = true;
      settings.vim_keys = true;
    };
    home-manager.enable = true;
  };
}
