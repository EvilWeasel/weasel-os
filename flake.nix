
{
  description = "WeaselOS";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    home-manager.url = "github:nix-community/home-manager/master";
    home-manager.inputs.nixpkgs.follows = "nixpkgs";
    nixos-hardware.url = "github:NixOS/nixos-hardware/master";
    stylix.url = "github:danth/stylix";
    fine-cmdline = {
      url = "github:VonHeikemen/fine-cmdline.nvim";
      flake = false;
    };
    quickshell = {
      # add ?ref=<tag> to track a tag
      url = "git+https://git.outfoxxed.me/outfoxxed/quickshell";

      # THIS IS IMPORTANT
      # Mismatched system dependencies will lead to crashes and other issues.
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { nixpkgs, home-manager, ... }@inputs:
    let
      system = "x86_64-linux";
      username = "evilweasel";
      host = "nixy-desktop";
      hostLaptop = "nixy-laptop";
    in {
      # PACKAGES.DEFS (DERIVATIONS)
      packages.${system}.certs = nixpkgs.lib.makeOverridable (pkgs:
        pkgs.callPackage ./certs/default.nix { }
      );

      # MODULES
      nixosModules.certs = { config, pkgs, ... }:
        let
          myCerts = inputs.self.packages.${pkgs.system}.certs;
        in {
          options.certs = nixpkgs.lib.mkOption {
            type = nixpkgs.lib.types.attrsOf nixpkgs.lib.types.path;
            default = myCerts;
            description = "Bundled custom certificates";
          };
        };

      # HOST CONFIGS
      nixosConfigurations.${host} = nixpkgs.lib.nixosSystem {
        specialArgs = { inherit system inputs username host; };
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
        specialArgs = { inherit system inputs username; host = hostLaptop; };
        modules = [
          ./hosts/${hostLaptop}/config.nix
          inputs.self.nixosModules.certs
          inputs.nixos-hardware.nixosModules.lenovo-yoga-7-14IAH7-hybrid
          inputs.stylix.nixosModules.stylix
          home-manager.nixosModules.home-manager
          {
            home-manager.extraSpecialArgs = {
              inherit username inputs; host = hostLaptop;
            };
            home-manager.useGlobalPkgs = false;
            home-manager.useUserPackages = true;
            home-manager.users.${username} = import ./hosts/${hostLaptop}/home.nix;
          }
        ];
      };
    };
}
