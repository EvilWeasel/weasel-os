{
  config,
  pkgs,
  ...
}:
let
  helixLanguagesPath = "${config.home.homeDirectory}/weasel-os/programs/helix/languages.toml";
in
{
  home.packages = [ pkgs.helix ];

  xdg.configFile."helix/languages.toml" = {
    force = true;
    source = config.lib.file.mkOutOfStoreSymlink helixLanguagesPath;
  };
}
