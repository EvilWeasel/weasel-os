{ inputs, pkgs, ... }:
let
  hermesDesktop = inputs.hermes-agent.packages.${pkgs.stdenv.hostPlatform.system}.desktop;
in
{
  imports = [
    ../../profiles/home/common.nix
    ../../profiles/home/base.nix
    ../../profiles/home/client.nix
    ../../profiles/home/laptop.nix
  ];

  home.packages = [
    hermesDesktop
    pkgs.caddy
  ];

  xdg.configFile."caddy/hermes-remote.Caddyfile".text = ''
    {
      admin off
      auto_https off
    }

    http://127.0.0.1:9119 {
      bind 127.0.0.1

      reverse_proxy http://127.0.0.1:9120 {
        header_up Host 10.145.80.4:9119
      }
    }
  '';

  systemd.user.services.hermes-blain-tunnel = {
    Unit = {
      Description = "SSH tunnel to Hermes on blain-ai";
      Wants = [ "network-online.target" ];
      After = [ "network-online.target" ];
    };
    Service = {
      ExecStart = "${pkgs.openssh}/bin/ssh -N -T -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=yes -L 127.0.0.1:9120:10.145.80.4:9119 blain-ai";
      Restart = "always";
      RestartSec = "5s";
    };
    Install.WantedBy = [ "default.target" ];
  };

  systemd.user.services.hermes-remote-bridge = {
    Unit = {
      Description = "Local bridge for Hermes Desktop remote gateway";
      Wants = [ "hermes-blain-tunnel.service" ];
      After = [ "hermes-blain-tunnel.service" ];
    };
    Service = {
      ExecStart = "${pkgs.caddy}/bin/caddy run --config %h/.config/caddy/hermes-remote.Caddyfile --adapter caddyfile";
      ExecReload = "${pkgs.caddy}/bin/caddy reload --config %h/.config/caddy/hermes-remote.Caddyfile --adapter caddyfile --force";
      Restart = "always";
      RestartSec = "5s";
    };
    Install.WantedBy = [ "default.target" ];
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
}
