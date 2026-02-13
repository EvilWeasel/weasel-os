{
  lib,
  pkgs,
  ...
}: let
  settingsJson = builtins.readFile ./vscode/settings.json;
  renderedSettings =
    lib.replaceStrings
    ["@ALEJANDRA@"]
    ["${pkgs.alejandra}/bin/alejandra"]
    settingsJson;
in {
  xdg.configFile."Code/User/settings.json" = {
    force = true;
    text = renderedSettings;
  };
}
