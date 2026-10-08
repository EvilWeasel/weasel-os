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

        source = builtins.fromJSON (builtins.readFile ./source.json);
        version = source.version;
        src = pkgs.fetchurl {
          inherit (source) url hash;
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
          nativeBuildInputs = [ pkgs.makeWrapper ];
          extraInstallCommands = ''
            wrapProgram $out/bin/t3code \
              --set T3CODE_DISABLE_AUTO_UPDATE true \
              --set WEASEL_T3_CLIENT 1
            install -Dm444 ${desktopFile} $out/share/applications/t3code.desktop
          '';

          meta = with pkgs.lib; {
            description = "T3 Code desktop app";
            homepage = "https://github.com/pingdotgg/t3code";
            license = licenses.mit;
            mainProgram = "t3code";
            platforms = [ "x86_64-linux" ];
          };
        };
      }
    );
}
