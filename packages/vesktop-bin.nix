{
  appimageTools,
  fetchurl,
  lib,
}:

appimageTools.wrapType2 rec {
  pname = "vesktop";
  version = "1.6.7";

  src = fetchurl {
    url = "https://github.com/Vencord/Vesktop/releases/download/v${version}/Vesktop-${version}.AppImage";
    hash = "sha256-hVYytou6pyTXbp89neqwQQER9dlbedo88CTOtU9ObYE=";
  };

  meta = {
    description = "Vesktop Discord client with current Wayland screenshare fixes";
    homepage = "https://github.com/Vencord/Vesktop";
    license = lib.licenses.gpl3Plus;
    mainProgram = pname;
    platforms = [ "x86_64-linux" ];
    sourceProvenance = with lib.sourceTypes; [ binaryNativeCode ];
  };
}
