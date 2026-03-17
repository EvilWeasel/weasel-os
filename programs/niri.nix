{lib, ...}: {
  xdg.configFile = {
    "niri/config.kdl" = {
      source = ./niri/config.kdl;
      force = true;
    };
    "niri/base/animations.kdl" = {
      source = ./niri/base/animations.kdl;
      force = true;
    };
    "niri/base/binds.kdl" = {
      source = ./niri/base/binds.kdl;
      force = true;
    };
    "niri/base/input.kdl" = {
      source = ./niri/base/input.kdl;
      force = true;
    };
    "niri/base/layout.kdl" = {
      source = ./niri/base/layout.kdl;
      force = true;
    };
    "niri/base/windowrules.kdl" = {
      source = ./niri/base/windowrules.kdl;
      force = true;
    };
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
