{ pkgs }:
pkgs.stdenv.mkDerivation {
  pname = "proton-drive-cli";
  version = "0.9.0";
  src = pkgs.fetchurl {
    url = "https://proton.me/download/drive/cli/0.9.0/linux-x64/proton-drive";
    sha512 = "3533025ba69ae112b64e3e01fbcc1ad0688136a4043f6cf6a72886967d85fdcd9ec235479c2e113171614be5225bfba93427509a05ca5aa6071d924fa7e91ca8";
  };
  dontUnpack = true;
  # Bun's compiled executable carries JavaScript after the ELF image. Stripping
  # it produces a generic Bun runtime with the embedded CLI removed.
  dontStrip = true;
  # Patchelf also shifts Bun's embedded payload. This laptop already provides
  # nix-ld; preserve the vendor bytes exactly and wrap libsecret separately.
  dontFixup = true;
  nativeBuildInputs = [
    pkgs.makeWrapper
  ];
  buildInputs = [ pkgs.stdenv.cc.cc.lib ];
  installPhase = ''
    install -Dm755 "$src" "$out/bin/proton-drive"
    wrapProgram "$out/bin/proton-drive" \
      --prefix LD_LIBRARY_PATH : ${pkgs.lib.makeLibraryPath [ pkgs.libsecret ]} \
      --set PROTON_DRIVE_LOG_LEVEL WARNING
  '';
  meta.platforms = [ "x86_64-linux" ];
}
