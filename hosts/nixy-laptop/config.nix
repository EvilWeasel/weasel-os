{
  config,
  lib,
  ...
}: {
  imports = [
    ../../profiles/system/common.nix
    ../../profiles/system/base.nix
    ../../profiles/system/laptop.nix
    ../../modules/networking/internal-dns.nix
    ./hardware.nix
    ./users.nix
  ];

  hardware.nvidia.package = lib.mkForce config.boot.kernelPackages.nvidiaPackages.production;
}
