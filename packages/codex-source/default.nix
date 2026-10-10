{
  lib,
  fetchzip,
  fetchurl,
  clang,
  cmake,
  gitMinimal,
  makeBinaryWrapper,
  pkg-config,
  libclang,
  openssl,
  alsa-lib,
  libcap,
  ripgrep,
  bubblewrap,
}:
let
  # Keep this upstream workspace's required Rust independent of the rolling
  # package input. Libraries still use the caller's configured package set.
  toolchain = import ./toolchain.nix { };
  src = fetchzip {
    name = "codex-c1382380de69521303b416720a52f42d51af6248";
    extension = "tar.gz";
    url = "https://codeload.github.com/openai/codex/tar.gz/c1382380de69521303b416720a52f42d51af6248";
    hash = "sha256-YG/9hFOCl4cMYzjaH/3gBid4osxcrvCYQUDDzdbIygo=";
  };
  v8 = fetchurl {
    name = "librusty_v8-ptrcomp-sandbox-150.4.0";
    url = "https://github.com/openai/codex/releases/download/rusty-v8-v150.4.0/librusty_v8_ptrcomp_sandbox_release_x86_64-unknown-linux-gnu.a.gz";
    hash = "sha256-o1x10fJuapg4haRbM0kKTr5U8FBQVosyuJz7QhswtYM=";
  };
  v8Binding = fetchurl {
    name = "rusty-v8-ptrcomp-sandbox-binding-150.4.0";
    url = "https://github.com/openai/codex/releases/download/rusty-v8-v150.4.0/src_binding_ptrcomp_sandbox_release_x86_64-unknown-linux-gnu.rs";
    hash = "sha256-dyeCauR5vbZF6Acjn7EtH44uI956bPFvXuWSaQ0dhQY=";
  };
in
assert toolchain.rustc.version == "1.95.0";
toolchain.rustPlatform.buildRustPackage {
  pname = "codex-scoped-cancel";
  version = "0.162.0";
  inherit src;
  cargoHash = "sha256-UTu+ws1DqL375C+1jaVI9HBqDHnTuAQr7/h1rSzsEzg=";
  sourceRoot = "${src.name}/codex-rs";
  patches = [
    ./codex-v0162-scoped-cancel.patch
    ./scoped-cancel-memory-tests.patch
  ];
  patchFlags = [ "-p2" ];
  cargoBuildFlags = [
    "--package"
    "codex-cli"
    "--bin"
    "codex"
    "--package"
    "codex-code-mode-host"
    "--bin"
    "codex-code-mode-host"
  ];
  nativeBuildInputs = [
    clang
    cmake
    gitMinimal
    makeBinaryWrapper
    pkg-config
  ];
  buildInputs = [
    libclang
    openssl
    alsa-lib
    libcap
  ];
  env = {
    LIBCLANG_PATH = "${lib.getLib libclang}/lib";
    RUSTY_V8_ARCHIVE = v8;
    RUSTY_V8_SRC_BINDING_PATH = v8Binding;
    STABLE_GIT_COMMIT = "c1382380de69521303b416720a52f42d51af6248";
    CC = "${clang}/bin/clang";
    CXX = "${clang}/bin/clang++";
    CARGO_BUILD_JOBS = "2";
    CARGO_PROFILE_RELEASE_DEBUG = "0";
    CARGO_PROFILE_RELEASE_LTO = "off";
    CARGO_PROFILE_RELEASE_CODEGEN_UNITS = "16";
  };
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    cargo test --offline --release --target x86_64-unknown-linux-gnu -j2 \
      --package codex-rmcp-client --lib request_cancel_guard::tests
    cargo test --offline --locked --release --target x86_64-unknown-linux-gnu -j2 \
      --package codex-core --lib tools::code_mode::owner_cancellation::tests
    cargo test --offline --locked --release --target x86_64-unknown-linux-gnu -j2 \
      --package codex-core --lib tools::code_mode::callback_admission::tests
    cargo test --offline --locked --release --target x86_64-unknown-linux-gnu -j2 \
      --package codex-core --lib tools::code_mode::delegate::tests
    runHook postCheck
  '';
  postInstall = ''
    test -x "$out/bin/codex"
    test -x "$out/bin/codex-code-mode-host"
    mkdir -p "$out/lib/codex/bin"
    ln -s ../../../bin/codex "$out/lib/codex/bin/codex"
    ln -s ../../../bin/codex-code-mode-host "$out/lib/codex/bin/codex-code-mode-host"
  '';
  postFixup = ''
    wrapProgram "$out/bin/codex" --prefix PATH : ${
      lib.makeBinPath [
        ripgrep
        bubblewrap
      ]
    }
  '';
  doInstallCheck = true;
  installCheckPhase = ''
    "$out/bin/codex" --version | grep -F '0.162.0'
    "$out/bin/codex-code-mode-host" --help > /dev/null
  '';
  meta = {
    description = "Pinned Codex 0.162.0 with request-scoped MCP cancellation";
    homepage = "https://github.com/openai/codex";
    license = lib.licenses.asl20;
    platforms = [ "x86_64-linux" ];
    mainProgram = "codex";
  };
}
