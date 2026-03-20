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

## Micha DMS / Quickshell Isolation Follow-Up

- Goal: if `michapc-debug` works but `michapc` does not, isolate the exact DMS or Quickshell component that breaks after login on Micha's HP Pavilion Gaming 17 (`17-cd1xxx`, high confidence) without changing the proven plain-`niri` baseline.
- Trigger condition: only do this after Micha tests both new hosts and reports:
  - `michapc-debug` boots into a usable desktop/session, and
  - `michapc` still fails after login or lands in the same "mouse only, no usable shell/hotkeys" state.
- Why this is the right next step: at that point the repo already proved that the issue is very unlikely to be the greeter, general Wayland bring-up, base `niri`, or the conservative Nvidia host module in `modules/michapc-nvidia.nix`. The remaining high-probability fault domain is the post-login shell layer: `dms`, `qs`/Quickshell, or one of the DMS-managed shell components.
- Current repo state before this follow-up:
  - `michapc` is the intended target host with normal DMS startup.
  - `michapc-debug` disables DMS startup via `weasel.session.startDms = false`.
  - Shared debug collection already exists via `weasel-collect-session-debug`.
  - DMS startup already goes through the wrapper `weasel-dms-session`, which writes persistent logs under `~/.local/state/weasel-debug/dms/`.
- Proposed implementation for the next debugging pass:
  - Add a third, temporary diagnostic mode or host variant that keeps DMS enabled but swaps the default DMS launch command for a more verbose wrapper.
  - Extend `scripts/weasel-dms-session.nix` to capture more evidence before `exec dms run --session`, including:
    - a timestamped environment dump
    - resolved executable paths for `dms`, `qs`, `quickshell`, `kitty`, and `rofi-launcher`
    - `ulimit -a`
    - relevant session vars such as `PATH`, `WAYLAND_DISPLAY`, `DISPLAY`, `XDG_RUNTIME_DIR`, `XDG_SESSION_TYPE`, `QT_QPA_PLATFORM`, `NIRI_SOCKET`, and `DBUS_SESSION_BUS_ADDRESS`
    - explicit begin/end markers and exit status logging
  - If `qs` or Quickshell can be invoked directly from the DMS stack, capture its stdout/stderr in a dedicated log file rather than only the outer DMS wrapper log.
  - Add optional `coredumpctl` capture for `dms`, `qs`, and `quickshell` into `weasel-collect-session-debug`.
  - If needed, add a repo option like `weasel.session.debugShellMode` or `weasel.session.dmsCommandExtraArgs` in `programs/niri.nix` so host-level variants can enable verbose startup without forking more config.
- Preferred narrowing strategy once the trigger condition is met:
  1. Keep `michapc-debug` unchanged as the known-good plain-`niri` baseline.
  2. Add a DMS-diagnostic variant that differs from `michapc` only by logging and optional shell-component gating.
  3. If logs show DMS starts and then dies quickly, split the shell into coarse chunks:
     - DMS with Quickshell disabled if that is supported cleanly
     - DMS with only core panels/widgets disabled
     - DMS with one suspect module at a time removed
  4. Stop as soon as one removed component makes the session usable again; that identifies the next real fix target.
- Files most likely to change in that future pass:
  - `scripts/weasel-dms-session.nix`
  - `scripts/weasel-collect-session-debug.nix`
  - `programs/niri.nix`
  - potentially the DMS or Quickshell-related files under `programs/` once the failing component is identified
  - optionally `lib/hosts.nix` and a temporary host directory if a dedicated `michapc-dms-debug` host is cleaner than another option toggle
- What not to do in that pass:
  - do not start by reworking Nvidia again unless the new logs point there directly
  - do not replace the working `michapc-debug` baseline
  - do not make broad architectural changes to `niri` or the greeter while the fault domain is already narrowed to post-login shell startup
- Operator workflow for tomorrow:
  1. Micha tests `michapc-debug`.
  2. If it works, Micha tests `michapc`.
  3. If only `michapc` fails, start a new chat and point to this entry plus `docs/micha-debug.md`.
  4. In that chat, ask specifically for the DMS/Quickshell follow-up described here, not another generic compatibility pass.
