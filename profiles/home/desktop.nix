{pkgs, ...}: {
  programs = {
    "dank-material-shell" = {
      enable = true;
      systemd = {
        enable = false;
        restartIfChanged = true;
      };
      enableSystemMonitoring = false;
      enableVPN = false;
      enableDynamicTheming = true;
      enableAudioWavelength = false;
      enableCalendarEvents = false;
    };
    vscode = {
      enable = true;
      package = pkgs.vscode.fhs;
    };
  };
}
