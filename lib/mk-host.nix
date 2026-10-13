{ inputs, mkPkgs }:
{
  hostName,
  class,
  system,
  username,
  extraModules ? [ ],
  ...
}:
inputs.nixpkgs.lib.nixosSystem {
  inherit system;

  specialArgs =
    let
      pkgsUnstable = mkPkgs inputs.nixpkgs-unstable system;
    in
    {
      inherit inputs pkgsUnstable username;
      host = hostName;
    };

  modules = [
    ../hosts/${hostName}/config.nix
    inputs.home-manager.nixosModules.home-manager
    {
      nixpkgs.config.allowUnfree = true;
      home-manager.extraSpecialArgs = {
        pkgsUnstable = mkPkgs inputs.nixpkgs-unstable system;
        inherit inputs username;
        host = hostName;
      };
      home-manager.useGlobalPkgs = false;
      home-manager.useUserPackages = true;
      home-manager.users.${username} = import ../hosts/${hostName}/home.nix;
    }
    (
      { lib, pkgs, ... }:
      lib.mkIf (class == "client") {
        environment.systemPackages = [
          pkgs.anydesk
        ];
      }
    )
  ]
  ++ extraModules;
}
