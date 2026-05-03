{ pkgs, ... }:
{
  # Keep a non-EOL 6.x kernel for out-of-tree modules such as EVDI/DisplayLink.
  # linuxPackages_zen moved to 7.0.x in nixpkgs and evdi 1.14.12 does not build there.
  boot.kernelPackages = pkgs.linuxPackages_6_18;
}
