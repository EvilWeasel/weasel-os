{...}: {
  imports = [
    ../../profiles/system/common.nix
    ../../profiles/system/base.nix
    ../../profiles/system/laptop.nix
    ./hardware.nix
    ./users.nix
  ];

  swapDevices = [
    {
      device = "/swapfile";
    }
  ];
}
