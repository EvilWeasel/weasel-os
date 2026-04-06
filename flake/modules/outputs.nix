{
  inputs,
  mkDevEnvironment,
  ...
}: {
  perSystem = {system, ...}: let
    env = mkDevEnvironment system;
    screenpipeApp = env.pkgsUnstable.callPackage ../../packages/screenpipe/default.nix {};
  in {
    formatter = env.pkgsStable.alejandra;

    packages = {
      screenpipe-app = screenpipeApp;
      screenpipe-xcap-probe = env.pkgsStable.callPackage ../../packages/screenpipe-xcap-probe/default.nix {};
      screenpipe-lab = env.pkgsStable.callPackage ../../scripts/weasel-screenpipe-lab.nix {
        inherit screenpipeApp;
      };
      t3code = inputs.t3code.packages.${system}.default;
    };

    devShells = {
      dev = env.devShell;
      default = env.devShell;
    };

    apps.dev = {
      type = "app";
      program = "${env.devShellLauncher}/bin/weasel-dev-shell";
    };
  };
}
