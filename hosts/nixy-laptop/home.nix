{ pkgs, ... }:
{
  imports = [
    ../../profiles/home/common.nix
    ../../profiles/home/base.nix
    ../../profiles/home/client.nix
    ../../profiles/home/laptop.nix
  ];

  home.packages = [
    pkgs.screen-pipe
  ];
}
