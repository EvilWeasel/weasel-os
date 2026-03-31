{
  description = "WeaselOS";

  inputs = {
    flake-parts.url = "github:hercules-ci/flake-parts";
    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nixpkgs-unstable.url = "github:nixos/nixpkgs/nixos-unstable";
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
    nixos-anywhere = {
      url = "github:nix-community/nixos-anywhere";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nix-openclaw = {
      url = "github:openclaw/nix-openclaw";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    home-manager = {
      url = "github:nix-community/home-manager/release-25.11";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nixos-hardware.url = "github:NixOS/nixos-hardware/master";
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
    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = inputs:
    inputs.flake-parts.lib.mkFlake {inherit inputs;} {
      systems = ["x86_64-linux"];
      imports = [
        ./flake/modules/shared.nix
        ./flake/modules/outputs.nix
        ./flake/modules/nixos-configurations.nix
        ./flake/modules/module-exports.nix
      ];
    };
}
