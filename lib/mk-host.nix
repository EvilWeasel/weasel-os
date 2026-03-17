{
  inputs,
  home-manager,
  nixpkgs,
  pkgsUnstable,
}: {
  hostName,
  system,
  username,
  extraModules ? [],
}:
nixpkgs.lib.nixosSystem {
  inherit system;

  specialArgs = {
    inherit
      inputs
      pkgsUnstable
      username
      ;
    host = hostName;
  };

  modules =
    [
      ../hosts/${hostName}/config.nix
      inputs.stylix.nixosModules.stylix
      home-manager.nixosModules.home-manager
      {
        home-manager.extraSpecialArgs = {
          inherit
            inputs
            pkgsUnstable
            username
            ;
          host = hostName;
        };
        home-manager.useGlobalPkgs = false;
        home-manager.useUserPackages = true;
        home-manager.users.${username} = import ../hosts/${hostName}/home.nix;
      }
    ]
    ++ extraModules;
}
