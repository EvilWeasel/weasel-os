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
  };

  outputs =
    {
      nixpkgs,
      nixpkgs-unstable,
      home-manager,
      ...
    }@inputs:
    let
      system = "x86_64-linux";
      username = "evilweasel";
      host = "nixy-desktop";
      hostLaptop = "nixy-laptop";

      mkPkgs =
        nixpkgs:
        import nixpkgs {
          localSystem = { system = system; };
          config.allowUnfree = true;
        };

      pkgsStable = mkPkgs nixpkgs;
      pkgsUnstable = mkPkgs nixpkgs-unstable;
    in
    {
      # PACKAGES (DERIVATIONS ONLY)
      packages.${system} = {
        certs = pkgsStable.callPackage ./certs/default.nix { };
        # frostycli = pkgsUnstable.callPackage ./packages/frostycli { };
      };

      # MODULES
      nixosModules.certs =
        { pkgs, ... }:
        {
          options.certs = nixpkgs.lib.mkOption {
            type = nixpkgs.lib.types.attrsOf nixpkgs.lib.types.path;
            default = inputs.self.packages.${pkgs.system}.certs;
            description = "Bundled custom certificates";
          };
        };

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
          inputs.self.nixosModules.certs
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
          inputs.self.nixosModules.certs
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
        ];
      };
    };
}
