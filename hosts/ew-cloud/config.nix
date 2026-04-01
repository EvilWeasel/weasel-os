{
  config,
  inputs,
  lib,
  ...
}: let
  secretFile = ../../secrets/hosts/ew-cloud/secrets.yaml;
  hasSecrets = builtins.pathExists secretFile;
  inherit (import ./variables.nix) grubDevice uplink;
in {
  imports = [
    ../../profiles/system/common.nix
    ../../profiles/system/server.nix
    inputs.disko.nixosModules.disko
    ../../modules/nixos/roles/openclaw.nix
    ./hardware.nix
    ./disko.nix
    ./users.nix
  ];

  weasel.roles.openclaw.enable = true;

  boot.loader = {
    efi.canTouchEfiVariables = false;
    grub = {
      enable = true;
      device = grubDevice;
      efiSupport = false;
      configurationLimit = 10;
    };
  };

  networking = {
    useDHCP = lib.mkForce false;
    useNetworkd = lib.mkForce true;
  };

  systemd.network = {
    enable = true;
    networks."10-uplink" = {
      matchConfig = {
        MACAddress = uplink.macAddress;
        Type = "ether";
      };
      address = [
        uplink.ipv4Address
        uplink.ipv6Address
      ];
      routes = [
        {
          Gateway = uplink.ipv4Gateway;
          GatewayOnLink = true;
        }
        {
          Gateway = uplink.ipv6Gateway;
          GatewayOnLink = true;
        }
      ];
      networkConfig = {
        DNS = uplink.dns;
        DHCP = "no";
        IPv6AcceptRA = false;
      };
      linkConfig.RequiredForOnline = "routable";
    };
  };

  # Temporary debug fallback so the host stays reachable even if Tailscale fails
  # during first boot. Remove once Tailscale bootstrapping is verified.
  networking.firewall.allowedTCPPorts = [22];
  services.openssh = {
    openFirewall = lib.mkForce true;
    settings = {
      PermitRootLogin = lib.mkForce "prohibit-password";
    };
  };

  users.users.root.openssh.authorizedKeys.keys = [
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCwnZIfnmThqqtIE9p0qOYtaPgdXEytr+BAyV2fAgdraOVqCYOVop8XSMwTBXL4bN0vgAkJe0smVzxhQ09DFR785korJBBDg/iYvnRyBJzfH7lzZzC2mVNs4eSMXSp93fVBm/7sCFAIyWlBoQpKwXuO18ocavu3jHJu9pzXzy6roGle3cghpEoeWzW7Egj56A6cwoL1kq6UhfEyR1fGXE7KfGbgWje5o3yjfAZkqqY7yuH7MM817zRm1vUPdFzdkP6T+1pQFcVln7uSVCgAJ7Bn/sxuowCC0GpgIxCXSkk7A0lpnoz6lUqf8AT5XA0iMmC0gITa8GLj3mFZnHzL52oYo+JXB3En/zYEUw4iRvZSLirtUBXIeuDIQTW5FKyhhsA1M8Mqa0pRuaSCep9NHc8osqjtHZ8tzhcTDGyWM4PSARoc3qKOX+zPPEsONNvIMSqjhRiuFYstsBGEuY+/ujtTtoVmRpcqVlV+BSiT2reaQjbu+pc5mjTVLFrw3ng3MnRT7sCAVNYPt4QnNdo2ftumOqr2fvxLT2Xv846Sf3gJLjviAPAHFPtcf30Ep2U72OO2y+WJRtOCNE8412em1AwVQGSiVS57g15eTuiwIrCTR1V63s9Ybpwbom5HqX9/rAFxY4f685gRVby0ctPqwMUWEUbw9+s7Qg2unNCIcSQeKQ== #hostinger-managed-key"
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINDXG/YhRAUs4Rz7oM/5fJSNy2n+CeaZcFhBYoydOKT1 evilweasel"
  ];

  sops = lib.mkIf hasSecrets {
    defaultSopsFile = secretFile;
    validateSopsFiles = false;
    secrets = {
      tailscale-auth-key = {
        key = "tailscale/auth_key";
        owner = "root";
        mode = "0400";
        restartUnits = [
          "tailscaled-autoconnect.service"
          "tailscaled-set.service"
        ];
      };
      openclaw-gateway-token = {
        key = "openclaw/gateway_token";
        owner = "openclaw";
        group = "openclaw";
        mode = "0400";
      };
    };
  };

  services.tailscale = lib.mkIf hasSecrets {
    authKeyFile = config.sops.secrets.tailscale-auth-key.path;
  };

  weasel.roles.openclaw.gatewayTokenFile = lib.mkIf hasSecrets config.sops.secrets.openclaw-gateway-token.path;
}
