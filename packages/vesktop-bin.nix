{
  appimageTools,
  fetchurl,
  lib,
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
in
appimageTools.wrapType2 {
  inherit pname version src;

  extraInstallCommands = ''
    install -Dm444 \
      ${appimageContents}/vesktop.desktop \
      "$out/share/applications/vesktop.desktop"
    substituteInPlace "$out/share/applications/vesktop.desktop" \
      --replace-fail 'Exec=AppRun --no-sandbox %U' 'Exec=vesktop %U'

    cp -r ${appimageContents}/usr/share/icons "$out/share/"
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
