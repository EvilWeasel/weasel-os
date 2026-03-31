{...}: {
  imports = [
    ../../profiles/home/common.nix
    ../../profiles/home/server.nix
  ];

  programs.direnv = {
    enable = true;
    nix-direnv.enable = true;
  };
}
