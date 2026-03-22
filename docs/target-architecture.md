# WeaselOS Target Architecture

This document defines the intended repository architecture after the modularization work.
It is written as a design target, not as a description of the current state.

## Goals

- Keep `programs/`, `packages/`, and `scripts/` as first-class concepts.
- Reduce duplication between laptop and desktop system/home configuration.
- Make it realistic for another user to fork the repo, clone it, adapt a host folder, and switch to the config.
- Keep `nixy-*` host naming. Do not reintroduce `weaselos-*`.
- Treat Niri plus Dank Material Shell (DMS) as the primary desktop stack.
- Keep DMS-generated compositor fragments mutable where DMS expects to own them.

## Non-Goals

- No large feature expansion during the modularization pass.
- No forced migration to a different shell/compositor stack.
- No deep package curation beyond what is required for portability and maintainability.

## Design Principles

### 1. Hosts should describe facts, not policy

`hosts/<host>/` should only contain host-specific facts and small overrides:

- hardware imports
- host name
- user name and groups
- hardware-specific toggles
- optional host-local package additions

Common policy should live outside the host directories.

### 2. Shared policy belongs in profiles

Shared NixOS and Home Manager composition should move into profiles:

- `profiles/system/` for NixOS-level composition
- `profiles/home/` for Home Manager-level composition

Profiles are higher-level than modules. They compose modules and programs into a role.

### 3. Modules should be truly reusable

`modules/` should contain reusable building blocks, not historical leftovers.

Recommended split:

- `modules/nixos/drivers/`
- `modules/nixos/features/`
- `modules/nixos/services/`
- `modules/nixos/overrides/`
- `modules/home/services/`

Examples:

- `modules/canbus.nix` -> `modules/nixos/features/canbus.nix`
- `modules/llama-cpp.nix` -> `modules/nixos/services/llama-cpp.nix`
- `home-modules/llama-cpp.nix` -> `modules/home/services/llama-cpp.nix`
- `modules/overrides/linux-zen-preempt-fix.nix` stays an override, but under a clearer namespace

### 4. Programs stay separate

`programs/` should remain the place for app-specific Home Manager config.

That includes things like:

- Neovim
- Fastfetch
- VS Code
- Rofi
- SwayNC
- Wlogout
- Niri base config fragments

### 5. Flake outputs should be generated from host metadata

`flake.nix` should not manually duplicate host wiring for every machine.

Target:

- a small host registry
- a helper such as `lib/mk-host.nix`
- a single pattern that builds `nixosConfigurations`

This reduces drift between laptop and desktop immediately.

## Proposed Repository Layout

```text
.
|-- flake.nix
|-- flake.lock
|-- README.md
|-- docs/
|   |-- migration-plan.md
|   `-- target-architecture.md
|-- lib/
|   |-- mk-host.nix
|   |-- mk-home.nix
|   `-- hosts.nix
|-- hosts/
|   |-- nixy-desktop/
|   |   |-- default.nix
|   |   |-- hardware.nix
|   |   |-- users.nix
|   |   |-- variables.nix
|   |   `-- overrides.nix
|   `-- nixy-laptop/
|       |-- default.nix
|       |-- hardware.nix
|       |-- users.nix
|       |-- variables.nix
|       `-- overrides.nix
|-- profiles/
|   |-- system/
|   |   |-- base.nix
|   |   |-- desktop-common.nix
|   |   |-- laptop-common.nix
|   |   |-- niri-dms.nix
|   |   |-- virtualization.nix
|   |   |-- gaming.nix
|   |   `-- dev.nix
|   `-- home/
|       |-- base.nix
|       |-- shell.nix
|       |-- git.nix
|       |-- desktop-common.nix
|       |-- niri-dms.nix
|       |-- dev-tools.nix
|       `-- media.nix
|-- modules/
|   |-- nixos/
|   |   |-- drivers/
|   |   |-- features/
|   |   |-- services/
|   |   `-- overrides/
|   `-- home/
|       `-- services/
|-- programs/
|   |-- fastfetch/
|   |-- niri/
|   |   |-- config.kdl
|   |   `-- base/
|   |       |-- animations.kdl
|   |       |-- binds.kdl
|   |       |-- input.kdl
|   |       |-- layout.kdl
|   |       `-- windowrules.kdl
|   |-- nvim/
|   |-- rofi/
|   `-- vscode/
|-- packages/
`-- scripts/
```

## Flake Composition Model

The flake should define a host registry with data, not hand-written per-host wiring.

Each host entry should declare things like:

- `system`
- `username`
- `hostName`
- `hardwareModules`
- `systemProfiles`
- `homeProfiles`
- `extraSystemModules`
- `extraHomeModules`
- `useUnstable`

Then `lib/mk-host.nix` assembles:

- NixOS modules
- Home Manager modules
- specialArgs
- host-specific extras

## Niri and DMS Target Model

This is the most important design constraint for compatibility.

### Declarative content

The flake should manage:

- the top-level `~/.config/niri/config.kdl`
- repo-owned base fragments under `~/.config/niri/base/*.kdl`
- repo-owned stable DMS defaults under `~/.config/niri/dms/*.kdl`
- Nix-owned Home Manager integration for the DMS package and shell startup

### Mutable content

The flake should not declaratively own files that DMS generates and mutates at runtime.

Observed live files under `~/.config/niri/dms/` include:

- `alttab.kdl`
- `binds.kdl`
- `clipboard.kdl`
- `colors.kdl`
- `cursor.kdl`
- `env.kdl`
- `layout.kdl`
- `outputs.kdl`
- `windowrules.kdl`
- `wpblur.kdl`
- `profiles/*.kdl`

The `profiles/*.kdl` files are DMS-managed and should remain mutable.

### Required structural change

Right now the repo only manages `config.kdl`, while the live installation also depends on repo-absent `base/*.kdl` files.
That is not portable enough for a fresh user.

Target:

- move the current live `~/.config/niri/base/*.kdl` base layer into the repository
- install those files declaratively
- keep `dms/profiles/*.kdl` outside declarative ownership
- let the stable `dms/*.kdl` defaults live in the repo and link them into the home directory

### Bootstrap concern

A fresh user may not have `~/.config/niri/dms/profiles/*.kdl` yet, but the stable defaults are linked from the repo.

This needs an explicit bootstrap strategy during implementation.

Recommended implementation direction:

- keep DMS-generated profile files mutable
- link the stable DMS defaults from repo-owned files via out-of-store symlinks
- add a bootstrap mechanism that creates missing mutable DMS profile files only when absent

This can be done with a user activation step or a small bootstrap script/service.

### DMS greeter requirement

`programs.dank-material-shell.greeter.configHome` must not be hardcoded to a placeholder path.
It should be derived from the actual configured username/home path.

## Host Onboarding Model

The intended user story for another person should be:

1. Fork repo
2. Clone repo to `~/weasel-os`
3. Create a new host directory from a simple host template
4. Replace `hardware.nix` with output from `nixos-generate-config`
5. Adjust `users.nix` and `variables.nix`
6. Run `sudo nixos-rebuild switch --flake ~/weasel-os#<host>`
7. Re-login
8. Use `fr` and `fu`

That means the repo must not assume:

- the username is `evilweasel`
- the repo path is `/home/evilweasel/weasel-os`
- hidden mutable config exists outside the repo

## Documentation Target

The README should become an operator-facing document, not a short project blurb.

It should cover:

- what WeaselOS is
- current desktop stack: Niri + DMS
- repository structure
- first-time setup on a fresh NixOS system
- migration from an existing `/etc/nixos`
- how to add a new host
- first rebuild command
- when `fr` and `fu` become available
- update and rollback notes

## Cleanup Candidates

These items should be reviewed during modularization:

- unused ZanyOS leftovers in `modules/`
- Apple Silicon support and bundled firmware if no longer supported
- Hyprland-only scripts and program modules
- stale comments and strings still referring to Hyprland
- hardcoded personal paths or identities

## Definition of Done

The architecture target is reached when:

- laptop and desktop share the majority of system/home composition
- host folders are mostly facts plus minimal overrides
- the repo can be forked and cloned by another user without absolute path fixes
- Niri base config is fully in-repo
- DMS mutable files are intentionally handled, not accidentally relied upon
- README is sufficient for a fresh install bootstrap
