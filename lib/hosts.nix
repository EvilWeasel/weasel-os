{inputs}: {
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
}
