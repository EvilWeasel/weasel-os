{ pkgs }:

pkgs.writeShellScriptBin "web-search" ''
    declare -A URLS

    URLS=(
      ["🌎 Search"]="https://duckduckgo.com/?ia=web&q="
      ["❄️  Unstable Packages"]="https://search.nixos.org/packages?channel=unstable&from=0&size=50&sort=relevance&type=packages&query="
      ["❄️  Options"]="https://search.nixos.org/options?channel=unstable&query="
      ["❄️  HomeManager Options"]="https://home-manager-options.extranix.com/?release=master&query="
      ["🎞️ YouTube"]="https://www.youtube.com/results?search_query="
      ["🦥 Arch Wiki"]="https://wiki.archlinux.org/title/"
    )

    # List for rofi
    gen_list() {
      for i in "''${!URLS[@]}"
      do
        echo "$i"
      done
    }

    main() {
      # Pass the list to rofi
      platform=$( (gen_list) | ${pkgs.wofi}/bin/wofi -dmenu )

      if [[ -n "$platform" ]]; then
        query=$( (echo ) | ${pkgs.wofi}/bin/wofi -dmenu )

        if [[ -n "$query" ]]; then
  	url=''${URLS[$platform]}$query
  	xdg-open "$url"
        else
  	exit
        fi
      else
        exit
      fi
    }

    main

    exit 0
''
