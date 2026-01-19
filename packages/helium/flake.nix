{
  description = "Helium browser (AppImage)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      ...
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };

        version = "0.7.10.1";
        src = pkgs.fetchurl {
          url = "https://github.com/imputnet/helium-linux/releases/download/v${version}/helium-${version}-x86_64.AppImage";
          sha256 = "1hadvg86nfzalklv7lz6zpc7n6ifcs8vgw1qqaajr6rafaa54p6p";
        };

        # Wrapper-Script für Wayland / Ozone
        wrapper = pkgs.writeShellScriptBin "helium" ''
          #!${pkgs.stdenv.shell}
          exec "${src}" --appimage-extract-and-run --ozone-platform=wayland "$@"
        '';
      in
      {
        packages.default = pkgs.appimageTools.wrapType2 {
          pname = "helium";
          inherit version src;

          # Desktopfile direkt ins Package
          desktopFile = pkgs.writeText "helium.desktop" ''
            [Desktop Entry]
            Name=Helium
            Comment=Helium Browser
            Exec=$out/bin/helium
            Icon=$out/Helium.AppImage
            Terminal=false
            Type=Application
            Categories=Network;WebBrowser;
          '';

          # binary im $out/bin
          unpackPhase = "true";
          installPhase = ''
            mkdir -p $out/bin
            cp ${wrapper} $out/bin/helium
            cp ${src} $out/Helium.AppImage
            chmod +x $out/bin/helium $out/Helium.AppImage
          '';

          meta = with pkgs.lib; {
            description = "Helium browser";
            homepage = "https://github.com/imputnet/helium";
            license = licenses.gpl3;
            platforms = [ "x86_64-linux" ];
          };
        };
      }
    );
}
