{ pkgs, ... }:
pkgs.writeShellApplication {
  name = "codex-artifact-run";
  text = ''
    if (( $# == 0 )); then
      echo "Usage: codex-artifact-run <bundled artifact command> [arguments...]" >&2
      exit 64
    fi

    # The imported runtime's LibreOffice needs lcms2 and OpenSSL-versioned
    # libcurl on NixOS. Scope these libraries to the requested artifact process.
    export LD_LIBRARY_PATH="${
      pkgs.lib.makeLibraryPath [
        pkgs.lcms2
        pkgs.curl
      ]
    }''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    exec "$@"
  '';
}
