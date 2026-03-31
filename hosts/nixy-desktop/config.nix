{...}: {
  imports = [
    ../../profiles/system/common.nix
    ../../profiles/system/base.nix
    ../../profiles/system/desktop.nix
    ./hardware.nix
    ./users.nix
  ];
}
