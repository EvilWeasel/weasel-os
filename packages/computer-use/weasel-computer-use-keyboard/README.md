# Persistent canonical German virtual keyboard

Independent Rust keyboard transport for the desktop executor. Root reported that
native GTK shortcuts accepted ydotool's actual evdev keycodes while equivalent
wtype modifiers with arbitrary keycode assignments did not activate shortcuts.
This helper keeps a virtual-keyboard object and a complete German evdev keymap.
All keyboard input remains the responsibility of the one physical desktop owner.

`src/de.xkb` was generated from the installed xkeyboard-config/libxkbcommon:

```sh
xkbcli compile-keymap --layout de --format 1
```

The generated map has real evdev keycodes (`XKB code = evdev + 8`) and actual
modifier maps. The Rust implementation was independently authored against the
official wayland-protocols-misc protocol API; no niri-use code was copied.

## Library API

- `Keyboard::new()`: reads registry, creates virtual keyboard, uploads German
  keymap; sends no keys. This changes keyboard state metadata and is not a
  read-only inventory command.
- `key_evdev(code, pressed)`: explicit Linux evdev transition. Duplicate
  transitions are refused.
- `refresh_keymap()`: reuse the retained canonical keymap memfd and wait at most
  100 milliseconds for compositor receipt. Call before every shortcut after a
  different virtual keyboard such as wtype may have replaced the seat keymap.
  Refresh refuses while this device holds keys. The executor must recheck
  cancellation, target focus and actual default German layout afterward.
- `key_named(name, pressed)`: mapping for Ctrl/Shift/Alt/AltGr/Super, navigation,
  letters, digits, umlauts, F1–F12, common punctuation and basic keypad keys.
- `named_evdev(name)`: pure mapping. German `y=44`, `z=21`.
- `release_all()`: release every held key and clear this virtual keyboard's
  modifier state without producing text or pointer input.
- `sync_timeout(Duration)`: bounded compositor receipt; this does not verify an
  app's UI result. `sync()` defaults to 100 milliseconds.

Unicode text should continue to use the separately tested wtype text or clipboard
path. This library represents physical keys; an uppercase letter name does not
implicitly add Shift. Shift and AltGr combinations must be explicit. Unsupported
keys return an error. CapsLock/NumLock toggle policy and syncing user-held
modifiers are not implemented; the executor must not claim those capabilities.

The embedding executor must check cancellation again after keyboard creation
and keymap refresh, and before each key dispatch, release on every
error/cancellation, then obtain
fresh UI evidence. It must not infer app success from an acknowledgement.

## CLI for root-owned validation

`cargo build --locked` creates
`target/debug/weasel-computer-use-keyboard`.
The following commands are examples for the physical desktop owner; this author
did not execute them:

```sh
/tmp/weasel-computer-use-keyboard/target/debug/weasel-computer-use-keyboard chord ctrl a
/tmp/weasel-computer-use-keyboard/target/debug/weasel-computer-use-keyboard chord ctrl s
```

With no arguments the process remains connected and accepts JSONL requests:

```json
{"id":0,"op":"refresh_keymap"}
{"id":1,"op":"named","name":"ctrl","pressed":true}
{"id":2,"op":"named","name":"a","pressed":true}
{"id":3,"op":"named","name":"a","pressed":false}
{"id":4,"op":"named","name":"ctrl","pressed":false}
{"id":5,"op":"sync"}
{"id":6,"op":"release_all"}
```

`--keymap-info` is pure metadata and does not connect to Wayland.

## Verification by this author

- `cargo build --locked` succeeded with the existing Nix GCC wrapper on PATH.
- The generated keymap contains the canonical German symbols and Control
  modifier map.
- No keyboard creation, keymap upload or key event was executed by this author.
- Actual native UI result verification belongs to the parent session.

Official-source extraction receipt:
`/tmp/weasel-keyboard-source-extract-20261009.json` (status ok, errors/warnings
empty). Smithay's full source was fetched; Niri input source is capped at 35000
characters and cannot be treated as a complete file.
