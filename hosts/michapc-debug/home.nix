{lib, ...}: {
  imports = [
    ../michapc/home.nix
  ];

  programs."dank-material-shell".enable = lib.mkForce false;
  weasel.session.startDms = lib.mkForce false;
}
