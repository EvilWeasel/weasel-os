{
  description = "T3 Code desktop package";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      nixpkgs,
      flake-utils,
      ...
    }:
    flake-utils.lib.eachSystem [ "x86_64-linux" ] (
      system:
      let
        pkgs = import nixpkgs { inherit system; };

        version = "0.0.4";
        src = pkgs.fetchurl {
          url = "https://github.com/pingdotgg/t3code/releases/download/v${version}/T3-Code-${version}-x86_64.AppImage";
          hash = "sha256-HlkQ/uPLXHh2Duamrmhp31yQqnETawQ4Ru7kg2MmpVs=";
        };

        desktopFile = pkgs.writeText "t3code.desktop" ''
          [Desktop Entry]
          Name=T3 Code
          Comment=AI coding assistant desktop app
          Exec=t3code %U
          Icon=applications-development
          Terminal=false
          Type=Application
          Categories=Development;IDE;
          StartupWMClass=T3 Code
        '';
      in
      {
        packages.default = pkgs.appimageTools.wrapType2 {
          pname = "t3code";
          inherit version src;
          extraInstallCommands = ''
            install -Dm444 ${desktopFile} $out/share/applications/t3code.desktop
          '';

          meta = with pkgs.lib; {
            description = "T3 Code desktop app";
            homepage = "https://github.com/pingdotgg/t3code";
            license = licenses.asl20;
            mainProgram = "t3code";
            platforms = [ "x86_64-linux" ];
          };
        };
      }
    );
}
