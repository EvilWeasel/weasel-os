{lib, ...}: {
  xdg.configFile = {
    "niri/config.kdl".source = ./niri/config.kdl;
    "niri/base/animations.kdl".source = ./niri/base/animations.kdl;
    "niri/base/binds.kdl".source = ./niri/base/binds.kdl;
    "niri/base/input.kdl".source = ./niri/base/input.kdl;
    "niri/base/layout.kdl".source = ./niri/base/layout.kdl;
    "niri/base/windowrules.kdl".source = ./niri/base/windowrules.kdl;
  };

  home.activation.ensureNiriDmsBootstrap = lib.hm.dag.entryAfter ["writeBoundary"] ''
    mkdir -p "$HOME/.config/niri/dms/profiles"

    for file in colors.kdl layout.kdl alttab.kdl wpblur.kdl clipboard.kdl env.kdl binds.kdl cursor.kdl outputs.kdl windowrules.kdl; do
      if [ ! -e "$HOME/.config/niri/dms/$file" ]; then
        touch "$HOME/.config/niri/dms/$file"
      fi
    done
  '';
}
