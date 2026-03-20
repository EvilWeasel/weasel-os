{
  pkgs,
  username,
  ...
}: {
  users.groups.llama = {};
  users.users = {
    "${username}" = {
      homeMode = "755";
      isNormalUser = true;
      description = username;
      extraGroups = [
        "networkmanager"
        "wheel"
        "libvirtd"
        "scanner"
        "lp"
        "docker"
        "openrazer"
        "llama"
      ];
      shell = pkgs.bash;
      ignoreShellProgramCheck = true;
      packages = with pkgs; [];
    };
  };
}
