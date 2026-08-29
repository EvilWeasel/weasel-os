{
  lib,
  stdenv,
  fetchurl,
  rpmextract,
  autoPatchelfHook,
  wrapGAppsHook4,
  cairo,
  gsettings-desktop-schemas,
  glib,
  gtk4,
  libsoup_3,
  webkitgtk_6_0,
  xorg,
  daemonSocket ? "unix:///var/run/netbird.sock",
}:

stdenv.mkDerivation (finalAttrs: {
  pname = "netbird-ui-bin";
  version = "0.77.1";

  src = fetchurl {
    url = "https://github.com/netbirdio/netbird/releases/download/v${finalAttrs.version}/netbird-ui_${finalAttrs.version}_linux_amd64.rpm";
    hash = "sha256-mwGioWtnR2CG3+u5e/CNZ7XXLXVDG6MKxFzLm/+2Muk=";
  };

  dontUnpack = true;
  dontBuild = true;

  nativeBuildInputs = [
    rpmextract
    autoPatchelfHook
    wrapGAppsHook4
  ];

  buildInputs = [
    cairo
    gsettings-desktop-schemas
    glib
    gtk4
    libsoup_3
    webkitgtk_6_0
    xorg.libX11
  ];

  installPhase = ''
    runHook preInstall
    rpmextract "$src"
    install -Dm755 usr/bin/netbird-ui "$out/bin/netbird-ui"
    install -Dm644 usr/share/applications/org.wails.netbird.desktop \
      "$out/share/applications/netbird.desktop"
    install -Dm644 usr/share/pixmaps/netbird.png \
      "$out/share/pixmaps/netbird.png"
    substituteInPlace "$out/share/applications/netbird.desktop" \
      --replace-fail "/usr/bin/netbird-ui" "$out/bin/netbird-ui"
    runHook postInstall
  '';

  preFixup = ''
    gappsWrapperArgs+=(
      --set-default NB_DAEMON_ADDR ${lib.escapeShellArg daemonSocket}
    )
  '';

  meta = {
    description = "Pinned NetBird desktop UI binary";
    homepage = "https://netbird.io";
    license = lib.licenses.bsd3;
    mainProgram = "netbird-ui";
    platforms = [ "x86_64-linux" ];
    sourceProvenance = with lib.sourceTypes; [ binaryNativeCode ];
  };
})
