# Agent Learnings

Append-only log of implementation lessons for future agents working in this repo.

## Entry Format
- `Date`: YYYY-MM-DD
- `Change`: short description of what was changed
- `Pitfall/Root cause`: what could fail or what failed
- `Verification`: exact command(s) used

## Entries

### 2026-02-24
- Date: 2026-02-24
- Change: Fixed laptop flake module wiring and added bridge netfilter sysctl values.
- Pitfall/Root cause: `nix-instantiate --parse` only validates syntax and does not catch invalid NixOS option paths like `configuration = { ... };`.
- Verification: `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath` and `nix build --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel --dry-run`.

### 2026-03-02
- Date: 2026-03-02
- Change: Added Home Manager global Playwright setup on `nixy-laptop` (`pkgs.playwright-driver`, `PLAYWRIGHT_BROWSERS_PATH`, `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD`).
- Pitfall/Root cause: Syntax parse alone does not validate Home Manager/NixOS option integration; use semantic evaluation for module changes.
- Verification: `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`.

### 2026-03-03
- Date: 2026-03-03
- Change: Stabilized `fu` updates by pinning `handy` input to a known-good revision and fixing Ventoy insecure-package allowlist handling.
- Pitfall/Root cause: `fu --update` pulled a newer `handy` revision with a broken Rust/Tauri dependency hash setup; after pinning, updates still failed because `permittedInsecurePackages` hardcoded an old Ventoy version (`1.1.07`) while nixpkgs moved to `1.1.10`.
- Verification: `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath` and `nix eval --update-input handy .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`.

### 2026-03-03 (follow-up)
- Date: 2026-03-03
- Change: Pinned Handy to its own fixed nixpkgs input (`handy-nixpkgs`) so `fu` updates of main nixpkgs channels do not repeatedly rebase/rebuild Handy.
- Pitfall/Root cause: Pinning only the Handy repo revision is not enough if `handy.inputs.nixpkgs` follows a moving channel; that still triggers frequent large rebuilds.
- Verification: `nix eval --update-input handy .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath` and `nix eval --update-input nixpkgs-unstable .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`.

### 2026-03-07
- Date: 2026-03-07
- Change: Added a local `packages/t3code` subflake for the upstream AppImage and installed it only on `nixy-laptop`.
- Pitfall/Root cause: The repo expects package additions to live under `./packages` as their own flake, and syntax-only checks are not enough to validate cross-file flake wiring into a host package list.
- Verification: `nix-instantiate --parse flake.nix`, `nix-instantiate --parse packages/t3code/flake.nix`, `nix-instantiate --parse hosts/nixy-laptop/config.nix`, and `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`.

### 2026-03-11
- Date: 2026-03-11
- Change: Moved `nixy-laptop` Niri startup to a declarative `programs/niri.nix` config that starts DMS and no longer spawns Waybar, removed leftover Hyprland/Waybar Home Manager wiring, disabled DMS user-systemd startup, and dropped the manual portal override so `programs.niri.enable` can supply the upstream Niri portal defaults.
- Pitfall/Root cause: The live `~/.config/niri/config.kdl` was still explicitly spawning `waybar`, and the host-level `xdg.portal` override forced Hyprland/wlr portal settings that conflict with Niri's recommended `xdg-desktop-portal-gnome` setup. Also, new files must be `git add`ed before `nix eval` sees them through the local Git-backed flake source.
- Verification: `nix-instantiate --parse programs/niri.nix`, `nix-instantiate --parse hosts/nixy-laptop/home.nix`, `nix-instantiate --parse hosts/nixy-laptop/config.nix`, and `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`.
