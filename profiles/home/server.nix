{pkgs, ...}: {
  imports = [
    ../../programs/neovim.nix
    ../../programs/terminal-stack.nix
  ];

  home.packages = with pkgs; [
    fastfetch
  ];
}
