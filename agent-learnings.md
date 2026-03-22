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

### 2026-03-20 (neovim + shell stack rebuild)
- Date: 2026-03-20
- Change: Reworked the custom Neovim stack with `which-key`, Catppuccin theming, LSP wiring for TS/JS/Bun, Rust, Python, C#, Nix, Bash, YAML, TOML, Markdown, Lua, and Dockerfiles; added a repo-owned terminal stack with Bash/Zsh/Nushell, Starship, Atuin, Carapace, Yazi, and Zellij; and added a portable `devShell` plus `nix run .#dev` launcher and quick-start docs.
- Pitfall/Root cause: Home Manager shell init options are shell-specific (`bash.initExtra`, `zsh.initContent`), the shared Starship config had to avoid clashing with DMS' own palette, and the repo needed a `git restore` cleanup after `nix fmt` touched unrelated files.
- Verification: `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`, `nix flake check`, `nix develop .#dev --command bash -lc 'command -v nvim yazi zellij bash zsh nu starship atuin carapace codex claude-code cargo python3 rustc pnpm dotnet >/dev/null && printf "dev-shell-ok\n"'`, and `nix develop .#dev --command nvim --headless -u NONE -c 'lua package.preload["which-key"] = function() return { add = function() end, setup = function() end } end; package.preload["lspconfig"] = function() return setmetatable({}, { __index = function() return { setup = function() end } end }) end; package.preload["cmp_nvim_lsp"] = function() return { default_capabilities = function() return {} end } end; package.preload["catppuccin"] = function() return { setup = function() end } end; vim.cmd = { colorscheme = function() end }; dofile("programs/nvim/keymaps.lua"); dofile("programs/nvim/plugins/theme.lua"); dofile("programs/nvim/plugins/lsp.lua")' -c q`.

### 2026-03-20 (home-manager reactivation backup)
- Date: 2026-03-20
- Change: Added a centralized `home-manager.backupFileExtension = "hm-backup";` in the system base profile so existing hand-managed `~/.config/atuin`, `~/.config/yazi`, and `~/.config/zellij` files are backed up instead of aborting activation.
- Pitfall/Root cause: Home Manager refuses to clobber pre-existing config files when new declarative modules take ownership, which caused `fr` to fail during reactivation on the laptop.
- Verification: `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`, and `nix flake check`.

### 2026-03-20 (runtime deprecations cleanup)
- Date: 2026-03-20
- Change: Switched the session keymaps and Alpha dashboard button from deprecated `SessionSave`/`SessionRestore` commands to `AutoSession save`/`AutoSession restore`, migrated the Neovim LSP setup off `require("lspconfig")` to `vim.lsp.config`/`vim.lsp.enable`, and updated Nushell history config to `history.file_format = "sqlite"`.
- Pitfall/Root cause: Neovim 0.11 deprecates the old lspconfig framework API, AutoSession renamed its commands, and Nushell 0.111 rejects the old `history.format` field.
- Verification: `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`, `nix flake check`, and `nix develop .#dev --command nvim --headless -u NONE -c 'lua package.preload["which-key"] = function() return { add = function() end, setup = function() end } end; package.preload["cmp_nvim_lsp"] = function() return { default_capabilities = function() return {} end } end; package.preload["auto-session"] = function() return { setup = function() end } end; vim.cmd = { colorscheme = function() end }; dofile("programs/nvim/plugins/auto-session.lua"); dofile("programs/nvim/keymaps.lua"); dofile("programs/nvim/plugins/lsp.lua")' -c q`.

### 2026-03-20 (wifi bssid helper)
- Date: 2026-03-20
- Change: Added a reusable `wifi-bssid` shell helper package and exposed it as a shared `bssid` alias in Bash, Zsh, and Nushell.
- Pitfall/Root cause: New files in this git-backed flake must be staged before `nix eval` can see them, and the first evaluation attempt was blocked by the sandboxed Nix daemon/cache path.
- Verification: `nix-instantiate --parse scripts/wifi-bssid.nix`, `nix-instantiate --parse programs/terminal-stack.nix`, `nix-instantiate --parse profiles/home/base.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`, and `nix flake check`.

### 2026-03-20 (bubblewrap availability)
- Date: 2026-03-20
- Change: Added `bubblewrap` to the shared NixOS package set and the flake dev shell so Codex and system installs can find `bwrap` without falling back to the vendored copy.
- Pitfall/Root cause: `codex` was launched from an environment that did not have `bubblewrap` available on `PATH`, and the common desktop system profile did not include it yet.
- Verification: `nix-instantiate --parse flake.nix`, `nix-instantiate --parse profiles/system/base.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, and `nix flake check` (desktop eval still hit an unrelated Home Manager derivation parse failure).

### 2026-03-20 (shell helpers + niri overlay docs)
- Date: 2026-03-20
- Change: Restored the old shell helpers as real PATH commands, added a startup alias table after `fastfetch` for Bash/Zsh/Nushell, and expanded the native Niri hotkey overlay bindings with clearer titles and an extra `Mod+Shift+/` shortcut.
- Pitfall/Root cause: This chat is voice-transcribed through another model, so unusual spellings in user requests may need context-based interpretation; also, helper additions and Niri bind changes need to stay synchronized with the alias table and overlay titles.
- Verification: Not yet run after this batch of edits.

### 2026-03-20 (local ai app switch)
- Date: 2026-03-20
- Change: Added `lmstudio` as a shared Home Manager package for both hosts and removed the laptop-specific `services.llama-cpp` wiring from the active configuration while keeping the module in the repo.
- Pitfall/Root cause: `llama-cpp` is useful as a service module but expensive to rebuild and unnecessary for the current desktop workflow; the desktop app path is a better fit for quick local-model iteration.
- Verification: Not yet run after this batch of edits.

### 2026-03-20 (xorg deprecation cleanup)
- Date: 2026-03-20
- Change: Added `libxcb` as an explicit argument in the vendored Asahi Mesa package so the evaluation no longer needs to resolve `xorg.libxcb`.
- Pitfall/Root cause: The deprecation warning came from the vendored Mesa file using `with xorg;` and implicitly reaching `xorg.libxcb`, which Nixpkgs now warns about.
- Verification: Not yet run after this batch of edits.

### 2026-03-20 (brave removal)
- Date: 2026-03-20
- Change: Removed `brave` from the shared system package list so the active laptop and desktop configs stop pulling in the package that triggered the `xorg.libxcb` warning.
- Pitfall/Root cause: The warning was coming from an unused but still-installed browser package, not from the Asahi support tree.
- Verification: Not yet run after this batch of edits.

### 2026-03-20 (kitty long-run notifications)
- Date: 2026-03-20
- Change: Enabled Kitty shell integration explicitly and added `notify_on_cmd_finish = "invisible 5.0 notify"` in the shared Home Manager Kitty config so long-running commands in unfocused or invisible Kitty windows emit desktop notifications.
- Pitfall/Root cause: Kitty's finish notifications depend on shell integration, and the config needs to live in the shared home profile to cover both hosts consistently.
- Verification: `nix-instantiate --parse profiles/home/base.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`; the desktop eval also hit an existing `weasel-rebuild` derivation parse error (`expected string 'D'`).

### 2026-03-20 (backburner ideas log)
- Date: 2026-03-20
- Change: Added `docs/backburner-ideas.md` as a concise holding area for deferred project ideas, starting with the Kitty/background-command notification idea and its relevant references.
- Pitfall/Root cause: This is intentionally a docs-only addition, so no Nix evaluation was needed for the new note file itself.
- Verification: `git diff --check`

### 2026-03-20 (michapc hosts + session debug tooling)
- Date: 2026-03-20
- Change: Added `michapc` and `michapc-debug` hosts, a conservative Micha-specific Nvidia module, configurable Niri DMS startup, shared session debug collection scripts, and repo-tracked Micha VT debug instructions.
- Pitfall/Root cause: `nixy-desktop` initially kept failing on `fu.drv` because the referenced store derivation was corrupted to a 1-byte file; changing `scripts/weasel-rebuild.nix` to emit a new derivation hash cleared the stale store path and restored evaluation.
- Verification: `nix-instantiate --parse lib/hosts.nix`, `nix-instantiate --parse profiles/home/base.nix`, `nix-instantiate --parse programs/niri.nix`, `nix-instantiate --parse modules/michapc-nvidia.nix`, `nix-instantiate --parse hosts/michapc/config.nix`, `nix-instantiate --parse hosts/michapc/home.nix`, `nix-instantiate --parse hosts/michapc/hardware.nix`, `nix-instantiate --parse hosts/michapc/users.nix`, `nix-instantiate --parse hosts/michapc/variables.nix`, `nix-instantiate --parse hosts/michapc-debug/config.nix`, `nix-instantiate --parse hosts/michapc-debug/home.nix`, `nix-instantiate --parse hosts/michapc-debug/variables.nix`, `nix-instantiate --parse scripts/weasel-dms-session.nix`, `nix-instantiate --parse scripts/weasel-collect-session-debug.nix`, `nix-instantiate --parse scripts/weasel-rebuild.nix`, `git diff --check`, `nix eval --no-write-lock-file .#nixosConfigurations.michapc.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.michapc-debug.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`, `nix build .#nixosConfigurations.michapc.config.system.build.toplevel --no-link`, and `nix build .#nixosConfigurations.michapc-debug.config.system.build.toplevel --no-link`

### 2026-03-20 (documented Micha DMS follow-up plan)
- Date: 2026-03-20
- Change: Added a detailed follow-up plan to `docs/backburner-ideas.md` describing when to escalate from `michapc-debug` to targeted DMS/Quickshell diagnostics, which files to touch, and which evidence to capture.
- Pitfall/Root cause: The next debugging step only makes sense if `michapc-debug` works and `michapc` fails; documenting that trigger avoids another generic compatibility pass in a future chat.
- Verification: `git diff --check`

### 2026-03-20 (niri hotkey overlay bind regression)
- Date: 2026-03-20
- Change: Removed the experimental `Mod+Shift+/` hotkey overlay bind from `programs/niri/base/binds.kdl` after it broke the shared Niri config on both `nixy-laptop` and Micha-related hosts.
- Pitfall/Root cause: Niri's current key syntax did not accept the literal `/` token in that bind, so `base/binds.kdl` failed to parse and the whole config loaded in broken mode with missing hotkeys and no DMS startup.
- Verification: `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix build .#nixosConfigurations.nixy-laptop.config.system.build.toplevel --no-link`, `nix build .#nixosConfigurations.nixy-laptop.config.home-manager.users.evilweasel.home.activationPackage --no-link`, `niri validate -c /tmp/niri-validate/config.kdl`, and `journalctl --user -b --no-pager | rg -i "niri|error loading config|error parsing KDL"`

### 2026-03-21 (DMS/Quickshell hang from qt5ct platform theme)
- Date: 2026-03-21
- Change: Forced `QT_QPA_PLATFORMTHEME` to an empty string in the shared Home Manager session environment and defensively unset it in `scripts/weasel-dms-session.nix` before launching DMS.
- Pitfall/Root cause: Home Manager's Qt setup exported `QT_QPA_PLATFORMTHEME=qt5ct`; Quickshell then spun forever before loading `shell.qml`, repeatedly `statx`-ing `~/.config/qt6ct/qt6ct.conf`, which made both the local laptop session and Micha's DMS session look dead while Niri itself still worked.
- Verification: `strace -f -tt -s 160 -o /tmp/quickshell.strace quickshell -v -p $(dirname $(dirname $(readlink -f $(which dms))))/share/quickshell/dms/shell.qml`, `env -u QT_QPA_PLATFORMTHEME quickshell -v -p $(dirname $(dirname $(readlink -f $(which dms))))/share/quickshell/dms/shell.qml`, `nix-instantiate --parse profiles/home/base.nix`, `nix-instantiate --parse scripts/weasel-dms-session.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.michapc.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.michapc-debug.config.system.build.toplevel.drvPath`, `nix build --no-link .#nixosConfigurations.nixy-laptop.config.home-manager.users.evilweasel.home.activationPackage`, `systemctl --user set-environment QT_QPA_PLATFORMTHEME=`, and `env QT_QPA_PLATFORMTHEME= dms run -d`

### 2026-03-21 (shared laptop DisplayLink module)
- Date: 2026-03-21
- Change: Added a reusable `modules/displaylink.nix` module, imported it from the shared system base, and enabled it in `profiles/system/laptop.nix` so `nixy-laptop`, `michapc`, and `michapc-debug` all get the same DisplayLink and `evdi` wiring.
- Pitfall/Root cause: New module files must be added to Git before flake evaluation sees them consistently, and the DisplayLink driver list should be merged with existing host GPU drivers instead of replacing them outright.
- Verification: `nix-instantiate --parse modules/displaylink.nix`, `nix-instantiate --parse profiles/system/base.nix`, `nix-instantiate --parse profiles/system/laptop.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.michapc.config.system.build.toplevel.drvPath`, and `nix eval --no-write-lock-file .#nixosConfigurations.michapc-debug.config.system.build.toplevel.drvPath`

### 2026-03-21 (DisplayLink EULA build fix)
- Date: 2026-03-21
- Change: Split the shared `modules/displaylink.nix` module into an always-on `evdi` kernel path plus an opt-in `features.displaylink.proprietaryUserspace.enable` path for the Synaptics DisplayLink userspace pieces.
- Pitfall/Root cause: Enabling `pkgs.displaylink`, `services.xserver.videoDrivers = [ "displaylink" ]`, and `dlm` unconditionally pulls `displaylink-620.zip`, which aborts the build until the proprietary Synaptics archive has been prefetched locally to satisfy the EULA.
- Verification: `nix-instantiate --parse modules/displaylink.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix build --dry-run --no-link .#nixosConfigurations.nixy-laptop.config.system.build.toplevel`, `nix eval --no-write-lock-file .#nixosConfigurations.michapc.config.system.build.toplevel.drvPath`, and `nix eval --no-write-lock-file .#nixosConfigurations.michapc-debug.config.system.build.toplevel.drvPath`

### 2026-03-21 (automatic DisplayLink source override)
- Date: 2026-03-21
- Change: Reworked `modules/displaylink.nix` to use the official NixOS DisplayLink module path (`services.xserver.videoDrivers = [ "displaylink" ]`) for all laptop hosts, but overrode `pkgs.displaylink.src` with a fixed-output `fetchurl` to the Synaptics 6.2 archive so the proprietary driver builds without a manual `requireFile` prefetch step.
- Pitfall/Root cause: The earlier half-measure only enabled `evdi`, which did not activate the full DisplayLink userspace stack; the real fix is to keep the upstream module behavior and replace only the source acquisition step that was failing on the EULA gate.
- Verification: `nix-prefetch-url --name displaylink-620.zip https://www.synaptics.com/sites/default/files/exe_files/2025-09/DisplayLink%20USB%20Graphics%20Software%20for%20Ubuntu6.2-EXE.zip`, `nix-instantiate --parse modules/displaylink.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix build --dry-run --no-link .#nixosConfigurations.nixy-laptop.config.system.build.toplevel`, `nix build --no-link -L .#nixosConfigurations.nixy-laptop.config.system.build.toplevel`, `nix eval --no-write-lock-file .#nixosConfigurations.michapc.config.system.build.toplevel.drvPath`, and `nix eval --no-write-lock-file .#nixosConfigurations.michapc-debug.config.system.build.toplevel.drvPath`

### 2026-03-21 (audio-aware session debug bundle)
- Date: 2026-03-21
- Change: Extended `weasel-collect-session-debug` to capture PipeWire/WirePlumber service state, audio journals, `wpctl`, `pactl`, ALSA device listings, and `/dev/snd` nodes in addition to the existing session logs.
- Pitfall/Root cause: The original debug bundle was strong for greetd/Niri/DMS issues but too generic for intermittent audio failures; without targeted PipeWire/WirePlumber snapshots, it was hard to distinguish a dead audio daemon from a wrong default sink or missing ALSA devices.
- Verification: `nix-instantiate --parse scripts/weasel-collect-session-debug.nix`, `nix build --no-link .#nixosConfigurations.michapc.config.home-manager.users.micha.home.activationPackage`, and `nix build --no-link .#nixosConfigurations.nixy-laptop.config.home-manager.users.evilweasel.home.activationPackage`

### 2026-03-21 (general incident bundle expansion)
- Date: 2026-03-21
- Change: Expanded `weasel-collect-session-debug` into a broader incident collector with system and user journals, failed-unit snapshots, DRM and USB topology, DisplayLink and `evdi` state, `niri`/`xrandr` output info, network basics, and extra user-state directories for Niri, DMS, PipeWire, WirePlumber, and Pulse.
- Pitfall/Root cause: A support bundle aimed only at one known failure mode stops being useful as soon as a second subsystem starts failing; for distro-style issue reports, the collector has to capture enough cross-cutting state to separate compositor, kernel, device, service, and application-level regressions.

### 2026-03-22 (current plan capture)
- Date: 2026-03-22
- Change: Created `current-plan.md` as the working plan for the Michael laptop issues, including global defaults for bindings/DisplayLink/audio, a structured debug-collection cleanup, and Hyprland cleanup notes.
- Pitfall/Root cause: The plan needed to reflect the user's addenda before implementation started, otherwise the work would drift toward a Michael-only fix instead of the requested shared-default approach.
- Verification: `sed -n '1,240p' current-plan.md`
- Verification: `nix-instantiate --parse scripts/weasel-collect-session-debug.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.michapc.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.michapc-debug.config.system.build.toplevel.drvPath`, `nix build --no-link .#nixosConfigurations.michapc.config.home-manager.users.micha.home.activationPackage`, and `nix build --no-link .#nixosConfigurations.nixy-laptop.config.home-manager.users.evilweasel.home.activationPackage`

### 2026-03-22 (German language convention)
- Date: 2026-03-22
- Change: Added an explicit repository rule in `AGENTS.md` that German communication must use real umlauts and `ß` instead of transliterations like `ue`, `oe`, `ae`, or `ss`, except where ASCII-only interfaces require a fallback.
- Pitfall/Root cause: Without an explicit rule, German writeups can silently drift into ASCII transliterations, which makes the repo's communication style inconsistent.
- Verification: `sed -n '1,220p' AGENTS.md`

### 2026-03-22 (German transliteration cleanup)
- Date: 2026-03-22
- Change: Rewrote the German text in `current-plan.md` to use proper umlauts and `ß` instead of ASCII transliterations.
- Pitfall/Root cause: The plan file had the usual `ue`/`oe`/`ae` style substitutions throughout, which is easy to miss if only the code files are checked.
- Verification: `rg -n '\\b(fuer|ueber|noetig|laeuft|Geraete|zusaetzlich|pruefen|oeffnet|Loesungen|grosse|aufraeumen)\\b' current-plan.md README.md docs/*.md AGENTS.md agent-learnings.md`

### 2026-03-22 (repo-owned MIME and DMS defaults)
- Date: 2026-03-22
- Change: Added a repo-owned `mimeapps.list`, moved the stable Niri/DMS default fragments into `programs/niri/dms/`, and linked them into `~/.config` with out-of-store symlinks while leaving DMS profile state mutable.
- Pitfall/Root cause: The useful split is between stable defaults and mutable profile state; repo-owning the wrong DMS layer would fight the settings UI or runtime-generated profiles.
- Verification: `nix-instantiate --parse programs/niri.nix`, `nix-instantiate --parse profiles/home/base.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`, and `nix flake check`

### 2026-03-21 (keyboard inventory in debug bundle)
- Date: 2026-03-21
- Change: Added input-device inventory to `weasel-collect-session-debug`, including `/proc/bus/input/devices`, `/dev/input/by-*`, filtered udev input metadata, and per-keyboard sysfs/uevent dumps to identify problematic internal laptop keyboards.
- Pitfall/Root cause: To disable a broken built-in keyboard reliably, you need a stable identifier such as the kernel device path, input handler, or udev properties; generic logs alone do not tell you which exact keyboard node to target.
- Verification: `nix-instantiate --parse scripts/weasel-collect-session-debug.nix`, `nix build --no-link .#nixosConfigurations.michapc.config.home-manager.users.micha.home.activationPackage`, and `nix build --no-link .#nixosConfigurations.nixy-laptop.config.home-manager.users.evilweasel.home.activationPackage`

### 2026-03-21 (nixy-laptop Nvidia + DisplayLink merge fix)
- Date: 2026-03-21
- Change: Restored an explicit `nvidia` entry for `nixy-laptop` in `profiles/system/laptop.nix` while keeping the shared DisplayLink module active, so the laptop's effective `services.xserver.videoDrivers` list becomes `["displaylink" "nvidia"]`.
- Pitfall/Root cause: The `nixos-hardware` Yoga hybrid profile sets `services.xserver.videoDrivers = mkDefault [ "nvidia" ]`; a normal-priority shared DisplayLink entry overrode that default instead of extending it, which dropped the Nvidia driver closure from the laptop generation even though `hardware.nvidia.open = true` and PRIME offload were still configured.
- Verification: `nix eval --json --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.services.xserver.videoDrivers`, `nix eval --json --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.hardware.nvidia.open`, `nix build --dry-run --no-link .#nixosConfigurations.nixy-laptop.config.system.build.toplevel`, and `nix build --no-link -L .#nixosConfigurations.nixy-laptop.config.system.build.toplevel`

### 2026-03-22 (fastfetch logo backend switch)
- Date: 2026-03-22
- Change: Switched Fastfetch from `kitty-direct` to `chafa` in `programs/fastfetch/default.nix` so the logo renders as terminal text instead of Kitty graphics in scrollback.
- Pitfall/Root cause: `fastfetch` is started from shell init in bash, zsh, and nushell; with a Kitty graphics logo, the image remains visible in scrollback and reappears when scrolling back through terminal history.
- Verification: `nix-instantiate --parse programs/fastfetch/default.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`

### 2026-03-22 (shell helper alias cleanup)
- Date: 2026-03-22
- Change: Updated `weasel-shell-helpers` so `v` invokes the configured `nvim` from `PATH` and `eza` wrappers pass `--color=auto` explicitly.
- Pitfall/Root cause: The `v` helper had been bypassing the Home Manager-managed Neovim wrapper by calling the package binary directly, and the `eza` wrappers were inheriting a broken color setting from elsewhere.
- Verification: `nix-instantiate --parse scripts/weasel-shell-helpers.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`

### 2026-03-22 (Stylix removal and DMS/Matugen migration)
- Date: 2026-03-22
- Change: Removed Stylix from the flake graph, switched shared desktop theming to DMS + Matugen, and added repo-owned Matugen templates plus generated target files for Waybar, Rofi, SwayNC, and Wlogout.
- Pitfall/Root cause: The DMS/Matugen config needed an explicit `[config]` table even for a dry-run, and Rofi already owns `~/.config/rofi/config.rasi` through the Home Manager module, so the final wiring had to split config ownership from the theme file itself.
- Verification: `nix-instantiate --parse flake.nix`, `nix-instantiate --parse lib/mk-host.nix`, `nix-instantiate --parse profiles/home/base.nix`, `nix-instantiate --parse profiles/home/desktop.nix`, `nix-instantiate --parse profiles/home/laptop.nix`, `nix-instantiate --parse profiles/system/base.nix`, `nix-instantiate --parse profiles/system/laptop.nix`, `nix-instantiate --parse programs/fastfetch/default.nix`, `nix-instantiate --parse programs/niri.nix`, `nix-instantiate --parse programs/rofi/rofi.nix`, `nix-instantiate --parse programs/swaync.nix`, `nix-instantiate --parse programs/waybar.nix`, `nix-instantiate --parse programs/wlogout.nix`, `nix-instantiate --parse scripts/weasel-dms-session.nix`, `nix-instantiate --parse scripts/weasel-shell-helpers.nix`, `nix-instantiate --parse programs/matugen.nix`, `matugen image "$HOME/weasel-os/pictures/wallpapers/beautifulmountainscape.jpg" --config "$HOME/weasel-os/programs/matugen/config.toml" --dry-run --type scheme-vibrant --mode dark`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`, `nix flake check`

### 2026-03-22 (theme cleanup follow-up)
- Date: 2026-03-22
- Change: Added Monaspace + Nerd Monaspace fonts, hooked Kitty into Matugen, added GTK `gtk.css` imports and a dark Adwaita GTK anchor, switched Qt off the missing Kvantum path to Adwaita-Dark, and corrected the DMS launcher icon theme default to Papirus-Dark.
- Pitfall/Root cause: Several theme outputs existed but were not actually consumed (`kitty.conf` did not include the theme files, GTK only had `dank-colors.css` without `gtk.css`, Qt was forced onto Kvantum without a theme, and DMS still defaulted launcher icons to `System Default`).
- Verification: `nix-instantiate --parse profiles/home/base.nix`, `nix-instantiate --parse profiles/system/base.nix`, `nix-instantiate --parse programs/matugen.nix`, `nix-instantiate --parse programs/matugen/config.toml`, `nix-instantiate --parse scripts/weasel-shell-helpers.nix`, `nix-instantiate --parse scripts/weasel-dms-session.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`, `nix flake check`

### 2026-03-22 (DMS theme worker recovery)
- Date: 2026-03-22
- Change: Fixed the DMS theme worker crash path by disabling the Kitty Matugen template collision, making the Qt config files mutable again via Home Manager activation, adding app-id substitutions for Firefox/Thunar/virt-manager/Handy, pinning Kitty to the Monaspice mono font, and replacing the broken BatteryOverride `StyledText` usage with plain `Text`.
- Pitfall/Root cause: The merged Matugen TOML contained a duplicate `dmskittytabs` key, `Apply Qt Colors` was writing to read-only symlink targets, the launcher had too few icon substitutions, and the BatteryOverride QML file referenced a type that was not resolving in the current DMS runtime.
- Verification: `jq empty programs/dank-material-shell/settings.json`, `nix-instantiate --parse programs/matugen.nix`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`, `nix flake check`

### 2026-03-22 (DMS icon theme live-profile trap)
- Date: 2026-03-22
- Change: Fixed the missing app/workspace/tray icons by installing `papirus-icon-theme` into the active user profile and restarting DMS after the repo config already pointed at `Papirus-Dark`.
- Pitfall/Root cause: The repo config was correct, but the active user profile still lacked `Papirus-Dark`, so DMS fell back to text letters for many icons. A local `nix profile add` repaired the live session only; the durable fix is the `home.packages` entry in `profiles/home/base.nix`.
- Verification: `readlink -f /home/evilweasel/.nix-profile/share/icons/Papirus-Dark`, `pgrep -af 'quickshell|/bin/dms'`, `dms restart`

### 2026-03-22 (Hyprland cleanup and DMS lock handoff)
- Date: 2026-03-22
- Change: Removed the remaining Hyprland/Waybar/Wlogout leftovers, switched the Niri lock bind to the DMS lock IPC call, and pruned the related Matugen outputs, helper scripts, and cached assets.
- Pitfall/Root cause: The old Hypr stack was mostly dead code but still pulled in `hypridle`, `hyprlock`, `hyprpicker`, Waybar/Wlogout assets, and a Hyprland cache entry. DMS already owns the lock and power actions, so keeping those extras only added stale dependencies and confusion.
- Verification: `nix-instantiate --parse profiles/home/base.nix`, `nix-instantiate --parse profiles/system/base.nix`, `nix-instantiate --parse programs/matugen.nix`, `nix-instantiate --parse programs/matugen/config.toml`, `nix-instantiate --parse programs/niri/base/binds.kdl`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-laptop.config.system.build.toplevel.drvPath`, `nix eval --no-write-lock-file .#nixosConfigurations.nixy-desktop.config.system.build.toplevel.drvPath`
