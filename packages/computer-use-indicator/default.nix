{
  lib,
  stdenv,
  pkg-config,
  gtk3,
  gtk-layer-shell,
  makeWrapper,
  python3,
  niri,
}:
stdenv.mkDerivation {
  pname = "weasel-computer-use-indicator";
  version = "0.1.0";
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./renderer.c
      ./indicator.py
    ];
  };
  strictDeps = true;
  nativeBuildInputs = [
    pkg-config
    makeWrapper
  ];
  buildInputs = [
    gtk3
    gtk-layer-shell
  ];
  buildPhase = ''
    runHook preBuild
    $CC -std=c11 -O2 -Wall -Wextra -Werror \
      renderer.c -o weasel-computer-use-indicator-renderer \
      $(pkg-config --cflags --libs gtk+-3.0 gtk-layer-shell-0)
    runHook postBuild
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/bin" "$out/libexec"
    cp weasel-computer-use-indicator-renderer "$out/libexec/"
    cp indicator.py "$out/libexec/indicator.py"
    makeWrapper ${python3}/bin/python3 "$out/bin/weasel-computer-use-indicator" \
      --add-flags "$out/libexec/indicator.py" \
      --set WEASEL_INDICATOR_RENDERER "$out/libexec/weasel-computer-use-indicator-renderer" \
      --set WEASEL_INDICATOR_NIRI "${niri}/bin/niri"
    runHook postInstall
  '';
  meta = {
    description = "Click-through, task-owned Wayland Computer Use monitor indicator";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "weasel-computer-use-indicator";
  };
}
