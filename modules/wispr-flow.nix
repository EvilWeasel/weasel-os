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
    # events for global push-to-talk. uaccess limits both grants to the active
    # local logind session; no permanent input-group membership is required.
    boot.kernelModules = [ "uinput" ];
    services.udev.extraRules = ''
      KERNEL=="uinput", SUBSYSTEM=="misc", OPTIONS+="static_node=uinput", TAG+="uaccess", GROUP="input", MODE="0660"
      SUBSYSTEM=="input", KERNEL=="event*", TAG+="uaccess", GROUP="input", MODE="0660"
    '';

    # The upstream AppImage deliberately uses --no-sandbox. The package patches
    # that out and points Electron at this root-owned NixOS sandbox wrapper.
    security.chromiumSuidSandbox.enable = true;
  };
}
