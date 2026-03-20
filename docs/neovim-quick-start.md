# Neovim Quick Start

This repo ships a custom Neovim stack, not a prebuilt distro. The goal is simple:
findable keymaps, usable LSPs, and a shell workflow that works on both the desktop
and in ephemeral dev environments.

## Start Here

Use the dev environment from the repo root:

```bash
nix develop .#dev
```

If you want the same environment through a single command, use:

```bash
nix run .#dev
```

On a remote machine, the same pattern works with a flake reference:

```bash
nix develop github:EvilWeasel/weasel-os#dev
```

## Leader Key

`<Space>` is the leader key.

`which-key` is enabled, so after pressing `<Space>` Neovim shows the available
groups and commands.

Main groups:

- `f` for file/search actions
- `l` for LSP actions
- `s` for split management
- `t` for tabs
- `w` for session/workspace actions

## Core Mappings

Files and search:

- `<leader>fe` toggle the file explorer
- `<leader>ff` find files
- `<leader>fg` live grep
- `<leader>fb` list open buffers
- `<leader>fh` search help tags
- `<leader>ft` search TODO comments

Window and tab management:

- `<leader>sv` split vertically
- `<leader>sh` split horizontally
- `<leader>se` equalize split sizes
- `<leader>sx` close the current split
- `<leader>to` open a new tab
- `<leader>tn` next tab
- `<leader>tp` previous tab
- `<leader>tx` close the current tab
- `<leader>tf` move the current buffer into a new tab

Workspace:

- `<leader>wr` restore the current session
- `<leader>ws` save the current session

Insert mode:

- `jk` exits insert mode

## LSP

Language support is Nix-managed and should work without Mason-style downloads.

Configured servers include:

- TypeScript / JavaScript via `ts_ls` or `tsserver`
- Bun via the TypeScript stack
- Rust via `rust-analyzer`
- Python via `pyright`
- C# via `csharp_ls`
- Nix via `nixd`
- Bash via `bashls`
- YAML via `yamlls`
- TOML via `taplo`
- Markdown via `marksman`
- Lua via `lua_ls`
- Dockerfiles via `dockerls`

LSP actions:

- `gd` go to definition
- `gD` go to declaration
- `gi` go to implementation
- `gr` list references
- `K` hover docs
- `<leader>la` code action
- `<leader>ld` line diagnostics
- `<leader>lf` format the current buffer
- `<leader>lr` rename symbol
- `<leader>ls` signature help
- `[d` previous diagnostic
- `]d` next diagnostic

## Shell And TUI

- Bash is the default shell.
- Zsh and Nushell are available as alternates.
- `starship` provides the prompt.
- `atuin` handles shell history.
- `carapace` provides completion for commands and options.
- `y` opens Yazi and returns you to the selected directory when you quit.
- `zj` opens Zellij.

Yazi is configured with a Catppuccin-style dark palette and a fuller plugin set
for borders, previewing, git metadata, and browsing workflows.

## Notes

- `WEASEL_OS_ROOT` points at the repo root for aliases like `fr` and `fu`.
- If you move the clone away from `~/weasel-os`, set `WEASEL_OS_ROOT` yourself.
- The shell and editor config are still repo-owned, so changes stay in the flake.
