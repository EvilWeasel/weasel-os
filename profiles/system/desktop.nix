{username, ...}: {
  drivers = {
    amdgpu.enable = false;
    nvidia.enable = true;
    nvidia-prime = {
      enable = false;
      intelBusID = "";
      nvidiaBusID = "";
    };
    intel.enable = false;
  };

  local.hardware-clock.enable = false;

  programs = {
    gnupg.agent.enableSSHSupport = true;
    steam = {
      gamescopeSession.enable = true;
      dedicatedServer.openFirewall = true;
    };
  };

  services = {
    desktopManager.plasma6.enable = true;
    blueman.enable = false;
  };

  hardware = {
    openrazer.enable = true;
    bluetooth = {
      enable = false;
      powerOnBoot = false;
    };
  };

  fileSystems."/home/${username}/fastboi" = {
    device = "/dev/disk/by-uuid/c2164edc-6381-4245-8022-bf7c849686f2";
    fsType = "btrfs";
  };
}
