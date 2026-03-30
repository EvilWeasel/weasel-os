{
  lib,
  stdenv,
  fetchFromGitHub,
  runCommand,
  importNpmLock,
  python3,
  rustPlatform,
  pkg-config,
  bun,
  nodejs_22,
  jq,
  onnxruntime,
  cargo-tauri,
  wrapGAppsHook4,
  makeWrapper,
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
  libgbm,
  libsecret,
  libayatana-appindicator,
  libsamplerate,
  webrtc-audio-processing,
  pipewire,
  openblas,
  bzip3,
  oniguruma,
  vips,
  zlib,
  librsvg,
  libpng,
}:
let
  version = "2.2.293";
  sourceTag = "app-v${version}";

  upstreamSrc = fetchFromGitHub {
    owner = "screenpipe";
    repo = "screenpipe";
    tag = sourceTag;
    hash = "sha256-Gtv42FHImYuOHo6shySiIQDbcNeqGciLy9tmKHZ+BnY=";
  };

  src = runCommand "screenpipe-source-${version}" {} ''
    cp -R ${upstreamSrc} "$out"
    chmod -R +w "$out"

    ${python3}/bin/python <<'PY'
    import os
    from pathlib import Path

    cargo_toml_path = Path(os.environ["out"]) / "apps/screenpipe-app-tauri/src-tauri/Cargo.toml"
    lock_path = Path(os.environ["out"]) / "apps/screenpipe-app-tauri/src-tauri/Cargo.lock"
    removed = {
        "nokhwa-bindings-macos",
        "nokhwa-core",
        "tauri-nspanel",
        "windows-icons",
    }

    cargo_toml = cargo_toml_path.read_text()
    for needle in (
        'nokhwa-bindings-macos = { git = "https://github.com/CapSoftware/nokhwa", rev = "0d3d1f30a78b" }\n',
        'tauri-nspanel = { git = "https://github.com/ahkohd/tauri-nspanel", branch = "v2" }\n',
        'windows-icons = { git = "https://github.com/tribhuwan-kumar/windows-icons.git" }\n',
    ):
        cargo_toml = cargo_toml.replace(needle, "")
    cargo_toml_path.write_text(cargo_toml)

    sections = lock_path.read_text().split("\n[[package]]\n")
    rewritten = [sections[0]]

    for section in sections[1:]:
        name = None
        for line in section.splitlines():
            if line.startswith('name = "'):
                name = line[len('name = "'):-1]
                break
        if name in removed:
            continue

        if name == "screenpipe-app":
            lines = []
            for line in section.splitlines():
                stripped = line.strip()
                if stripped in {
                    '"nokhwa-bindings-macos",',
                    '"tauri-nspanel",',
                    '"windows-icons",',
                }:
                    continue
                lines.append(line)
            section = "\n".join(lines)

        rewritten.append(section)

    lock_path.write_text("\n[[package]]\n".join(rewritten))
    PY
  '';

  cargoTauri = rustPlatform.buildRustPackage (finalAttrs: {
      pname = "tauri";
      version = "2.10.0";
      auditable = false;

      src = fetchFromGitHub {
        owner = "tauri-apps";
        repo = "tauri";
        tag = "tauri-cli-v${finalAttrs.version}";
        hash = "sha256-aaUr+6CiH+5e03ZzPexMTYavTmJRKqw/5PnyZqP2/f0=";
      };

      cargoDeps = rustPlatform.fetchCargoVendor {
        inherit (finalAttrs)
          pname
          version
          src
          ;

        hash = "sha256-YoHQNqIfwV0zt9iZ7aKlW75KXPyeFgqkjEU5s980KW4=";
      };

      nativeBuildInputs = [
        pkg-config
      ];

      buildInputs = [
        bzip2
        xz
      ]
      ++ lib.optionals stdenv.hostPlatform.isLinux [
        zstd
      ];

      cargoBuildFlags = [
        "--package"
        "tauri-cli"
      ];
      cargoTestFlags = finalAttrs.cargoBuildFlags;

      env = lib.optionalAttrs stdenv.hostPlatform.isLinux {
        ZSTD_SYS_USE_PKG_CONFIG = true;
      };

      passthru = {
        inherit (cargo-tauri)
          gst-plugin
          ;

        hook = cargo-tauri.passthru.hook.override {
          cargo-tauri = finalAttrs.finalPackage;
        };
      };
    });

  nodeModules = importNpmLock.buildNodeModules {
    npmRoot = ./npm;
    nodejs = nodejs_22;
    derivationArgs = {
      pname = "screenpipe-node-modules";
      inherit version;
      nativeBuildInputs = [
        pkg-config
      ];
      buildInputs = [
        vips
        libpng
      ];
      env.SHARP_FORCE_GLOBAL_LIBVIPS = "1";
      npmRebuildFlags = [
        "--ignore-scripts"
      ];
    };
  };
in
rustPlatform.buildRustPackage rec {
  pname = "screenpipe-app";
  inherit version src;

  cargoRoot = "apps/screenpipe-app-tauri/src-tauri";
  cargoHash = "sha256-ttBOC3BYC4zJlvkfwdUfIkwKtMLsMM906IxmKr1yOqo=";
  buildAndTestSubdir = "apps/screenpipe-app-tauri/src-tauri";
  cargoBuildType = "release";
  doCheck = false;

  nativeBuildInputs = [
    cargoTauri.passthru.hook
    nodejs_22
    jq
    pkg-config
    wrapGAppsHook4
    makeWrapper
    python3
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
    libgbm
    libsecret
    libayatana-appindicator
    libsamplerate
    webrtc-audio-processing
    pipewire
    openblas
    onnxruntime
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
    layout = Path("apps/screenpipe-app-tauri/app/layout.tsx")

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

    layout_text = layout.read_text()
    layout_text = layout_text.replace('import { Inter } from "next/font/google";\n', "")
    layout_text = layout_text.replace('const inter = Inter({ subsets: ["latin"] });\n\n', "")
    layout_text = layout_text.replace(
        '<body className={`''${inter.className} scrollbar-hide ''${isSearch ? "bg-transparent" : ""}`}>',
        '<body className={`scrollbar-hide ''${isSearch ? "bg-transparent" : ""}`}>',
    )
    layout.write_text(layout_text)
    PY
  '';

  preBuild = ''
    export HOME="$TMPDIR"
    export PKG_CONFIG_PATH="${onnxruntime.dev}/lib/pkgconfig''${PKG_CONFIG_PATH:+:}$PKG_CONFIG_PATH"
    export ORT_LIB_LOCATION="${onnxruntime}"
    export NIX_CFLAGS_COMPILE="-D_POSIX_C_SOURCE=200809L -D_GNU_SOURCE ''${NIX_CFLAGS_COMPILE:+ }$NIX_CFLAGS_COMPILE"
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
