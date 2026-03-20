# WeaselOS

WeaselOS is my personal NixOS flake for `nixy-laptop` and `nixy-desktop`.
The current desktop stack is Niri plus Dank Material Shell (DMS), with shared system and Home Manager profiles layered underneath the host directories.

This repo is optimized for three workflows:

1. Rebuild my own laptop and desktop without host drift.
2. Fork the repo and use it as a starting point for another machine.
3. Keep host-specific facts separate from shared policy.

## Repository Layout

- `hosts/<host>/`: host entrypoints and machine-specific facts.
- `profiles/system/`: shared NixOS policy.
- `profiles/home/`: shared Home Manager policy.
- `programs/`: program-specific Home Manager modules.
- `packages/`: local package flakes and derivations.
- `scripts/`: packaged helper scripts.
- `docs/`: migration and architecture notes.

## Current Assumptions

- Hosts are named `nixy-*`.
- The preferred clone location is `~/weasel-os`.
- `programs/niri/` owns `config.kdl` and `base/*.kdl`.
- `~/.config/niri/dms/*.kdl` stays mutable and is generated or updated by DMS.

The repo no longer hard-requires the path `/home/evilweasel/weasel-os`, but the aliases and examples assume `~/weasel-os` unless you set `WEASEL_OS_ROOT`.

## Using This Repo On A Fresh NixOS Install

1. Install NixOS normally.
2. Log in as your user.
3. If your current NixOS install does not already have flake support enabled, add this to your existing NixOS config before the first rebuild:

   ```nix
   nix.settings.experimental-features = [ "nix-command" "flakes" ];
   ```

   You need this for `nixos-rebuild --flake` and for `nh` while bootstrapping.
4. Clone your fork into your home directory:

```bash
git clone git@github.com:<your-user>/Weasel-OS.git ~/weasel-os
cd ~/weasel-os
```

5. Create a new host folder by copying one of the existing hosts:

```bash
cp -r hosts/nixy-laptop hosts/<your-host>
```

6. Generate fresh hardware config on the target machine:

```bash
sudo nixos-generate-config --show-hardware-config > hosts/<your-host>/hardware.nix
```

7. Edit these files for your machine:

- `hosts/<your-host>/users.nix`
- `hosts/<your-host>/variables.nix`
- `lib/hosts.nix`

At minimum adjust:

- the username
- host name entry in `lib/hosts.nix`
- user groups
- Git identity
- any host-specific monitor notes or custom packages you want to change

8. If you want to keep the repo somewhere other than `~/weasel-os`, export `WEASEL_OS_ROOT` before rebuilds or add it to your shell environment.

9. Switch to the flake for the first time:

```bash
sudo nixos-rebuild switch --flake ~/weasel-os#<your-host>
```

10. Log out and back in.

That first switch is the important bootstrap step. After it completes, Home Manager installs the shared Niri base config and creates empty mutable DMS files if DMS has not generated them yet.

## Migrating An Existing `/etc/nixos` Setup

1. Fork and clone this repo.
2. Copy an existing host folder:

```bash
cp -r hosts/nixy-laptop hosts/<your-host>
```

3. Replace `hosts/<your-host>/hardware.nix` with the hardware config from your machine.
4. Update `hosts/<your-host>/users.nix`, `hosts/<your-host>/variables.nix`, and `lib/hosts.nix`.
5. Run:

```bash
sudo nixos-rebuild switch --flake ~/weasel-os#<your-host>
```

You do not need to move your old `/etc/nixos` files into this repo first. Treat this flake as the new source of truth.

## Daily Commands

After the first successful switch and re-login, the shell aliases are available:

- `fr`: rebuild the current host from this repo.
- `fu`: update flake inputs and rebuild the current host.
- `ncg`: garbage-collect user and system generations, then refresh boot config.
- `nix develop .#dev`: enter the portable editor and tool shell.
- `nix run .#dev`: launch the same portable shell with one command.

Examples:

```bash
fr
fu
ncg
nix develop .#dev
nix run .#dev
```

For Neovim and the portable shell workflow, see [docs/neovim-quick-start.md](docs/neovim-quick-start.md).

If the repo is not at `~/weasel-os`, set:

```bash
export WEASEL_OS_ROOT=/absolute/path/to/your/clone
```

## Niri And DMS Notes

- `programs/niri/config.kdl` is declarative.
- `programs/niri/base/*.kdl` is declarative.
- `~/.config/niri/dms/*.kdl` is mutable and should not be edited declaratively in this repo.

That split is intentional. DMS owns monitor and runtime-generated fragments such as `outputs.kdl`, while the repo owns the stable base layer.

## Validation

Useful evaluation commands from repo root:

```bash
nix fmt
nix flake check
nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath
nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath
```

## Status

The repo is mid-migration toward the target architecture documented in:

- `docs/migration-plan.md`
- `docs/target-architecture.md`
