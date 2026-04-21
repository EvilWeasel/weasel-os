{
  config,
  pkgs,
  ...
}: let
  vscodeSettingsPath = "${config.home.homeDirectory}/weasel-os/programs/vscode/settings.json";
in {
  home.packages = [pkgs.nixfmt-rfc-style];

  xdg.configFile."Code/User/settings.json" = {
    force = true;
    source = config.lib.file.mkOutOfStoreSymlink vscodeSettingsPath;
  };
}
