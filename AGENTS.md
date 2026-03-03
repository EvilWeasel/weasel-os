# Repository Guidelines

## Project Structure & Module Organization
This repo is a Nix flake for two NixOS hosts: `nixy-desktop` and `nixy-laptop`.
- `hosts/<host>/`: host entrypoints (`config.nix`, `home.nix`, `hardware.nix`, `users.nix`, `variables.nix`).
- `modules/`: reusable NixOS modules (drivers, certs, hardware support, Apple Silicon overlays).
- `programs/`: Home Manager program configs (Hyprland, Waybar, Neovim, VS Code, etc.).
- `packages/`: custom derivations/flake packages.
- `scripts/`: packaged helper scripts written as Nix derivations.
- `pictures/`, `certs/`: assets and bundled cert material.

## Build, Test, and Development Commands
Run commands from repo root.
- `nix fmt`: format all Nix files (uses `alejandra`, also run by `.githooks/pre-commit`).
- `nix flake check`: evaluate flake outputs and basic checks.
- `nix build .#certs`: build the custom package exposed by this flake.
- `nix build .#nixosConfigurations.nixy-desktop.config.system.build.toplevel`: validate desktop system build.
- `sudo nixos-rebuild switch --flake .#nixy-desktop` (or `.#nixy-laptop`): apply a host config.

## Local Alias Workflow
Preferred day-to-day rebuild commands are defined in `hosts/nixy-laptop/home.nix` and `hosts/nixy-desktop/home.nix`:
- `fr`: `nh os switch --hostname ${host} /home/${username}/weasel-os` (rebuild current flake state).
- `fu`: `nh os switch --hostname ${host} --update /home/${username}/weasel-os` (update inputs + rebuild).
- `ncg`: run system/user garbage collection, then switch boot configuration.
Use these aliases when available; use the full `nixos-rebuild`/`nh` commands in non-interactive or fresh environments.

## Coding Style & Naming Conventions
- Nix code is formatted with `alejandra`; do not hand-format around it.
- Use 2-space indentation and trailing-semicolon style that `alejandra` produces.
- Prefer lowercase kebab-case file names (examples: `nvidia-drivers.nix`, `local-hardware-clock.nix`).
- Keep host-specific logic in `hosts/<host>/`; move reusable logic to `modules/` or `programs/`.

## Testing Guidelines
There is no separate unit-test framework in this repo.
- Treat `nix flake check` + target `nix build` as the required validation baseline.
- For host changes, build the affected host output before opening a PR.
- For Home Manager/program edits, verify evaluation through the relevant host build.

## Agent Verification Policy
- Prefer syntax-only verification when possible: `nix-instantiate --parse <changed-file>`.
- If a change cannot be fully validated by syntax parse (for example flake wiring, module option names, cross-file integration), run: `nix eval --no-write-lock-file .#nixosConfigurations.<affected-host>.config.system.build.toplevel.drvPath`.
- Do not use verification commands that modify `flake.lock` unless the task explicitly requires lock updates.

## Commit & Pull Request Guidelines
Git history uses short, imperative, scope-first messages (for example: `added llama-cpp.nix module`).
- Keep commits focused to one area (host/module/program).
- PRs should include: what changed, why, affected host(s), and exact validation commands run.
- Include screenshots only for visible UI changes (Waybar, Rofi, wallpapers, wlogout, etc.).

## Agent Learnings
- Maintain `agent-learnings.md` as an append-only log for future agents.
- After every task that changes files, append a short entry with date, what changed, pitfalls/root cause, and verification command(s) used.
- Keep entries concise and factual.
