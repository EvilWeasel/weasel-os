---
name: niri-computer-use
description: Control the actual Niri laptop desktop, existing browser windows and native apps through the local desktop MCP tools. Use for requested GUI work on this laptop.
---

Use the `weasel_desktop` MCP tools for the real desktop. The daemon is shared
by T3 and ordinary Codex sessions and serializes physical input. Prefer T3's
preview tools for work explicitly targeting its managed preview browser.

The owned `weasel_desktop` MCP entry preapproves this desktop transport. Tool
annotations describe effects; they do not expand the user's task authorization.
After a managed configuration change, prove the connection in a fresh ordinary
agent session. If a tool is blocked by client approval policy, preserve global
Codex settings and report/reconnect the specific integration.

Start with `desktop_status`. Every backend start initially latches input, and a
restart preserves any prior takeover cause. Inspect
`takeover_persistence.reason.source`: for `backend_startup`, a current user
request authorizing desktop work permits an explicit `desktop_resume` once the
actor is released and its input monitor is ready and quiet. Do not request a
second generic permission for that already authorized work. A physical or
explicit takeover waits for the user to return control; a backend restart does
not grant that return. Never automatically clear `physical_input_activity` or
`explicit_desktop_takeover`. Controlled evdev simulation is test evidence only.
A resume refusal requires bounded status checks or capability repair, and a
successful resume always requires a fresh observation before input.

Read `desktop_windows` to identify the exact app instance by Niri ID, PID,
app ID and contents. `desktop_observe` captures one named output and reports
actual image dimensions, fractional display geometry, focus and capabilities.
Pointer coordinates are local to that screenshot, not global compositor
coordinates. Niri may omit window bounds; never derive them from invented
geometry or Cua's window-local accessibility frames.
For small or crowded visual targets, obtain a targeted crop and use its local
coordinates. A crop changes the coordinate frame; never reuse full-output
coordinates in it. Reobserve after animation and focus changes.

`desktop_semantic` maps the Niri inventory identity to a fresh, unambiguous Cua
entry and supports bounded queries. Its tree is application/PID scoped because
Cua does not attest exact window scoping. Electron controls may sit more than ten
levels deep. Use a targeted query at depth 24 where useful; an incomplete tree
is a capability limitation, not evidence that the control is absent. Ground
visual or canvas targets from the fresh image when semantic actions are absent.

`desktop_semantic_direct` reads an exact selected AT-SPI window and returns
opaque daemon-owned handles, roles, labels, descriptions, action names and text
excerpts. Descriptions can identify icon-only GTK toolbar controls. Its versioned
scope retains the selected root and SHOWING ancestor chains; hidden branches
and their deeper descendants are omitted. Inspect the scope/pruning metadata.
Visibility contradictions or unknown states make the snapshot read-only.
Use only a complete snapshot and a showing, enabled node whose meaning matches the fresh
UI. `semantic_set_value` replaces its complete editable buffer with a complete
prior-text precondition; `semantic_click` invokes the node's exact named action.
Raw D-Bus paths, Cua indices and guessed coordinates are never direct semantic
targets. After an edit changes the semantic window context, read fresh semantics
before a dependent Save-button action. Incomplete or unsupported trees require
a deliberate visual route and fresh result verification. A failed action may
already have effects; inspect its report instead of replaying it.
On the tested Zen 1.21.8b bridge, `SetTextContents` acknowledged a no-op.
Use fresh named actions and guarded keyboard input for browser editing;
an acknowledgement does not prove focus or text. If a named `activate` action
is used to focus an entry, read fresh semantics and confirm its focused state
before dependent typing. The adapter reads individual action names and bounded
text ranges because Gecko's bulk action names and oversized ranges were faulty.
Do not repeat an uncertain setter; inspect the actual result and change route.

Focus the identified window with a separate action, then observe again.
Send `desktop_act` with the observation ID and intended window ID. Keep batches
small and limited to actions whose targets survive the preceding steps. The
response normally includes a fresh `after_observation` and image. Reuse that
evidence and observation ID when its focus and target remain appropriate;
avoid an extra full capture of the same state. If it reports
`after_observation_error`, observe again before further input, and inspect
completed effects before considering a retry. A dispatch acknowledgement is
not a successful UI result: verify the expected content, dialog, saved artifact
or independent evidence. UI rendering can lag behind dispatch; use bounded
fresh observations or semantic checks for dependent steps.
Scroll `dx`/`dy` are integer wheel steps in -100..100, positive right/down,
not pixels. Browser smooth scrolling may outlast the default settle; request
a suitable bounded settle and inspect fresh state. A focused End/PageDown
shortcut may navigate a verified scroll container faster than repeated wheels.
If an observation or capability is rejected, inspect the current state before
retrying. Preserve unrelated windows, tabs and user files.

`desktop_cancel` stops pending work. `desktop_takeover` gives the desktop back
to the user and persists that latch across backend restarts. Check
`desktop_status` until `active` is null, `actor_release_confirmed` is true and
`queued_batches` is zero; an initial cancellation acknowledgement alone does
not confirm release. Already completed effects remain. Do not retry interrupted editing or file
operations without checking what already happened. Never restart T3 or the
compositor to recover this backend.

Physical input latches takeover when its evdev monitor is available. After a
takeover, stop and wait for the user to request continuation. Only then call
`desktop_resume` and obtain a new observation. The emergency key is
**Ctrl+Alt+Escape**. Normal T3/Codex tool cancellation is forwarded to the actor;
verify that it has released input. German shortcuts use a persistent canonical
Wayland keyboard for app shortcuts. For a Niri shortcut, send
`{"kind":"key","keys":[...],"key_scope":"compositor"}`. App shortcuts use
`key_scope:"app"` by default; Super/meta/logo always use the compositor route.
Inspect `global_keyboard.routing_revision = 2` in fresh status before relying
on global shortcuts. The owned uinput device is prepared before any batch input;
the proxy refuses an old backend or changed binding. Verify the visible result
and reobserve after a workspace or fullscreen change. Never repeat a failed
global chord as an app chord: that can type into the wrong field. Failure or
cancel must confirm key release before continuing.
`type` defaults to automatic text routing: tested Electron app
IDs and long text use clipboard insertion, other apps use wtype. Do not force
keyboard text into Electron: arbitrary physical keycodes and supplementary
Unicode keysyms have proven unreliable there. `text_method: "clipboard"` is
available for additional verified apps. Clipboard preservation takes a bounded
RAM-only snapshot from one offer, including supported rich formats and original
Chromium provenance. It never attaches that provenance to temporary agent text.
Unknown/sensitive/portal formats refuse before replacement. `SAVE_TARGETS` is
an omitted transport marker. `GTK_TEXT_BUFFER_CONTENTS` is likewise omitted
without reading its process-local pointer; serialized GTK rich text is preserved
as bounded opaque bytes. Restoration is best effort without atomic ownership
guarantees and is skipped after cancel/takeover/another copy. The restored source
has its own user scope and survives actor restart until the next copy/session end.
Keep explicit clipboard replacement intentional; inspect partial effects on failure.
Use `restore_clipboard:false` only on `kind:paste` for an explicitly intended
replacement. `kind:type` always preserves the existing selection. Unknown or
misplaced action fields reject the whole batch before input; do not reuse a
field from another action kind.
For actual cross-app Copy/Paste, do not inject the source text with `type` or
`paste(text)`. Prepare destination tabs before copying, then use real Ctrl+C/V.
Meld's implicit final LF is absent from its selected buffer; for an exact-file
workflow, verify the pasted saved bytes and add one GUI Return only if that
is the sole required difference. Preserve and report the original discrepancy.
CapsLock/NumLock state is not supported. VS Code's isolated accepted profile
uses `keyboard.dispatch: "keyCode"`; verify unfamiliar profiles rather than
assuming their cached layout matches. A crop's action coordinates are local
to the displayed crop; the actor adds the crop origin itself.

The driver contains no model credentials. Optional OpenAI Decisions routing is
separate from desktop execution and ordinary Codex authentication.

A new GUI process started in a yielded `exec_command` may be cleaned up when
that Codex run ends. To retain a task-owned app across client exits, use a
separate transient user service (`systemd-run --user --collect`, a unique owned
unit and `--property=ExitType=cgroup`) with absolute executable and explicit
private profile/files. Verify actual PID/profile/window binding: single-instance
apps may forward to an existing process. Do not stop shared apps or unrelated
units. Prove continued GUI use from the next ordinary client session.
