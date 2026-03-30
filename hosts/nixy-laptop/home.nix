{
  inputs,
  pkgs,
  ...
}: {
  imports = [
    ../../profiles/home/base.nix
    ../../profiles/home/laptop.nix
  ];

  home.packages = [
    inputs.self.packages.${pkgs.stdenv.hostPlatform.system}.screenpipe-app
  ];
}
