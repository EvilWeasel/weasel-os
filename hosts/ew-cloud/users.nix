{
  pkgs,
  ...
}: {
  users.users.evilweasel = {
    isNormalUser = true;
    description = "evilweasel";
    home = "/home/evilweasel";
    extraGroups = [
      "wheel"
    ];
    shell = pkgs.bash;
    ignoreShellProgramCheck = true;
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINDXG/YhRAUs4Rz7oM/5fJSNy2n+CeaZcFhBYoydOKT1 evilweasel"
    ];
  };
}
