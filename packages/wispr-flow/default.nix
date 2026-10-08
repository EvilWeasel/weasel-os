{
  appimageTools,
  fetchFromGitHub,
  fetchurl,
  lib,
  makeWrapper,
  rustPlatform,
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

  # Keep the proprietary AppImage pinned, but replace its helper with a small,
  # reviewed source patch. The helper release is independently content-addressed.
  helperSrc = fetchFromGitHub {
    owner = "wispr-flow-linux";
    repo = "helper";
    rev = "v0.1.2";
    hash = "sha256-VH5rJ2wZd482TcDZKAQZHqeqLk443wkEIStxIjouVlU=";
  };

  linuxHelper = rustPlatform.buildRustPackage {
    pname = "wispr-flow-linux-helper";
    version = "0.1.2-release-all-keys";
    src = helperSrc;
    cargoLock.lockFile = "${helperSrc}/Cargo.lock";
    patches = [ ./release-all-uinput-keys.patch ];
    doCheck = true;
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
          $'_doctor_check_sandbox() {\n\tlocal electron_path="''${1:-}"' \
          $'_doctor_check_sandbox() {\n\tlocal electron_path="''${1:-}"\n\tif [[ -n ''${CHROME_DEVEL_SANDBOX:-} && -x ''${CHROME_DEVEL_SANDBOX:-} && -u ''${CHROME_DEVEL_SANDBOX:-} ]]; then\n\t\t_pass "chrome-sandbox: external setuid helper OK ($CHROME_DEVEL_SANDBOX)"\n\t\treturn\n\tfi'

      substituteInPlace "$out/usr/lib/wispr-flow/doctor.sh" \
        --replace-fail \
          "local desktop_file='/usr/share/applications/wispr-flow.desktop'" \
          'local desktop_file="''${WISPR_DESKTOP_FILE:-/usr/share/applications/wispr-flow.desktop}"'

      install -Dm755 \
        ${linuxHelper}/bin/wispr-flow-linux-helper \
        "$out/usr/lib/wispr-flow/resources/Release/wispr-flow-linux-helper"
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

    install -Dm444 /dev/stdin \
      "$out/lib/udev/rules.d/70-wispr-flow-uinput.rules" <<'UDEV'
    # Wispr Flow: active-session access for text injection and push-to-talk.
    KERNEL=="uinput", SUBSYSTEM=="misc", OPTIONS+="static_node=uinput", TAG+="uaccess", GROUP="input", MODE="0660"
    SUBSYSTEM=="input", KERNEL=="event*", TAG+="uaccess", GROUP="input", MODE="0660"
    UDEV
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
