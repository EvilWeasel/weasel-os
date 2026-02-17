{
  config,
  pkgs,
  ...
}:
let
  repoSettingsPath = "${config.home.homeDirectory}/weasel-os/programs/vscode/settings.json";
in
{
  home.packages = [ pkgs.alejandra ];

  xdg.configFile."Code/User/settings.json" = {
    force = true;
    source = config.lib.file.mkOutOfStoreSymlink repoSettingsPath;
  };
}
