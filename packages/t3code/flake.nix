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
        appimageContents = pkgs.appimageTools.extractType2 {
          pname = "t3code";
          inherit version src;
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
        urlHandlerDesktopFile = pkgs.writeText "com.t3tools.T3Code.desktop" ''
          [Desktop Entry]
          Type=Application
          Name=T3 Code URL handler
          Exec=t3code %U
          Icon=applications-development
          Terminal=false
          NoDisplay=true
          StartupNotify=false
          MimeType=x-scheme-handler/t3code;
        '';
      in
      {
        # An FHS/AppImage bubblewrap launcher sets NoNewPrivs on T3 itself.
        # Codex then inherits it even for approved commands outside its own
        # sandbox, so sudo cannot elevate. Patch the upstream binary's native
        # library paths instead; T3 and Codex keep their own sandbox controls.
        packages.default = pkgs.stdenv.mkDerivation {
          pname = "t3code";
          inherit version;
          src = appimageContents;
          dontUnpack = true;
          dontBuild = true;
          dontWrapGApps = true;

          nativeBuildInputs = [
            pkgs.autoPatchelfHook
            pkgs.makeWrapper
            pkgs.wrapGAppsHook3
          ];
          buildInputs = with pkgs; [
            alsa-lib
            at-spi2-atk
            at-spi2-core
            cairo
            cups
            dbus
            dbus-glib
            expat
            gdk-pixbuf
            glib
            gtk3
            libdrm
            libdbusmenu
            libdbusmenu-gtk3
            libgbm
            libnotify
            libsecret
            libxkbcommon
            nspr
            nss
            openssl
            pango
            stdenv.cc.cc.lib
            systemd
            libx11
            libxcomposite
            libxdamage
            libxext
            libxfixes
            libxrandr
            libxcb
          ];

          # The upstream payload also includes unused musl Node prebuilds.
          autoPatchelfIgnoreMissingDeps = [ "libc.musl-x86_64.so.1" ];

          installPhase = ''
            runHook preInstall
            mkdir -p "$out/lib/t3code" "$out/share"
            cp -a "$src"/. "$out/lib/t3code/"
            chmod -R u+w "$out/lib/t3code"
            cp -a "$src/usr/share/icons" "$out/share/"
            install -Dm444 ${desktopFile} "$out/share/applications/t3code.desktop"
            install -Dm444 ${urlHandlerDesktopFile} "$out/share/applications/com.t3tools.T3Code.desktop"
            runHook postInstall
          '';

          postFixup = ''
            makeWrapper "$out/lib/t3code/t3code" "$out/bin/t3code" \
              "''${gappsWrapperArgs[@]}" \
              --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.xdg-utils ]} \
              --prefix LD_LIBRARY_PATH : ${
                pkgs.lib.makeLibraryPath [
                  pkgs.libglvnd
                  pkgs.libsecret
                ]
              } \
              --set T3CODE_DISABLE_AUTO_UPDATE true \
              --set WEASEL_T3_CLIENT 1
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
