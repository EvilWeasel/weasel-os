{
  description = "WeaselOS";

  inputs = {
    nixpkgs-unstable.url = "github:nixos/nixpkgs/nixos-unstable";
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
    home-manager = {
      url = "github:nix-community/home-manager/release-25.11";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nixos-hardware.url = "github:NixOS/nixos-hardware/master";
    stylix = {
      url = "github:danth/stylix/release-25.11";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    fine-cmdline = {
      url = "github:VonHeikemen/fine-cmdline.nvim";
      flake = false;
    };
    quickshell = {
      url = "git+https://git.outfoxxed.me/outfoxxed/quickshell";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    dms = {
      url = "github:AvengeMedia/DankMaterialShell/stable";
      inputs.nixpkgs.follows = "nixpkgs-unstable";
    };
    helium = {
      url = "path:/home/evilweasel/weasel-os/packages/helium";
      inputs.nixpkgs.follows = "nixpkgs-unstable";
    };
    t3code = {
      url = "path:/home/evilweasel/weasel-os/packages/t3code";
      inputs.nixpkgs.follows = "nixpkgs-unstable";
    };
    handy-nixpkgs.url = "github:NixOS/nixpkgs/d6c71932130818840fc8fe9509cf50be8c64634f";
    handy = {
      # Pin to a known-good revision because latest upstream currently breaks Nix builds
      # (`tauri-runtime-2.9.1` hash/dependency mismatch during evaluation/build).
      url = "github:cjpais/Handy/f705a4948d01a29a815e284c44dae5fec890639c";
      inputs.nixpkgs.follows = "handy-nixpkgs";
    };
  };

  outputs = {
    nixpkgs,
    nixpkgs-unstable,
    home-manager,
    handy,
    ...
  } @ inputs: let
    system = "x86_64-linux";
    username = "evilweasel";
    host = "nixy-desktop";
    hostLaptop = "nixy-laptop";

    mkPkgs = nixpkgs:
      import nixpkgs {
        localSystem = {
          system = system;
        };
        config.allowUnfree = true;
      };

    pkgsStable = mkPkgs nixpkgs;
    pkgsUnstable = mkPkgs nixpkgs-unstable;
  in {
    formatter.${system} = pkgsStable.alejandra;
    packages.${system}.t3code = inputs.t3code.packages.${system}.default;

    # HOST CONFIGS
    nixosConfigurations.${host} = nixpkgs.lib.nixosSystem {
      specialArgs = {
        inherit
          system
          inputs
          username
          host
          ;
      };
      modules = [
        ./hosts/${host}/config.nix
        inputs.stylix.nixosModules.stylix
        home-manager.nixosModules.home-manager
        {
          home-manager.extraSpecialArgs = {
            inherit username inputs host;
          };
          home-manager.useGlobalPkgs = false;
          home-manager.useUserPackages = true;
          home-manager.users.${username} = import ./hosts/${host}/home.nix;
        }
      ];
    };

    nixosConfigurations.${hostLaptop} = nixpkgs.lib.nixosSystem {
      specialArgs = {
        inherit system inputs username;
        host = hostLaptop;
        pkgsUnstable = pkgsUnstable;
      };
      modules = [
        ./hosts/${hostLaptop}/config.nix
        inputs.nixos-hardware.nixosModules.lenovo-yoga-7-14IAH7-hybrid
        inputs.stylix.nixosModules.stylix
        home-manager.nixosModules.home-manager
        ./modules/canbus.nix
        {
          home-manager.extraSpecialArgs = {
            inherit username inputs pkgsUnstable;
            host = hostLaptop;
          };
          home-manager.useGlobalPkgs = false;
          home-manager.useUserPackages = true;
          home-manager.users.${username} = import ./hosts/${hostLaptop}/home.nix;
        }
        {
          environment.systemPackages = [
            handy.packages.${system}.handy
          ];
        }
      ];
    };
  };
}
