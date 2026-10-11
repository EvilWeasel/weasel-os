{
  lib,
  python3,
  fetchFromGitHub,
  gzip,
  gnutar,
  lzfse,
}:

python3.pkgs.buildPythonApplication rec {
  pname = "asahi-fwextract";
  version = "0.9.2";

  # tracking version: https://packages.fedoraproject.org/pkgs/asahi-installer/python3-asahi_firmware/
  src = fetchFromGitHub {
    owner = "AsahiLinux";
    repo = "asahi-installer";
    rev = "v${version}";
    hash = "sha256-q+J3/q7SP9KSkoyrL9uvI4wGls/16CUXxMFcUaz+ytM=";
  };

  postPatch = ''
    substituteInPlace asahi_firmware/img4.py \
      --replace-fail 'liblzfse.so' '${lzfse}/lib/liblzfse.so'
    substituteInPlace asahi_firmware/update.py \
      --replace-fail '"tar"' '"${gnutar}/bin/tar"' \
      --replace-fail '"xf"' '"-x", "-I", "${gzip}/bin/gzip", "-f"'
  '';

  nativeBuildInputs = [ python3.pkgs.setuptools ];

  doCheck = false;
}
