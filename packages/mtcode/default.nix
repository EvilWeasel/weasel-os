{ pkgs }:
let
  source = builtins.fromJSON (builtins.readFile ./source.json);
  inherit (source) version;
  src = pkgs.fetchurl { inherit (source) url hash; };
  appimageContents = pkgs.appimageTools.extractType2 {
    pname = "mtcode";
    inherit version src;
  };
  desktopFile = pkgs.writeText "mtcode.desktop" ''
    [Desktop Entry]
    Name=MT Code
    Comment=Coding agents with realtime voice
    Exec=mtcode %U
    Icon=mtcode
    Terminal=false
    Type=Application
    Categories=Development;IDE;
    StartupWMClass=mtcode
    MimeType=x-scheme-handler/mtcode;
  '';
in
pkgs.stdenv.mkDerivation {
  pname = "mtcode";
  inherit version;
  src = appimageContents;
  dontUnpack = true;
  dontBuild = true;
  dontWrapGApps = true;

  # Keep the same native launcher approach as T3. An FHS bubblewrap launcher
  # would make approved Codex children inherit NoNewPrivs.
  nativeBuildInputs = [
    pkgs.asar
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
  autoPatchelfIgnoreMissingDeps = [ "libc.musl-x86_64.so.1" ];

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/lib/mtcode" "$out/share"
    cp -a "$src"/. "$out/lib/mtcode/"
    chmod -R u+w "$out/lib/mtcode"
    test -x "$out/lib/mtcode/mtcode"
    # The OAuth transport registers the upstream scheme on every launch.
    # Preserve the configured t3code:// association during the parallel trial.
    asar extract "$out/lib/mtcode/resources/app.asar" app
    substituteInPlace app/apps/desktop/dist-electron/main.cjs \
      --replace-fail 'electron.app.setAsDefaultProtocolClient(options.renderer.scheme);' \
      'if (options.renderer.scheme !== "t3code") electron.app.setAsDefaultProtocolClient(options.renderer.scheme);'
    asar pack app "$out/lib/mtcode/resources/app.asar" --unpack-dir node_modules
    cp -a "$src/usr/share/icons" "$out/share/"
    install -Dm444 ${desktopFile} "$out/share/applications/mtcode.desktop"
    runHook postInstall
  '';

  postFixup = ''
    makeWrapper "$out/lib/mtcode/mtcode" "$out/bin/mtcode" \
      "''${gappsWrapperArgs[@]}" \
      --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.xdg-utils ]} \
      --prefix LD_LIBRARY_PATH : ${
        pkgs.lib.makeLibraryPath (
          with pkgs;
          [
            alsa-lib
            at-spi2-core
            dbus
            expat
            glib
            libgbm
            libglvnd
            libsecret
            libx11
            libxcomposite
            libxdamage
            libxext
            libxfixes
            libxrandr
            libxcb
            libxkbcommon
            nspr
            nss
            systemd
          ]
        )
      } \
      --unset NO_AT_BRIDGE \
      --unset T3CODE_HOME \
      --unset T3CODE_PORT \
      --add-flags "--force-renderer-accessibility" \
      --set T3CODE_DESKTOP_DISTRO munim \
      --set T3CODE_DISABLE_AUTO_UPDATE true
  '';

  meta = with pkgs.lib; {
    description = "MT Code desktop app with realtime voice, installed alongside T3 Code";
    homepage = "https://github.com/munimtechnologies/mtcode";
    license = [
      licenses.asl20
      licenses.mit
    ];
    mainProgram = "mtcode";
    platforms = [ "x86_64-linux" ];
  };
}
