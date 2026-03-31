{inputs}: {
  hostName,
  system,
  username,
  extraModules ? [],
  ...
}:
inputs.nixpkgs.lib.nixosSystem {
  inherit system;

  specialArgs = let
    pkgsUnstable = import inputs.nixpkgs-unstable {
      inherit system;
      config.allowUnfree = true;
    };
  in {
    inherit inputs pkgsUnstable username;
    host = hostName;
  };

  modules =
    [
      ../hosts/${hostName}/config.nix
      inputs.home-manager.nixosModules.home-manager
      {
        home-manager.extraSpecialArgs = {
          pkgsUnstable = import inputs.nixpkgs-unstable {
            inherit system;
            config.allowUnfree = true;
          };
          inherit inputs username;
          host = hostName;
        };
        home-manager.useGlobalPkgs = false;
        home-manager.useUserPackages = true;
        home-manager.users.${username} = import ../hosts/${hostName}/home.nix;
      }
    ]
    ++ extraModules;
}
