{
  stdenvNoCC,
  fetchurl,
  lib,
}:

stdenvNoCC.mkDerivation (finalAttrs: {
  pname = "codex";
  version = "0.153.3";

  src = fetchurl {
    url = "https://registry.npmjs.org/@openai/codex/-/codex-${finalAttrs.version}-linux-x64.tgz";
    hash = "sha256-UFktUtFpRhX5zPPKUEMrtFIal8vJOqLDl2j6ZZ24FbU=";
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
