{
  clang,
  libgbm,
  libglvnd,
  libX11,
  libxcb,
  libXrandr,
  mesa,
  pipewire,
  pkg-config,
  rustPlatform,
  wayland,
}:
rustPlatform.buildRustPackage {
  pname = "screenpipe-xcap-probe";
  version = "0.1.0";

  src = ./.;

  cargoLock = {
    lockFile = ./Cargo.lock;
  };

  nativeBuildInputs = [
    clang
    pkg-config
    rustPlatform.bindgenHook
  ];

  buildInputs = [
    libgbm
    libglvnd
    libX11
    libxcb
    libXrandr
    mesa
    pipewire
    wayland
  ];

  meta = {
    mainProgram = "screenpipe-xcap-probe";
  };
}
