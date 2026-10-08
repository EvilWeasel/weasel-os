{ pkgs, pkgsUnstable, ... }:
let
  protonPassCli = import ../packages/proton-pass-cli.nix { inherit pkgs pkgsUnstable; };
  # This vault contains only the user's own infrastructure credentials.
  # The native agent loads SSH-key items from this exact share, never AI/Personal.
  infrastructureShareId = "TdWv4kzYCsYZC1rphg_t3NEU2GvL2WijzEo7qS67v7WzK5M2dEA2a_HkyzwL-HZGK0vZw6ZnimZhTQAVIZvtpA==";
in
{
  # The initial setup installs this same, previously absent unit before the
  # OS bootstrap. Home Manager may replace only that task-owned unit later.
  xdg.configFile."systemd/user/weasel-proton-infra-ssh-agent.service".force = true;

  systemd.user.services.weasel-proton-infra-ssh-agent = {
    Unit = {
      Description = "Proton Pass SSH agent for own infrastructure";
      After = [ "dbus.socket" ];
      Wants = [ "dbus.socket" ];
    };
    Service = {
      Type = "simple";
      ExecStart = "${protonPassCli}/bin/pass-cli ssh-agent start --share-id ${infrastructureShareId} --socket-path %t/proton-infra-ssh-agent.sock --refresh-interval 300";
      Environment = [
        "PROTON_PASS_LINUX_KEYRING=dbus"
        "XDG_RUNTIME_DIR=%t"
        "DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus"
      ];
      UMask = "0077";
      NoNewPrivileges = true;
      Restart = "on-failure";
      RestartSec = 15;
    };
    Install.WantedBy = [ "default.target" ];
  };
}
