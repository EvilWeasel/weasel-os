{
  config,
  host,
  pkgs,
  pkgsUnstable,
  ...
}:
let
  repoDefaultPath = "${config.home.homeDirectory}/weasel-os";
  mkScript =
    { name, body }:
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
    (import ./wifi-bssid.nix { inherit pkgs; })
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
      if [ -t 1 ]; then
        bold="$(${pkgs.ncurses}/bin/tput bold 2>/dev/null || true)"
        blue="$(${pkgs.ncurses}/bin/tput setaf 4 2>/dev/null || true)"
        dim="$(${pkgs.ncurses}/bin/tput dim 2>/dev/null || true)"
        reset="$(${pkgs.ncurses}/bin/tput sgr0 2>/dev/null || true)"
      else
        bold=""
        blue=""
        dim=""
        reset=""
      fi

      print_section() {
        printf '\n%s%s%s\n' "$bold$blue" "$1" "$reset"
      }

      print_table() {
        ${pkgs.util-linux}/bin/column -t -s $'\t' -o '  '
      }

      printf '%s%s%s\n' "$bold" "Weasel terminal cheatsheet" "$reset"
      printf '%sHost: ${host}%s\n' "$dim" "$reset"

      print_section "Aliases and helpers"
      cat <<'EOF' | print_table
      Name	Runs	Description
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

      print_section "Modern and diagnostic tools"
      cat <<'EOF' | print_table
      Command	Runs	Description
      btm	bottom	Full-screen process, CPU, memory, disk, and network monitor
      btop	btop	Interactive resource monitor with process controls
      procs	procs	Modern ps with tree, colors, and useful defaults
      dust	dust	Readable disk-usage tree for finding large paths
      duf	duf	Readable disk free/usage overview by filesystem
      ncdu	ncdu	Interactive terminal disk-usage browser
      doggo	doggo	Human-friendly DNS lookup client
      mtr	mtr	Live traceroute plus ping/network-loss view
      bandwhich	bandwhich	Show current bandwidth usage by process and connection
      hyperfine	hyperfine	Benchmark commands with warmups and statistics
      tokei	tokei	Count code, comments, and files by language
      delta	delta	Syntax-highlighted pager for git diffs
      sd	sd	Simple search-and-replace command
      strace	strace	Trace syscalls when debugging process behavior
      tcpdump	tcpdump	Capture and inspect network packets
      nmap	nmap	Scan hosts and ports during network debugging
      sponge	moreutils	Read stdin fully before writing output files
      ifne	moreutils	Run a command only when stdin is not empty
      vidir	moreutils	Edit directory entries in your editor
      ts	moreutils	Add timestamps to command output
      pstree	psmisc	Show processes as a parent/child tree
      fuser	psmisc	Show processes using a file, mount, or socket
      EOF
    '')
  ];
}
