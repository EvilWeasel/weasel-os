{ pkgs, pkgsUnstable }:
pkgsUnstable.proton-pass-cli.overrideAttrs (old: {
  version = "2.4.2";
  src = pkgs.fetchurl {
    url = "https://proton.me/download/pass-cli/2.4.2/pass-cli-linux-x86_64";
    hash = "sha256-QIm99ZgRQKxb7mXS15v5h2dTf1TTMZe3nl+GxjBxSEI=";
  };
  buildInputs = (old.buildInputs or [ ]) ++ [ pkgs.dbus ];
})
