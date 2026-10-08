{ lib, pkgs, ... }:
let
  reserveGiB = 50;
  reserveBytes = reserveGiB * 1024 * 1024 * 1024;
  spaceCheck = pkgs.writeShellScript "snapper-home-space-check" ''
    set -euo pipefail

    # ExecCondition reserves 1-254 for a clean skip; other failures must surface.
    ${pkgs.btrfs-progs}/bin/btrfs subvolume show /home/.snapshots >/dev/null || exit 255
    ${pkgs.snapper}/bin/snapper -c home cleanup timeline || exit 255
    available_bytes=$(${pkgs.coreutils}/bin/df --block-size=1 --output=avail /home | ${pkgs.coreutils}/bin/tail -n 1) || exit 255
    if (( available_bytes < ${toString reserveBytes} )); then
      echo "Skipping home snapshot: less than ${toString reserveGiB} GiB available after cleanup."
      exit 1
    fi
  '';
in
{
  services.snapper = {
    persistentTimer = true;
    cleanupInterval = lib.mkForce "1h";
    configs.home = lib.mkForce {
      SUBVOLUME = "/home";
      FSTYPE = "btrfs";
      TIMELINE_CREATE = true;
      TIMELINE_CLEANUP = true;
      TIMELINE_LIMIT_HOURLY = 0;
      # The range permits extra cleanup under disk pressure, including the last
      # eligible snapshot. A fixed count disables space-aware cleanup.
      TIMELINE_LIMIT_DAILY = "0-7";
      TIMELINE_LIMIT_WEEKLY = 0;
      TIMELINE_LIMIT_MONTHLY = 0;
      TIMELINE_LIMIT_QUARTERLY = 0;
      TIMELINE_LIMIT_YEARLY = 0;
      # FREE_LIMIT uses filesystem free space and works without Btrfs quotas.
      FREE_LIMIT = "${toString reserveGiB}GiB";
    };
  };

  # NixOS writes Snapper's config but does not create its snapshot subvolume.
  systemd.tmpfiles.rules = [ "v /home/.snapshots 0700 root root -" ];
  systemd.services.snapper-timeline = {
    requires = [ "systemd-tmpfiles-setup.service" ];
    after = [ "systemd-tmpfiles-setup.service" ];
    unitConfig.RequiresMountsFor = "/home";
    # The native timeline helper does not check FREE_LIMIT before creation.
    serviceConfig.ExecCondition = spaceCheck;
  };
}
