{
  lib,
  stdenv,
  fetchFromGitHub,
  rustPlatform,
  pkg-config,
  bun,
  nodejs_22,
  jq,
  cargo-tauri,
  wrapGAppsHook4,
  makeWrapper,
  writableTmpDirAsHomeHook,
  rustc,
  cargo,
  rustfmt,
  clippy,
  cmake,
  clang,
  bzip2,
  xz,
  zstd,
  glib,
  gtk3,
  webkitgtk_4_1,
  libsoup_3,
  glib-networking,
  openssl,
  sqlite,
  ffmpeg,
  tesseract5,
  at-spi2-core,
  libpulseaudio,
  alsa-lib,
  xdotool,
  libxkbcommon,
  libX11,
  libXtst,
  libXext,
  libXrandr,
  libXinerama,
  libXcursor,
  libXi,
  mesa,
  libsecret,
  libayatana-appindicator,
  libsamplerate,
  webrtc-audio-processing,
  pipewire,
  openblas,
  bzip3,
  oniguruma,
  zlib,
  librsvg,
}:
let
  version = "2.2.293";
  sourceTag = "app-v${version}";

  src = fetchFromGitHub {
    owner = "screenpipe";
    repo = "screenpipe";
    tag = sourceTag;
    hash = "sha256-Gtv42FHImYuOHo6shySiIQDbcNeqGciLy9tmKHZ+BnY=";
  };

  cargoTauri = cargo-tauri.overrideAttrs (_: rec {
    version = "2.10.0";
    src = fetchFromGitHub {
      owner = "tauri-apps";
      repo = "tauri";
      tag = "tauri-cli-v${version}";
      hash = "sha256-aaUr+6CiH+5e03ZzPexMTYavTmJRKqw/5PnyZqP2/f0=";
    };
    cargoHash = lib.fakeHash;
  });

  nodeModules = stdenv.mkDerivation {
    pname = "screenpipe-node-modules";
    inherit version src;

    sourceRoot = "source/apps/screenpipe-app-tauri";

    nativeBuildInputs = [
      bun
      writableTmpDirAsHomeHook
    ];

    dontConfigure = true;

    buildPhase = ''
      runHook preBuild
      bun install --frozen-lockfile --allow-scripts --no-progress
      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall
      mkdir -p $out
      cp -R node_modules $out/node_modules
      runHook postInstall
    '';

    outputHashMode = "recursive";
    outputHashAlgo = "sha256";
    outputHash = lib.fakeHash;
  };
in
rustPlatform.buildRustPackage rec {
  pname = "screenpipe-app";
  inherit version src;

  cargoHash = lib.fakeHash;
  buildAndTestSubdir = "apps/screenpipe-app-tauri/src-tauri";
  cargoBuildType = "release";
  doCheck = false;

  nativeBuildInputs = [
    cargoTauri.passthru.hook
    bun
    nodejs_22
    jq
    pkg-config
    wrapGAppsHook4
    makeWrapper
    rustPlatform.bindgenHook
    cmake
    clang
  ];

  buildInputs = [
    bzip2
    xz
    zstd
    glib
    gtk3
    webkitgtk_4_1
    libsoup_3
    glib-networking
    openssl
    sqlite
    ffmpeg
    tesseract5
    at-spi2-core
    libpulseaudio
    alsa-lib
    xdotool
    libxkbcommon
    libX11
    libXtst
    libXext
    libXrandr
    libXinerama
    libXcursor
    libXi
    mesa
    libsecret
    libayatana-appindicator
    libsamplerate
    webrtc-audio-processing
    pipewire
    openblas
    bzip3
    oniguruma
    zlib
    librsvg
  ];

  env = {
    CARGO_BUILD_JOBS = "16";
    ZSTD_SYS_USE_PKG_CONFIG = "true";
  };

  postPatch = ''
    rm -rf apps/screenpipe-app-tauri/node_modules
    cp -R ${nodeModules}/node_modules apps/screenpipe-app-tauri/node_modules
    chmod -R +w apps/screenpipe-app-tauri/node_modules
    patchShebangs --build apps/screenpipe-app-tauri/node_modules

    python <<'PY'
    import json
    from pathlib import Path

    base = Path("apps/screenpipe-app-tauri/src-tauri")

    def patch_json(path, updater):
        data = json.loads(path.read_text())
        updater(data)
        path.write_text(json.dumps(data, indent=2) + "\n")

    def patch_common(data):
        data["build"]["beforeBuildCommand"] = "true"
        data["bundle"]["externalBin"] = []
        updater = data.get("plugins", {}).get("updater")
        if updater is not None:
            updater["active"] = False
            updater["endpoints"] = []

    for name in ("tauri.conf.json", "tauri.prod.conf.json"):
        patch_json(base / name, patch_common)

    def patch_linux(data):
        bundle = data.setdefault("bundle", {})
        bundle["externalBin"] = []
        linux = bundle.setdefault("linux", {})
        linux["deb"] = {"depends": []}
        linux.pop("appimage", None)

    patch_json(base / "tauri.linux.conf.json", patch_linux)
    PY
  '';

  preBuild = ''
    export HOME="$TMPDIR"
    mkdir -p "$TMPDIR/openblas/lib"
    ln -sf ${openblas}/lib/libopenblas.so "$TMPDIR/openblas/lib/liblibopenblas.so"
    ln -sf ${openblas}/lib/libopenblas.a "$TMPDIR/openblas/lib/liblibopenblas.a"
    export OPENBLAS_PATH="$TMPDIR/openblas"

    pushd apps/screenpipe-app-tauri
    ./node_modules/.bin/next build
    popd
  '';

  postInstall = ''
    wrapProgram "$out/bin/screenpipe" \
      --prefix PATH : ${lib.makeBinPath [
        bun
        ffmpeg
        tesseract5
        xdotool
      ]} \
      --set TESSDATA_PREFIX "${tesseract5}/share/tessdata"
  '';

  meta = with lib; {
    description = "Screenpipe desktop app";
    homepage = "https://github.com/screenpipe/screenpipe";
    license = with licenses; [
      asl20
      mit
    ];
    platforms = platforms.linux;
    mainProgram = "screenpipe";
  };
}
