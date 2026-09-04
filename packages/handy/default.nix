{
  handy,
  handyNixpkgs,
  system,
}:
let
  pkgs = import handyNixpkgs { inherit system; };
  importCargoLock = pkgs.callPackage "${handyNixpkgs}/pkgs/build-support/rust/import-cargo-lock.nix" {
    fetchurl =
      args:
      pkgs.fetchurl (
        args
        // {
          url =
            pkgs.lib.replaceStrings
              [ "https://crates.io/api/v1/crates/" ]
              [ "https://static.crates.io/crates/" ]
              args.url;
        }
      );
  };
in
handy.packages.${system}.handy.overrideAttrs (_old: {
  # The crates.io redirect API returns HTTP 403. The official static endpoint
  # serves identical archives, verified against every Cargo.lock checksum.
  # Override only the fetch URL, not extraRegistries: registering crates-io a
  # second time produces a duplicate-source Cargo error.
  cargoDeps = importCargoLock {
    lockFile = "${handy}/src-tauri/Cargo.lock";
    allowBuiltinFetchGit = true;
  };
})
