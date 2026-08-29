{
  appimageTools,
  asar,
  fetchurl,
  lib,
  nodejs,
  runCommand,
}:

let
  pname = "vesktop";
  version = "1.6.7";

  src = fetchurl {
    url = "https://github.com/Vencord/Vesktop/releases/download/v${version}/Vesktop-${version}.AppImage";
    hash = "sha256-hVYytou6pyTXbp89neqwQQER9dlbedo88CTOtU9ObYE=";
  };

  appimageContents = appimageTools.extractType2 {
    inherit pname version src;
  };

  # Vesktop 1.6.7 asks its renderer to open a second, custom picker after
  # xdg-desktop-portal has already selected a Wayland source.  When that
  # renderer command rejects, the error is swallowed and Electron receives an
  # empty capture result.  Keep the working portal source and hand it directly
  # to Electron instead.  The patcher deliberately checks the exact bundled
  # code so a future Vesktop update cannot silently lose this workaround.
  patchedAppimageContents =
    runCommand "${pname}-${version}-wayland-patched"
      {
        nativeBuildInputs = [
          asar
          nodejs
        ];
      }
      ''
        mkdir -p "$out"
        cp -a ${appimageContents}/. "$out/"
        chmod -R u+w "$out/resources"

        mkdir app
        asar extract "$out/resources/app.asar" app
        node ${../scripts/patch-vesktop-wayland-capture.mjs} app/dist/js/main.js

        rm -f "$out/resources/app.asar"
        rm -rf "$out/resources/app.asar.unpacked"
        asar pack app "$out/resources/app.asar" --unpack '**/*.node'
      '';
in
appimageTools.wrapAppImage {
  inherit pname version;
  src = patchedAppimageContents;

  extraInstallCommands = ''
    install -Dm444 \
      ${patchedAppimageContents}/vesktop.desktop \
      "$out/share/applications/vesktop.desktop"
    substituteInPlace "$out/share/applications/vesktop.desktop" \
      --replace-fail 'Exec=AppRun --no-sandbox %U' 'Exec=vesktop %U'

    cp -r ${patchedAppimageContents}/usr/share/icons "$out/share/"
  '';

  meta = {
    description = "Vesktop Discord client with current Wayland screenshare fixes";
    homepage = "https://github.com/Vencord/Vesktop";
    license = lib.licenses.gpl3Plus;
    mainProgram = pname;
    platforms = [ "x86_64-linux" ];
    sourceProvenance = with lib.sourceTypes; [ binaryNativeCode ];
  };
}
