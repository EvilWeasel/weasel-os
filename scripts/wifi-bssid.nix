{pkgs}:

pkgs.writeShellScriptBin "wifi-bssid" ''
  # Print the BSSID of the first connected wireless interface.
  for iface in $(${pkgs.iw}/bin/iw dev | ${pkgs.gawk}/bin/awk '$1 == "Interface" { print $2 }'); do
    bssid=$(${pkgs.iw}/bin/iw dev "$iface" link | ${pkgs.gawk}/bin/awk '
      /^Connected to / { print $3; exit }
    ')

    if [ -n "$bssid" ]; then
      printf '%s\n' "$bssid"
      exit 0
    fi
  done

  printf '%s\n' "wifi-bssid: no connected wireless interface found" >&2
  exit 1
''
