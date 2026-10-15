{ pkgs, pkgsUnstable }:
let
  inherit (pkgs) lib;
  codex = pkgsUnstable.callPackage ../codex-source { };
  acp = pkgsUnstable.callPackage ../codex-acp.nix { codexPackage = codex; };
  # Keep the stable package recipe/libraries. Override only the reviewed native
  # release manifest, not the global package input or its auto-updater policy.
  claude = pkgs.claude-code.override {
    manifest = {
      version = "2.1.300";
      platforms.linux-x64 = {
        binary = "claude";
        checksum = "674deba0bba9aee479f4503c438b49303b6fdd304b9a471b14977aaec5215453";
      };
    };
  };
  metadataFor = claudePackage: role: {
    schema = 1;
    system = "x86_64-linux";
    inherit role;
    codex = {
      version = codex.version;
      storePath = toString codex;
      sourceRevision = "c1382380de69521303b416720a52f42d51af6248";
      patches = {
        "codex-v0162-scoped-cancel.patch" =
          builtins.hashFile "sha256" ../codex-source/codex-v0162-scoped-cancel.patch;
        "scoped-cancel-memory-tests.patch" =
          builtins.hashFile "sha256" ../codex-source/scoped-cancel-memory-tests.patch;
      };
    };
    claude = {
      version = claudePackage.version;
      storePath = toString claudePackage;
      recipe = "locked-stable-nixpkgs/claude-code";
    }
    // lib.optionalAttrs (role == "candidate") {
      manifestUrl = "https://downloads.claude.ai/claude-code-releases/2.1.300/manifest.json";
      manifestSha256 = "fb62dae2893ff954bbf8caa9f4b9345737b98a210e3a6085bf9feec9ddf5d9ca";
      binarySha256 = "674deba0bba9aee479f4503c438b49303b6fdd304b9a471b14977aaec5215453";
    };
    acp = {
      version = acp.version;
      storePath = toString acp;
      codexPath = "${codex}/bin/codex";
    };
  };
  mkBundle =
    claudePackage: role:
    let
      manifest = pkgs.writeText "provider-tools.json" (builtins.toJSON (metadataFor claudePackage role));
    in
    pkgs.stdenvNoCC.mkDerivation {
      pname = "weasel-provider-tools";
      version = "${codex.version}-${claudePackage.version}-${role}";
      dontUnpack = true;
      dontBuild = true;
      installPhase = ''
        mkdir -p "$out/bin"
        ln -s ${codex}/bin/codex "$out/bin/codex"
        ln -s ${codex}/bin/codex-code-mode-host "$out/bin/codex-code-mode-host"
        ln -s ${acp}/bin/codex-acp "$out/bin/codex-acp"
        ln -s ${claudePackage}/bin/claude "$out/bin/claude"
        cp ${manifest} "$out/provider-tools.json"
      '';
      doInstallCheck = true;
      installCheckPhase = ''
        "$out/bin/codex" --version | grep -F '${codex.version}'
        HOME="$TMPDIR" "$out/bin/claude" --version | grep -F '${claudePackage.version}'
        "$out/bin/codex-code-mode-host" --help > /dev/null
        grep -F '${codex}/bin/codex' ${acp}/bin/codex-acp
      '';
      passthru = {
        inherit
          codex
          claude
          acp
          launchers
          manager
          baseline
          ;
      };
    };
  baseline = mkBundle pkgs.claude-code "baseline";
  bundle = mkBundle claude "candidate";
  manager = pkgs.writeShellApplication {
    name = "weasel-provider-tools";
    runtimeInputs = [
      pkgs.nix
      pkgs.zstd
    ];
    text = ''
      exec ${pkgs.python3}/bin/python3 ${../../scripts/weasel-provider-tools.py} "$@"
    '';
  };
  # Resolve one complete generation once per launch. Existing processes keep
  # their executable and ACP's embedded CODEX_PATH from that generation.
  launchers = pkgs.runCommand "weasel-provider-launchers" { } ''
    mkdir -p "$out/bin"
    ${lib.concatMapStringsSep "\n"
      (name: ''
        cat > "$out/bin/${name}" <<'SCRIPT'
        #!${pkgs.bash}/bin/bash
        set -euo pipefail
        selector="$HOME/.local/state/weasel-provider-tools/current"
        if [[ -L "$selector" ]]; then
          generation="$(${pkgs.coreutils}/bin/readlink -e -- "$selector")"
          case "$generation" in /nix/store/*) ;; *) echo 'Invalid provider generation' >&2; exit 1 ;; esac
        elif [[ -e "$selector" ]]; then
          echo 'Provider selector is not a symlink' >&2; exit 1
        else
        echo 'Provider selection is not initialized; Root must qualify and select the existing baseline first' >&2
        exit 1
        fi
        exec "$generation/bin/${name}" "$@"
        SCRIPT
        chmod 0555 "$out/bin/${name}"
      '')
      [
        "codex"
        "codex-code-mode-host"
        "codex-acp"
        "claude"
      ]
    }
  '';
in
bundle
