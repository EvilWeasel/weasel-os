{
  stdenvNoCC,
  fetchurl,
  lib,
}:

stdenvNoCC.mkDerivation (finalAttrs: {
  pname = "codex";
  version = "0.160.0";

  src = fetchurl {
    url = "https://registry.npmjs.org/@openai/codex/-/codex-${finalAttrs.version}-linux-x64.tgz";
    hash = "sha256-N6QdYcM5kYK4xye3cJDMehVmvYSdDwkHCgu8b+xMWNw=";
  };

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/lib/codex" "$out/bin"
    cp -a vendor/x86_64-unknown-linux-musl/. "$out/lib/codex/"
    ln -s "$out/lib/codex/bin/codex" "$out/bin/codex"
    ln -s "$out/lib/codex/bin/codex-code-mode-host" "$out/bin/codex-code-mode-host"
    runHook postInstall
  '';

  meta = {
    description = "Pinned OpenAI Codex CLI";
    homepage = "https://github.com/openai/codex";
    license = lib.licenses.asl20;
    platforms = [ "x86_64-linux" ];
    mainProgram = "codex";
    sourceProvenance = with lib.sourceTypes; [ binaryNativeCode ];
  };
})
