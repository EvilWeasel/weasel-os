{...}: {
  flake = {
    nixosModules = {
      common = import ../../profiles/system/common.nix;
      client-base = import ../../profiles/system/base.nix;
      server = import ../../profiles/system/server.nix;
      laptop = import ../../profiles/system/laptop.nix;
      desktop = import ../../profiles/system/desktop.nix;
      openclaw = import ../../modules/nixos/roles/openclaw.nix;
    };

    homeModules = {
      common = import ../../profiles/home/common.nix;
      client-base = import ../../profiles/home/base.nix;
      server = import ../../profiles/home/server.nix;
      laptop = import ../../profiles/home/laptop.nix;
      desktop = import ../../profiles/home/desktop.nix;
    };
  };
}
