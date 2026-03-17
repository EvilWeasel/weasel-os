{...}: {
  imports = [
    ../../profiles/system/base.nix
    ../../profiles/system/laptop.nix
    ./hardware.nix
    ./users.nix
  ];
}
