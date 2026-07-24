{ pkgs }:

pkgs.writeShellApplication {
  name = "sophos-vpn";
  runtimeInputs = [
    pkgs.coreutils
    pkgs.gnugrep
    pkgs.gnused
    pkgs.jq
    pkgs.libsecret
    pkgs.networkmanager
    pkgs.openssh
    pkgs.iproute2
  ];
  text = builtins.readFile ./sophos-vpn.sh;
}
