{ ... }:
{
  imports = [
    ../../profiles/home/common.nix
    ../../profiles/home/base.nix
    ../../profiles/home/client.nix
    ../../profiles/home/laptop.nix
    ../../programs/hephaestus-recovery-console.nix
  ];

  weasel.hephaestusRecoveryConsole.enable = true;
}
