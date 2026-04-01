{host, lib, ...}: let
  inherit (import ./variables.nix) diskDevice;
in {
  disko.devices.disk.main = {
    type = "disk";
    device = lib.mkDefault diskDevice;
    content = {
      type = "gpt";
      partitions = {
        BIOS = {
          type = "EF02";
          size = "4M";
        };

        boot = {
          size = "512M";
          content = {
            type = "filesystem";
            format = "ext4";
            mountpoint = "/boot";
            mountOptions = [
              "defaults"
            ];
          };
        };

        root = {
          size = "100%";
          content = {
            type = "btrfs";
            extraArgs = ["-f"];
            subvolumes = {
              "/root" = {
                mountpoint = "/";
                mountOptions = ["compress=zstd" "noatime"];
              };
              "/nix" = {
                mountpoint = "/nix";
                mountOptions = ["compress=zstd" "noatime"];
              };
              "/home" = {
                mountpoint = "/home";
                mountOptions = ["compress=zstd" "noatime"];
              };
              "/persist" = {
                mountpoint = "/persist";
                mountOptions = ["compress=zstd" "noatime"];
              };
              "/log" = {
                mountpoint = "/var/log";
                mountOptions = ["compress=zstd" "noatime"];
              };
            };
          };
        };
      };
    };
  };

  fileSystems."/boot".neededForBoot = true;
  fileSystems."/persist".neededForBoot = true;
}
