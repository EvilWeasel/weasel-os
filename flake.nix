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
      url = "path:./packages/helium";
      inputs.nixpkgs.follows = "nixpkgs-unstable";
    };
    t3code = {
      url = "path:./packages/t3code";
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
    ...
  } @ inputs: let
    mkPkgs = nixpkgs:
      import nixpkgs {
        localSystem = {
          system = "x86_64-linux";
        };
        config.allowUnfree = true;
      };

    pkgsStable = mkPkgs nixpkgs;
    pkgsUnstable = mkPkgs nixpkgs-unstable;
    hosts = import ./lib/hosts.nix {inherit inputs;};
    mkHost = import ./lib/mk-host.nix {
      inherit
        home-manager
        inputs
        nixpkgs
        pkgsUnstable
        ;
    };
  in {
    formatter.x86_64-linux = pkgsStable.alejandra;
    packages.x86_64-linux.t3code = inputs.t3code.packages.x86_64-linux.default;

    nixosConfigurations =
      nixpkgs.lib.mapAttrs
      (hostName: hostConfig:
        mkHost (
          hostConfig
          // {
            inherit hostName;
          }
        ))
      hosts;
  };
}
