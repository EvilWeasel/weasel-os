{
  config,
  pkgsUnstable,
  ...
}:
{
  hardware.bluetooth = {
    enable = true;
    powerOnBoot = true;
    package = pkgsUnstable.bluez;
    settings.General = {
      ControllerMode = "dual";
      Experimental = true;
      Privacy = "device";
    };
  };

  services.pipewire.package = pkgsUnstable.pipewire;
  services.pipewire.wireplumber.package = pkgsUnstable.wireplumber;

  systemd.services.bluetooth.serviceConfig.ExecStart = [
    ""
    "${config.hardware.bluetooth.package}/libexec/bluetooth/bluetoothd -f /etc/bluetooth/main.conf -E -K"
  ];

  services.pipewire.wireplumber.extraConfig."10-bluetooth-audio" = {
    "wireplumber.settings" = {
      "bluetooth.autoswitch-to-headset-profile" = true;
    };

    "monitor.bluez.properties" = {
      "bluez5.roles" = [
        "a2dp_sink"
        "a2dp_source"
        "bap_sink"
        "bap_source"
        "hsp_hs"
        "hsp_ag"
        "hfp_hf"
        "hfp_ag"
      ];
      "bluez5.codecs" = [
        "sbc"
        "sbc_xq"
        "aac"
      ];
      "bluez5.enable-sbc-xq" = true;
      "bluez5.enable-msbc" = false;
      "bluez5.hfphsp-backend" = "native";
    };
  };
}
