{
  gitUsername = "evilweasel";
  gitEmail = "38261180+EvilWeasel@users.noreply.github.com";
  gitSigningKey = "7D184861D38A4EA986C541FC9B2586DEDAFE5BEF";

  browser = "none";
  terminal = "bash";
  keyboardLayout = "de";
  consoleKeyMap = "de";

  diskDevice = "/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi0";
  grubDevice = "/dev/sda";

  uplink = {
    macAddress = "1a:e8:d4:bc:74:ed";
    ipv4Address = "76.13.6.180/24";
    ipv4Gateway = "76.13.6.254";
    ipv6Address = "2a02:4780:41:8a8f::1/48";
    ipv6Gateway = "2a02:4780:41::1";
    dns = [
      "153.92.2.6"
      "1.1.1.1"
      "8.8.4.4"
    ];
  };
}
