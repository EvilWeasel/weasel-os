{
  appimageTools,
  fetchurl,
  lib,
  makeWrapper,
  wl-clipboard,
  xclip,
  xsel,
}:

let
  pname = "wispr-flow";
  version = "1.6.7-1.0.3";

  src = fetchurl {
    url = "https://github.com/wispr-flow-linux/wispr-flow-linux/releases/download/v1.0.3%2Bwispr1.6.7/wispr-flow-1.6.7-1.0.3-x86_64.AppImage";
    hash = "sha256-T9/evAykYnc20TVc7sX3Bwf8aTkTkxEtDr8FNavIMfA=";
  };

  appimageContents = appimageTools.extractType2 {
    inherit pname version src;

    postExtract = ''
          # AppImages normally disable Chromium's sandbox because a SquashFS mount
          # cannot retain a setuid helper. We run the extracted payload and use the
          # audited NixOS wrapper at /run/wrappers/bin/__chromium-suid-sandbox.
          substituteInPlace "$out/AppRun" \
            --replace-fail "build_electron_args 'appimage'" "build_electron_args 'nix'"

          substituteInPlace "$out/usr/lib/wispr-flow/doctor.sh" \
            --replace-fail \
              'local electron_path="''${1:-}"' \
              'local electron_path="''${1:-}"
      if [[ -n ''${CHROME_DEVEL_SANDBOX:-} && -x ''${CHROME_DEVEL_SANDBOX:-} && -u ''${CHROME_DEVEL_SANDBOX:-} ]]; then
        _pass "chrome-sandbox: external setuid helper OK ($CHROME_DEVEL_SANDBOX)"
        return
      fi'

          substituteInPlace "$out/usr/lib/wispr-flow/doctor.sh" \
            --replace-fail \
              "local desktop_file='/usr/share/applications/wispr-flow.desktop'" \
              'local desktop_file="''${WISPR_DESKTOP_FILE:-/usr/share/applications/wispr-flow.desktop}"'
    '';
  };
in
appimageTools.wrapAppImage {
  inherit pname version;
  src = appimageContents;

  nativeBuildInputs = [ makeWrapper ];
  extraPkgs = pkgs: [
    pkgs.at-spi2-core
    wl-clipboard
    xclip
    xsel
  ];

  extraInstallCommands = ''
    mv "$out/bin/${pname}" "$out/bin/.${pname}-unwrapped"
    makeWrapper "$out/bin/.${pname}-unwrapped" "$out/bin/${pname}" \
      --set CHROME_DEVEL_SANDBOX /run/wrappers/bin/__chromium-suid-sandbox \
      --set WISPR_DESKTOP_FILE "$out/share/applications/${pname}.desktop"

    install -Dm444 \
      ${appimageContents}/ai.wisprflow.WisprFlow.desktop \
      "$out/share/applications/${pname}.desktop"
    substituteInPlace "$out/share/applications/${pname}.desktop" \
      --replace-fail 'Exec=AppRun %U' 'Exec=wispr-flow %U'

    cp -r ${appimageContents}/usr/share/icons "$out/share/"
    cp -r ${appimageContents}/usr/share/metainfo "$out/share/"
  '';

  meta = {
    description = "Unofficial Linux package of the Wispr Flow voice-dictation app";
    homepage = "https://github.com/wispr-flow-linux/wispr-flow-linux";
    license = lib.licenses.unfree;
    mainProgram = pname;
    platforms = [ "x86_64-linux" ];
    sourceProvenance = with lib.sourceTypes; [ binaryNativeCode ];
  };
}
