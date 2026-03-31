{inputs}: {
  nixy-desktop = {
    class = "client";
    system = "x86_64-linux";
    username = "evilweasel";
    extraModules = [];
  };

  nixy-laptop = {
    class = "client";
    system = "x86_64-linux";
    username = "evilweasel";
    extraModules = [
      inputs.nixos-hardware.nixosModules.lenovo-yoga-7-14IAH7-hybrid
    ];
  };

  michapc = {
    class = "client";
    system = "x86_64-linux";
    username = "micha";
    extraModules = [
      ../modules/michapc-nvidia.nix
    ];
  };

  michapc-debug = {
    class = "client";
    system = "x86_64-linux";
    username = "micha";
    extraModules = [
      ../modules/michapc-nvidia.nix
    ];
  };

  ew-cloud = {
    class = "server";
    system = "x86_64-linux";
    username = "evilweasel";
    extraModules = [];
  };
}
