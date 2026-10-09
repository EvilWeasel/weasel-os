{
  system ? "x86_64-linux",
}:
import
  (builtins.fetchTree {
    type = "github";
    owner = "nixos";
    repo = "nixpkgs";
    rev = "64c08a7ca051951c8eae34e3e3cb1e202fe36786";
    narHash = "sha256-tpyBcxPpcQb8ukyNF7DoCwfSY3VPsxHoYwj00Cayv5o=";
  })
  {
    inherit system;
    config.allowUnfree = true;
  }
