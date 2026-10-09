{
  config,
  lib,
  pkgs,
  pkgsUnstable,
  inputs,
  ...
}:
let
  p = pkgsUnstable;
  codexPackage = pkgsUnstable.callPackage ../packages/codex-source { };
  codexAcp = p.callPackage ../packages/codex-acp.nix { inherit codexPackage; };
  serena = inputs.serena.packages.${pkgs.stdenv.hostPlatform.system}.default;
  languagePackages = with p; [
    nixd
    nil
    pyright
    ruff
    lua-language-server
    rust-analyzer
    rustc
    cargo
    rustPlatform.rustLibSrc
    typescript
    typescript-language-server
    vtsls
    bash-language-server
    shellcheck
    vscode-langservers-extracted
    yaml-language-server
    taplo
    qt6.qtdeclarative
    nodejs
    python3
    uv
  ];
  serenaWrapped = pkgs.symlinkJoin {
    name = "serena-with-language-servers";
    paths = [ serena ];
    nativeBuildInputs = [ pkgs.makeWrapper ];
    postBuild = ''
      wrapProgram $out/bin/serena --prefix PATH : ${lib.makeBinPath languagePackages} \
        --set-default RUST_SRC_PATH ${p.rustPlatform.rustLibSrc}
    '';
  };
  ls = exe: args: {
    ls_base_cmd = [ exe ];
    ls_args = args;
  };
  settings = pkgs.writeText "serena-lsp-settings.json" (
    builtins.toJSON {
      nix = ls "${p.nixd}/bin/nixd" [ ];
      python = ls "${p.pyright}/bin/pyright-langserver" [ "--stdio" ];
      typescript = ls "${p.typescript-language-server}/bin/typescript-language-server" [ "--stdio" ];
      rust = ls "${p.rust-analyzer}/bin/rust-analyzer" [ ];
      bash = ls "${p.bash-language-server}/bin/bash-language-server" [ "start" ];
      yaml = ls "${p.yaml-language-server}/bin/yaml-language-server" [ "--stdio" ];
      json = ls "${p.vscode-langservers-extracted}/bin/vscode-json-language-server" [ "--stdio" ];
      toml = ls "${p.taplo}/bin/taplo" [
        "lsp"
        "stdio"
      ];
      qml = ls "${p.qt6.qtdeclarative}/bin/qmlls" [ ];
    }
  );
  configPython = pkgs.python3.withPackages (ps: [
    ps.pyyaml
    ps.tomlkit
  ]);
in
{
  xdg.configFile."zed/settings.json".source = lib.mkForce (
    config.lib.file.mkOutOfStoreSymlink "${config.home.homeDirectory}/weasel-os/programs/zed/settings-laptop.json"
  );
  home.packages = languagePackages ++ [
    codexAcp
    serenaWrapped
  ];
  # Both clients use the same MCP entry. Keep credentials and all unrelated
  # mutable client settings out of the Nix store and preserve them on activation.
  home.activation.configureSerena = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    $DRY_RUN_CMD ${configPython}/bin/python ${../scripts/configure-serena.py} \
      ${lib.escapeShellArg config.home.homeDirectory} \
      ${serenaWrapped}/bin/serena ${settings}
  '';
}
