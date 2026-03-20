# Backburner Ideas

This file is a short holding area for project ideas that are worth revisiting later but are not active implementation work right now.

Keep entries concise. The goal is enough context for a future AI agent or future-you to understand the idea without re-deriving the whole discussion.

## Kitty / Command-Input Notifications

- Goal: notify when a long-running terminal command finishes in Kitty, and optionally when a command appears to wait for input.
- Current status: the finish-notification part is already implemented with Kitty's built-in `notify_on_cmd_finish = "invisible 5.0 notify"` in `profiles/home/base.nix`.
- Deferred part: a more general "command needs input" signal is much harder than finish notifications. `sudo`-specific handling is realistic, but a universal solution would likely need command-specific wrappers or a PTY-level proxy.
- Revisit if needed: only if I want prompt detection, `sudo`/`doas`/`pkexec` integration, or broader shell-level automation beyond Kitty.
- Relevant repo context: `profiles/home/base.nix`, `programs/terminal-stack.nix`, `programs/niri/config.kdl`.
- Useful references:
  - Kitty config reference: <https://sw.kovidgoyal.net/kitty/conf/>
  - Kitty shell integration: <https://sw.kovidgoyal.net/kitty/shell-integration/>
  - Niri IPC docs: <https://github.com/YaLTeR/niri/wiki/IPC>
