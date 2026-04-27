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

        pname = "helium";
        version = "0.10.6.1";
        src = pkgs.fetchurl {
          url = "https://github.com/imputnet/helium-linux/releases/download/${version}/helium-${version}-x86_64.AppImage";
          sha256 = "sha256-6xqNRaP3aqitEseexRVEEjKkJClC0j1HHZoRGQanhSk=";
        };

        appimageContents = pkgs.appimageTools.extractType2 {
          inherit pname version src;
        };
      in
      {
        packages.default = pkgs.appimageTools.wrapType2 {
          inherit pname;
          inherit version src;

          runScript = "appimage-exec.sh -w ${appimageContents} -- --ozone-platform=wayland";

          extraInstallCommands = ''
            install -Dm444 ${appimageContents}/helium.desktop $out/share/applications/helium.desktop
            substituteInPlace $out/share/applications/helium.desktop \
              --replace-fail 'Exec=helium %U' "Exec=$out/bin/helium %U" \
              --replace-fail 'Exec=helium' "Exec=$out/bin/helium"

            install -Dm444 ${appimageContents}/helium.png $out/share/icons/hicolor/256x256/apps/helium.png
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
