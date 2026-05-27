# Waylandcraft on nixy-laptop

Waylandcraft is a Fabric client mod that runs a Wayland compositor inside Minecraft. This setup keeps the Minecraft profile and mod downloads manual in Prism Launcher, but installs the system tools it needs.

## Installed by this flake

The laptop profile includes:

- `prismlauncher`
- `xwayland-satellite`
- `libxkbcommon`, which provides `xkbcli`

After rebuilding the laptop, confirm the tools are available:

```sh
command -v prismlauncher
command -v xwayland-satellite
command -v xkbcli
```

## Prism instance

Create a dedicated Prism Launcher instance:

- Minecraft: `26.1.2`
- Loader: Fabric
- Launcher package: use the normal Nix-installed Prism Launcher, not a Flatpak launcher

For NVIDIA, set this environment variable only on the Waylandcraft Prism instance:

```sh
__GL_THREADED_OPTIMIZATIONS=0
```

## Mods

Download these into the instance `mods` folder:

- Waylandcraft `1.0.1`: <https://modrinth.com/mod/waylandcraft/version/EuKmUsll>
- Fabric API `0.149.1+26.1.2`: <https://modrinth.com/mod/fabric-api/version/BLz7ETCw>

Sodium is recommended by the Waylandcraft project, but is optional.

## Runtime notes

Default Waylandcraft keybinds:

- `V`: app launcher
- `G`: keyboard capture
- `B`: window manager screen
- `Alt+Q`: hard keyboard capture, useful when the app needs Escape or relative mouse movement

For X11 apps, start Xwayland from a terminal inside Waylandcraft:

```sh
xwayland-satellite :2
```

Then launch X11 apps with the matching display, for example:

```sh
DISPLAY=:2 steam
```

If NVIDIA rendering glitches appear, try the Waylandcraft "Improved Transparency" video option. Avoid forcing Zink for this instance; the project recommends native OpenGL.

## Sources

- Waylandcraft README: <https://github.com/EVV1E/waylandcraft>
- Waylandcraft Modrinth: <https://modrinth.com/mod/waylandcraft>
- Fabric API Modrinth: <https://modrinth.com/mod/fabric-api>
