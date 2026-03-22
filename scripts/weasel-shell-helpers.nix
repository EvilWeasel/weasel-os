{config, host, pkgs, pkgsUnstable, ...}:
let
  repoDefaultPath = "${config.home.homeDirectory}/weasel-os";
  mkScript = {name, body}:
    pkgs.writeShellScriptBin name ''
      set -euo pipefail
      ${body}
    '';
in
pkgs.symlinkJoin {
  name = "weasel-shell-helpers";
  paths = [
    (import ./weasel-rebuild.nix {
      inherit config host pkgs;
    })
    (import ./wifi-bssid.nix {inherit pkgs;})
    (mkScript {
      name = "sv";
      body = "exec ${pkgs.sudo}/bin/sudo ${pkgs.neovim}/bin/nvim \"$@\"";
    })
    (mkScript {
      name = "v";
      body = "exec nvim \"$@\"";
    })
    (mkScript {
      name = "cat";
      body = "exec ${pkgs.bat}/bin/bat \"$@\"";
    })
    (mkScript {
      name = "ls";
      body = "exec ${pkgs.eza}/bin/eza --icons --color=auto \"$@\"";
    })
    (mkScript {
      name = "ll";
      body = "exec ${pkgs.eza}/bin/eza -lh --icons --grid --group-directories-first --color=auto \"$@\"";
    })
    (mkScript {
      name = "la";
      body = "exec ${pkgs.eza}/bin/eza -lah --icons --grid --group-directories-first --color=auto \"$@\"";
    })
    (mkScript {
      name = "ncg";
      body = ''
        ${pkgs.nix}/bin/nix-collect-garbage --delete-old
        ${pkgs.sudo}/bin/sudo ${pkgs.nix}/bin/nix-collect-garbage -d
        ${pkgs.sudo}/bin/sudo /run/current-system/bin/switch-to-configuration boot
      '';
    })
    (mkScript {
      name = "zj";
      body = "exec ${pkgsUnstable.zellij}/bin/zellij \"$@\"";
    })
    (mkScript {
      name = "bssid";
      body = "exec wifi-bssid \"$@\"";
    })
    (pkgs.writeShellScriptBin "weasel-shell-aliases" ''
      set -euo pipefail
      cat <<'EOF' | ${pkgs.util-linux}/bin/column -t -s $'\t'
      Alias	Command	Description
      ..	cd ..	Go up one directory
      fr	nh os switch --hostname ${host}	Rebuild the current host
      fu	nh os switch --hostname ${host} --update	Update inputs and rebuild the current host
      weasel-collect-session-debug	weasel-collect-session-debug	Capture a timestamped session debug bundle in \$HOME/weasel-debug
      sv	sudo nvim	Edit files as root with Neovim
      v	nvim	Open Neovim
      cat	bat	Pretty-print file contents
      ls	eza --icons --color=auto	List files with icons
      ll	eza -lh --icons --grid --group-directories-first --color=auto	Compact long listing
      la	eza -lah --icons --grid --group-directories-first --color=auto	Long listing including hidden files
      ncg	nix-collect-garbage	Clean old generations and refresh the boot profile
      zj	zellij	Open the Zellij terminal multiplexer
      bssid	wifi-bssid	Print the BSSID of the connected Wi-Fi AP
      EOF
    '')
  ];
}
