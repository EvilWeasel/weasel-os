{
  lib,
  pkgs,
  ...
}: {
  # Temporary workaround for nixpkgs linux_zen PREEMPT regression on release-25.11.
  # Remove once upstream issue/PR is resolved:
  # - https://github.com/NixOS/nixpkgs/issues/498620
  # - https://github.com/NixOS/nixpkgs/pull/499620
  boot.kernelPackages = pkgs.linuxPackagesFor (
    pkgs.linuxPackages_zen.kernel.override {
      structuredExtraConfig = with lib.kernel; {
        PREEMPT = lib.mkOverride 90 no;
        PREEMPT_LAZY = lib.mkOverride 90 (option yes);
        PREEMPT_VOLUNTARY = lib.mkOverride 90 (option yes);
      };
    }
  );
}
