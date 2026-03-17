{pkgs, ...}: {
  home.packages = [pkgs.alejandra];

  xdg.configFile."Code/User/settings.json" = {
    force = true;
    source = ./vscode/settings.json;
  };
}
