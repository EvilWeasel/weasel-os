{
  inputs,
  lib,
  pkgs,
  ...
}:
let
  hermesDesktop = inputs.hermes-agent.packages.${pkgs.stdenv.hostPlatform.system}.desktop;
  netbirdUi = pkgs.callPackage ../../packages/netbird-ui-bin.nix {
    daemonSocket = "unix:///var/run/netbird-personal/sock";
  };
  netbirdUiLauncher = pkgs.writeShellScript "netbird-ui-launcher" ''
    set -eu

    for _ in {1..120}; do
      if [[ -S /var/run/netbird-personal/sock ]]; then
        # 0.77.x can fall back to the default socket despite NB_DAEMON_ADDR.
        exec ${lib.getExe netbirdUi} \
          --daemon-addr=unix:///var/run/netbird-personal/sock
      fi
      ${pkgs.coreutils}/bin/sleep 1
    done

    echo "NetBird daemon socket did not appear within 120 seconds" >&2
    exit 1
  '';
in
{
  imports = [
    ../../profiles/home/common.nix
    ../../profiles/home/base.nix
    ../../profiles/home/client.nix
    ../../profiles/home/laptop.nix
    ../../programs/hephaestus-recovery-console.nix
  ];

  home.packages = [
    hermesDesktop
  ];

  # Disable the package's unordered XDG autostart. It can race the hardened
  # daemon and then remain disconnected until manually restarted.
  xdg.configFile."autostart/netbird.desktop" = {
    force = true;
    text = ''
      [Desktop Entry]
      Type=Application
      Name=NetBird (managed by systemd)
      Hidden=true
      NoDisplay=true
    '';
  };

  # Preserve Home Manager's stale backup outside the autostart directory so
  # systemd-xdg-autostart-generator cannot launch a second, obsolete UI.
  home.activation.archiveLegacyNetbirdAutostart = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    legacy="$HOME/.config/autostart/netbird.desktop.hm-backup"
    archive="$HOME/.local/state/weasel-os/netbird.desktop.hm-backup"
    if [[ -e "$legacy" ]]; then
      $DRY_RUN_CMD ${pkgs.coreutils}/bin/mkdir -p "$HOME/.local/state/weasel-os"
      $DRY_RUN_CMD ${pkgs.coreutils}/bin/mv --backup=numbered -T "$legacy" "$archive"
    fi
  '';

  # The UI is a tray process and must start only after the custom daemon socket
  # exists. A clean user-initiated quit remains respected (Restart=on-failure).
  systemd.user.services.netbird-ui = {
    Unit = {
      Description = "NetBird tray for the personal client";
      After = [ "graphical-session.target" ];
      PartOf = [ "graphical-session.target" ];
    };
    Service = {
      Environment = [ "WEBKIT_DISABLE_DMABUF_RENDERER=1" ];
      ExecStart = netbirdUiLauncher;
      Restart = "on-failure";
      RestartSec = "5s";
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };

  xdg.desktopEntries.hermes-desktop = {
    name = "Hermes";
    comment = "Hermes Agent desktop application";
    exec = "${hermesDesktop}/bin/hermes-desktop";
    icon = "${hermesDesktop}/share/hermes-desktop/dist/hermes.png";
    terminal = false;
    categories = [
      "Development"
      "Utility"
    ];
    startupNotify = true;
  };

  weasel.hephaestusRecoveryConsole.enable = true;
}
