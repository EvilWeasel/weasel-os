{
  config,
  lib,
  ...
}: {
  drivers.nvidia.enable = true;

  drivers.nvidia-prime = {
    enable = true;
    intelBusID = "PCI:0:2:0";
    nvidiaBusID = "PCI:1:0:0";
  };

  services.xserver.videoDrivers = ["nvidia"];

  hardware = {
    enableRedistributableFirmware = true;
    graphics = {
      enable = true;
      enable32Bit = true;
    };
    nvidia = {
      modesetting.enable = lib.mkForce true;
      powerManagement.enable = lib.mkForce false;
      open = lib.mkForce false;
      package = lib.mkForce config.boot.kernelPackages.nvidiaPackages.production;
    };
  };
}
