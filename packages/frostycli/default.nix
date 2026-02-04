{
  lib,
  stdenv,
  fetchFromGitHub,
  mono,
  msbuild,
  nuget,
}:

stdenv.mkDerivation rec {
  pname = "frostycli";
  version = "c32856d45d7438379f295ffba46b2bd3c39abc5d";

  src = fetchFromGitHub {
    owner = "HarGabt";
    repo = "FrostyToolsuite";
    rev = "c32856d45d7438379f295ffba46b2bd3c39abc5d";
    hash = "sha256-cDTpIy6ittc6ShVtPplKapXhmVVbGZbYgbrDbjZqjNU=";
  };

  nativeBuildInputs = [
    mono
    msbuild
    nuget
  ];

  buildPhase = ''
    runHook preBuild

    export HOME="$TMPDIR"
    nuget restore FrostyCmd/FrostyCmd.csproj -PackagesDirectory packages
    msbuild FrostyCmd/FrostyCmd.csproj \
      /p:Configuration="Release - Final" \
      /p:Platform="x64" \
      /p:OutputPath=publish/

    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall

    mkdir -p $out/lib/frostycli
    cp -r publish/* $out/lib/frostycli/

    mkdir -p $out/bin
    cat > $out/bin/frostycli <<EOF
    #!${stdenv.shell}
    exec ${mono}/bin/mono \
      $out/lib/frostycli/FrostyCmd.exe "\$@"
    EOF

    chmod +x $out/bin/frostycli

    runHook postInstall
  '';

  meta = with lib; {
    description = "Frosty Mod Manager CLI for Frostbite games";
    license = licenses.mit;
    platforms = platforms.linux;
    mainProgram = "frostycli";
  };
}
