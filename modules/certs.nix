
{ lib, pkgs, ... }:

let
  # Funktion: Baut eine Derivation für eine einzelne Datei
  mkCert = name: path: pkgs.stdenv.mkDerivation {
    inherit name;

    src = path;

    dontBuild = true;

    installPhase = ''
      mkdir -p $out
      cp $src $out/${name}.cer
    '';
  };

in {
  options.certs = lib.mkOption {
    description = "Imported certificate files as derivations";
    type = lib.types.attrsOf lib.types.path;
    default = { };
    readOnly = true;
  };

  # config.certs wird dynamisch gebaut
  config = let
    # Liste aller Zert-Dateien, die du importieren willst
    # HIER ändern: einfach weitere eintragen
    certFiles = {
      boxcert = ../../certs/boxcert.cer;
      # zweiteCafile = ../../certs/zweite.cer;
      # nochEins = ../../certs/foo.pem;
    };

    certDerivations =
      lib.mapAttrs
        (name: path: (mkCert name path) + "/${name}.cer")
        certFiles;

  in {
    certs = certDerivations;
  };
}
