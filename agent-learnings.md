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

### 2026-03-14
- Date: 2026-03-14
- Change: Added a repo convention for temporary Nixpkgs/workaround overrides: keep them in a dedicated override path (for example `modules/overrides/`) instead of burying them in host config, and put the upstream issue/PR removal note directly in the module file.
- Pitfall/Root cause: Temporary fixes placed inline in host modules are easy to forget and harder to remove once upstream resolves the regression.
- Verification: `nix-instantiate --parse modules/overrides/linux-zen-preempt-fix.nix`, `nix-instantiate --parse hosts/nixy-laptop/config.nix`, `nix-instantiate --parse hosts/nixy-desktop/config.nix`, and `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`.

### 2026-03-14 (linux-zen PREEMPT follow-up)
- Date: 2026-03-14
- Change: Updated `modules/overrides/linux-zen-preempt-fix.nix` to match the upstream nixpkgs 6.18 preemption workaround by overriding `PREEMPT = no` and allowing `PREEMPT_LAZY` / `PREEMPT_VOLUNTARY` as optional selections.
- Pitfall/Root cause: Linux 6.18 changed preemption Kconfig handling, so forcing `PREEMPT = y` now fails config validation for `linux_zen`; disabling only `PREEMPT_LAZY` was insufficient because the old hard `PREEMPT` expectation still aborted the build.
- Verification: `nix-instantiate --parse modules/overrides/linux-zen-preempt-fix.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, and `nix build --no-link .#nixosConfigurations.nixy-laptop.config.boot.kernelPackages.kernel.configfile`.

### 2026-03-17
- Date: 2026-03-17
- Change: Integrated `origin/main` into the local branch with local `nixy-*` host naming preserved, then migrated `nixy-desktop` off stale `config/*` imports and Hyprland wiring onto the current `programs/*` / `pictures/*` layout with Niri plus DMS.
- Pitfall/Root cause: The remote branch still carried an older host rename (`weaselos-*`) and Hyprland-era files, while the local laptop-first tree had already moved to Niri/DMS and different path conventions; desktop evaluation also exposed unrelated stale package and option drift (`protonup`, `greetd.tuigreet`, `noto-fonts-emoji`, insecure `stremio`, removed libvirtd OVMF options).
- Verification: `nix-instantiate --parse hosts/nixy-desktop/config.nix`, `nix-instantiate --parse hosts/nixy-desktop/home.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, and `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`.

### 2026-03-17 (modularization pass)
- Date: 2026-03-17
- Change: Introduced shared `lib/` host generation, `profiles/system/` and `profiles/home/`, moved Niri base KDL fragments into `programs/niri/`, added mutable DMS bootstrap scaffolding, replaced absolute local flake package paths with repo-relative ones, and rewrote the README around fork/bootstrap/rebuild flow.
- Pitfall/Root cause: Local flake evaluation will not reliably see newly added files until they are `git add`ed, and DMS/Niri portability breaks if the repo manages only `config.kdl` without also shipping the stable `base/*.kdl` fragments while leaving `dms/*.kdl` mutable.
- Verification: `nix-instantiate --parse flake.nix`, `nix-instantiate --parse profiles/system/base.nix`, `nix-instantiate --parse profiles/home/base.nix`, `nix-instantiate --parse programs/niri.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, and `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`.

### 2026-03-18
- Date: 2026-03-18
- Change: Fixed Home Manager activation for the declarative Niri base layer by making the repo-owned `~/.config/niri/config.kdl` and `base/*.kdl` entries `force = true`, and synchronized the committed base KDL files back to the exact live laptop versions.
- Pitfall/Root cause: Evaluation succeeded, but activation failed because Home Manager refused to clobber pre-existing mutable files in `~/.config/niri/base/`; additionally, the first repo import of some base KDL files had been truncated to partial content instead of mirroring the full live configuration.
- Verification: `systemctl status home-manager-evilweasel.service --no-pager --full`, `journalctl -u home-manager-evilweasel.service -n 200 --no-pager`, `diff -u ~/.config/niri/base/binds.kdl programs/niri/base/binds.kdl`, `nix-instantiate --parse programs/niri.nix`, and `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`.

### 2026-03-19
- Date: 2026-03-19
- Change: Switched VS Code `Code/User/settings.json` to `config.lib.file.mkOutOfStoreSymlink` so the committed repo file stays in the flake while the live file remains writable from the editor UI.
- Pitfall/Root cause: A normal Home Manager `source` link points into the Nix store and is read-only, so UI edits cannot persist; the symlink target must stay inside the writable working tree.
- Verification: `nix-instantiate --parse programs/vscode.nix` and `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`.

### 2026-03-19 (README bootstrap note)
- Date: 2026-03-19
- Change: Added the missing bootstrap note to `README.md` telling new users to enable `nix-command` and `flakes` before the first flake rebuild.
- Pitfall/Root cause: Fresh NixOS installs still need the experimental features enabled in their existing config before `nixos-rebuild --flake` works.
- Verification: README content update only.

### 2026-03-19 (michapc rollback)
- Date: 2026-03-19
- Change: Removed the temporary `michapc` host scaffolding and Nvidia module after the host-specific change was no longer wanted.
- Pitfall/Root cause: The new host files were only a temporary integration step and should not remain in the shared repo without the full machine-specific setup.
- Verification: `nix-instantiate --parse lib/hosts.nix`.

### 2026-03-19 (zed-editor)
- Date: 2026-03-19
- Change: Added `pkgsUnstable.zed-editor` to the shared Home Manager base package list so both hosts get Zed from the unstable pin.
- Pitfall/Root cause: The common home base module needed `pkgsUnstable` threaded through before it could reference the unstable package set.
- Verification: `nix-instantiate --parse profiles/home/base.nix` and `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`.
