{...}: {
  imports = [
    ../../profiles/system/base.nix
    ../../profiles/system/desktop.nix
    ./hardware.nix
    ./users.nix
  ];
}
