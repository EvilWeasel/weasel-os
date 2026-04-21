{
  config,
  ...
}: let
  zedSettingsPath = "${config.home.homeDirectory}/weasel-os/programs/zed/settings.json";
in {
  xdg.configFile."zed/settings.json" = {
    force = true;
    source = config.lib.file.mkOutOfStoreSymlink zedSettingsPath;
  };
}
