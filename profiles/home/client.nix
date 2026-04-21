{ lib, pkgs, ... }:
{
  home.packages = [
    pkgs.deskflow
    pkgs.krita
    pkgs.telegram-desktop
  ];

  programs = {
    "dank-material-shell" = {
      enable = lib.mkDefault true;
      systemd = {
        enable = lib.mkDefault false;
        restartIfChanged = lib.mkDefault true;
      };
      enableDynamicTheming = lib.mkDefault true;
    };
    vscode = {
      enable = lib.mkDefault true;
      package = lib.mkDefault pkgs.vscode.fhs;
    };
  };
}
