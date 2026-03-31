{inputs, mkDevEnvironment, ...}: {
  perSystem = {system, ...}: let
    env = mkDevEnvironment system;
  in {
    formatter = env.pkgsStable.alejandra;

    packages = {
      screenpipe-app = env.pkgsUnstable.callPackage ../../packages/screenpipe/default.nix {};
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
