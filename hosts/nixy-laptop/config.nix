{
  config,
  lib,
  pkgs,
  ...
}:
{
  imports = [
    ../../profiles/system/common.nix
    ../../profiles/system/base.nix
    ../../profiles/system/client.nix
    ../../profiles/system/laptop.nix
    # ../../modules/networking/internal-dns.nix
    ./hardware.nix
    ./users.nix
  ];

  hardware.nvidia.package = lib.mkForce config.boot.kernelPackages.nvidiaPackages.production;

  # Only the RPM payload is installed. Its scriptlets would otherwise add an
  # imperative OpenAI DNF repository and updater outside the flake.
  environment.systemPackages = [
    (pkgs.callPackage ../../packages/chatgpt/default.nix { })
  ];
}
