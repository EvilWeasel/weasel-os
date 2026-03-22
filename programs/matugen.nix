{config, lib, ...}: let
  repoPath = "${config.home.homeDirectory}/weasel-os";
  matugenRoot = "${repoPath}/programs/matugen";
  configText =
    builtins.replaceStrings ["@REPO_ROOT@" "@HOME@"]
    [repoPath config.home.homeDirectory]
    (builtins.readFile ./matugen/config.toml);
in {
  xdg.configFile = {
    "matugen/config.toml" = {
      text = configText;
      force = true;
    };
    "matugen/templates" = {
      source = config.lib.file.mkOutOfStoreSymlink "${matugenRoot}/templates";
      recursive = true;
      force = true;
    };
  };

  home.file = {
    ".config/waybar/style.css" = {
      source = config.lib.file.mkOutOfStoreSymlink "${matugenRoot}/generated/waybar.css";
      force = true;
    };
    ".local/share/rofi/themes/rofi.rasi" = {
      source = config.lib.file.mkOutOfStoreSymlink "${matugenRoot}/generated/rofi.rasi";
      force = true;
    };
    ".config/swaync/style.css" = {
      source = config.lib.file.mkOutOfStoreSymlink "${matugenRoot}/generated/swaync.css";
      force = true;
    };
    ".config/wlogout/style.css" = {
      source = config.lib.file.mkOutOfStoreSymlink "${matugenRoot}/generated/wlogout.css";
      force = true;
    };
    ".config/kitty/dank-theme.conf" = {
      source = config.lib.file.mkOutOfStoreSymlink "${matugenRoot}/generated/kitty-theme.conf";
      force = true;
    };
    ".config/kitty/dank-tabs.conf" = {
      source = config.lib.file.mkOutOfStoreSymlink "${matugenRoot}/generated/kitty-tabs.conf";
      force = true;
    };
    ".config/gtk-3.0/dank-colors.css" = {
      source = config.lib.file.mkOutOfStoreSymlink "${matugenRoot}/generated/gtk3-colors.css";
      force = true;
    };
    ".config/gtk-4.0/dank-colors.css" = {
      source = config.lib.file.mkOutOfStoreSymlink "${matugenRoot}/generated/gtk4-colors.css";
      force = true;
    };
    ".config/DankMaterialShell/firefox.css" = {
      source = config.lib.file.mkOutOfStoreSymlink "${matugenRoot}/generated/firefox.css";
      force = true;
    };
  };

  home.activation.ensureMatugenDirectories = lib.hm.dag.entryAfter ["writeBoundary"] ''
    mkdir -p \
      "$HOME/.config/matugen/templates" \
      "$HOME/.config/waybar" \
      "$HOME/.config/rofi" \
      "$HOME/.local/share/rofi/themes" \
      "$HOME/.config/swaync" \
      "$HOME/.config/wlogout" \
      "$HOME/.config/kitty" \
      "$HOME/.config/gtk-3.0" \
      "$HOME/.config/gtk-4.0" \
      "$HOME/.config/qt5ct/colors" \
      "$HOME/.config/qt6ct/colors" \
      "$HOME/.config/DankMaterialShell"
  '';

  home.activation.ensureMutableQtConfigs = lib.hm.dag.entryAfter ["writeBoundary"] ''
    install -d "$HOME/.config/qt5ct" "$HOME/.config/qt6ct"

    for target in \
      "$HOME/.config/qt5ct/qt5ct.conf" \
      "$HOME/.config/qt6ct/qt6ct.conf"
    do
      case "$target" in
        */qt5ct.conf) src="${repoPath}/programs/qt5ct.conf" ;;
        */qt6ct.conf) src="${repoPath}/programs/qt6ct.conf" ;;
      esac

      if [ ! -e "$target" ] || [ -L "$target" ]; then
        tmp="$target.hm-bootstrap"
        rm -f "$tmp"
        if cp -L "$target" "$tmp" 2>/dev/null; then
          :
        else
          cp "$src" "$tmp"
        fi
        chmod 0644 "$tmp"
        mv -f "$tmp" "$target"
      fi
    done
  '';
}
