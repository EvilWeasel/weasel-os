{ ... }:
{
  weasel.t3Fork.enable = true;
  imports = [
    ../../programs/t3code-fork.nix
    ../../profiles/home/common.nix
    ../../profiles/home/base.nix
    ../../profiles/home/client.nix
    ../../profiles/home/desktop.nix
  ];
}
