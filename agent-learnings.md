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
