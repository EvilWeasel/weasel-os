{
  lib,
  stdenvNoCC,
  python3,
  makeWrapper,
}:
stdenvNoCC.mkDerivation {
  pname = "weasel-ui-decisions";
  version = "0.1.0";
  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./decisiond.py
      ./mcp.py
      ./benchmark.py
      ./test_offline.py
      ./README.md
    ];
  };
  nativeBuildInputs = [
    python3
    makeWrapper
  ];
  dontConfigure = true;
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    python3 -m py_compile decisiond.py mcp.py benchmark.py test_offline.py
    python3 test_offline.py
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/libexec/weasel-ui-decisions" "$out/bin" "$out/share/doc/weasel-ui-decisions"
    cp decisiond.py mcp.py benchmark.py "$out/libexec/weasel-ui-decisions/"
    cp README.md "$out/share/doc/weasel-ui-decisions/"
    makeWrapper ${python3}/bin/python3 "$out/bin/weasel-ui-decisions" \
      --add-flags "$out/libexec/weasel-ui-decisions/decisiond.py"
    makeWrapper ${python3}/bin/python3 "$out/bin/weasel-ui-decisions-mcp" \
      --add-flags "$out/libexec/weasel-ui-decisions/mcp.py"
    makeWrapper ${python3}/bin/python3 "$out/bin/weasel-ui-decisions-benchmark" \
      --add-flags "$out/libexec/weasel-ui-decisions/benchmark.py"
    runHook postInstall
  '';
  meta = {
    description = "Optional typed UI evaluator with a persistent budget ledger; no desktop input";
    platforms = [ "x86_64-linux" ];
    mainProgram = "weasel-ui-decisions";
  };
}
