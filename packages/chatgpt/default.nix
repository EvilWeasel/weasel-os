{
  alsa-lib,
  at-spi2-atk,
  at-spi2-core,
  autoPatchelfHook,
  cairo,
  cups,
  dbus,
  expat,
  fetchurl,
  gdk-pixbuf,
  glib,
  gtk3,
  lib,
  libdrm,
  libgbm,
  libnotify,
  libsecret,
  libusb1,
  libxkbcommon,
  makeWrapper,
  mesa,
  nspr,
  nss,
  pango,
  qt5,
  qt6,
  rpmextract,
  stdenv,
  systemd,
  wrapGAppsHook3,
  xdg-utils,
  xorg,
}:

stdenv.mkDerivation (finalAttrs: {
  pname = "chatgpt";
  version = "26.825.41651";

  # The official documentation currently exposes a mutable `latest` link. The
  # versioned object below returned `Cache-Control: immutable` and was hashed
  # independently before it was pinned here.
  src = fetchurl {
    url = "https://persistent.oaistatic.com/codex-app-prod/linux/rpm/x86_64/chatgpt-${finalAttrs.version}-1.x86_64.rpm";
    hash = "sha256-NmtlvHMDZwKZzfxXNHKesB36qFy881dKmb/XN6loMRQ=";
  };

  dontUnpack = true;
  dontBuild = true;

  nativeBuildInputs = [
    rpmextract
    autoPatchelfHook
    makeWrapper
    wrapGAppsHook3
  ];

  buildInputs = [
    alsa-lib
    at-spi2-atk
    at-spi2-core
    cairo
    cups
    dbus
    expat
    gdk-pixbuf
    glib
    gtk3
    libdrm
    libgbm
    libnotify
    libsecret
    libusb1
    libxkbcommon
    mesa
    nspr
    nss
    pango
    qt5.qtbase.out
    qt6.qtbase.out
    systemd
    xorg.libX11
    xorg.libXcomposite
    xorg.libXdamage
    xorg.libXext
    xorg.libXfixes
    xorg.libXrandr
  ];

  # The payload carries both glibc and musl prebuilds. On NixOS it selects the
  # glibc variants; leave the unused musl objects untouched.
  autoPatchelfIgnoreMissingDeps = [ "libc.musl-x86_64.so.1" ];

  installPhase = ''
    runHook preInstall

    rpmextract "$src"
    mkdir -p "$out/lib"
    cp -a usr/lib/chatgpt "$out/lib/"

    install -Dm644 usr/share/applications/chatgpt.desktop \
      "$out/share/applications/chatgpt.desktop"
    install -Dm644 usr/share/pixmaps/chatgpt.png \
      "$out/share/pixmaps/chatgpt.png"

    runHook postInstall
  '';

  postFixup = ''
    # Nix supplies all runtime libraries through the closure. Do not install or
    # execute the RPM's scriptlets: those register OpenAI's DNF repository,
    # write a GPG key below /etc, and enable imperative package-manager updates.
    makeWrapper "$out/lib/chatgpt/ChatGPT" "$out/bin/chatgpt" \
      --prefix PATH : ${lib.makeBinPath [ xdg-utils ]}
  '';

  meta = {
    description = "Official OpenAI ChatGPT desktop application with Codex support";
    homepage = "https://developers.openai.com/codex/app";
    license = lib.licenses.unfree;
    mainProgram = "chatgpt";
    platforms = [ "x86_64-linux" ];
    sourceProvenance = with lib.sourceTypes; [ binaryNativeCode ];
  };
})
