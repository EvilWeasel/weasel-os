{inputs}: {
  lucas = {
    system = "x86_64-linux";
    username = "lucas";
    extraModules = [];
  };

  nixy-desktop = {
    system = "x86_64-linux";
    username = "evilweasel";
    extraModules = [];
  };

  nixy-laptop = {
    system = "x86_64-linux";
    username = "evilweasel";
    extraModules = [
      inputs.nixos-hardware.nixosModules.lenovo-yoga-7-14IAH7-hybrid
    ];
  };

  michapc = {
    system = "x86_64-linux";
    username = "micha";
    extraModules = [
      ../modules/michapc-nvidia.nix
    ];
  };

  michapc-debug = {
    system = "x86_64-linux";
    username = "micha";
    extraModules = [
      ../modules/michapc-nvidia.nix
    ];
  };
}
