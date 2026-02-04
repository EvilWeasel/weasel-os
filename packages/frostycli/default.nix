{ lib
, stdenv
, fetchFromGitHub
, dotnet-sdk_8
, dotnet-runtime_8
}:

stdenv.mkDerivation rec {
  pname = "frostycli";
  version = "master";

  src = fetchFromGitHub {
    owner = "HarGabt";
    repo = "FrostyToolsuite";
    rev = "master";
    # fill this after first build
    hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
  };

  nativeBuildInputs = [
    dotnet-sdk_8
  ];

  buildPhase = ''
    runHook preBuild

    dotnet publish FrostyCli/FrostyCli.csproj \
      --configuration Release \
      --framework net8.0 \
      --output publish \
      /p:UseAppHost=false

    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall

    mkdir -p $out/lib/frostycli
    cp -r publish/* $out/lib/frostycli/

    mkdir -p $out/bin
    cat > $out/bin/frostycli <<EOF
    #!${stdenv.shell}
    exec ${dotnet-runtime_8}/bin/dotnet \
      $out/lib/frostycli/FrostyCli.dll "\$@"
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

