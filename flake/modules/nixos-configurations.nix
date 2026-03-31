{hostRegistry, mkHost, ...}: {
  flake.nixosConfigurations =
    builtins.mapAttrs
    (hostName: hostConfig:
      mkHost (
        hostConfig
        // {
          inherit hostName;
        }
      ))
    hostRegistry;
}
