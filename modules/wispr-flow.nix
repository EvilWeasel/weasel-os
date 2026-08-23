{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.weasel.wispr-flow;
  wisprFlow = pkgs.callPackage ../packages/wispr-flow/default.nix { };
in
{
  options.weasel.wispr-flow.enable = lib.mkEnableOption "Wispr Flow voice dictation";

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ wisprFlow ];

    # Wispr's Wayland helper injects text through uinput and monitors input
    # events for global push-to-talk. The package's 70-* rule runs before
    # systemd's seat-late rule, so uaccess can grant active-session ACLs without
    # permanent input-group membership.
    boot.kernelModules = [ "uinput" ];
    services.udev.packages = [ wisprFlow ];

    # The upstream AppImage deliberately uses --no-sandbox. The package patches
    # that out and points Electron at this root-owned NixOS sandbox wrapper.
    security.chromiumSuidSandbox.enable = true;
  };
}
