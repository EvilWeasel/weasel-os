---
name: niri-computer-use
description: Control the actual Niri laptop desktop, existing browser windows and native apps through the local desktop MCP tools. Use for requested GUI work on this laptop.
---

Use the `weasel_desktop` MCP tools for the real desktop. The daemon is shared
by T3 and ordinary Codex sessions and serializes physical input. Prefer T3's
preview tools for work explicitly targeting its managed preview browser.

For T3 desktop execution, use an app-owned Codex child with model
`gpt-6-luna` and medium reasoning by default. The planning/conversation model
may remain unchanged. Discover the live provider/model catalog first; send the
complete current task, target output, allowed files and success criteria to
one child, without assuming it inherits this conversation. Retain its task ID.
Only that worker owns desktop input until it finishes or confirms release.
The parent may read status and report progress, but must not send competing
input. Use the existing Codex authentication; do not extract OAuth tokens.
Outside T3, use a supported Luna delegation path when available; explicitly
report if the current client cannot provide the requested model separation.

For the full workflow, keep the selected output visibly marked with the
click-through blue indicator. Start `weasel-computer-use-indicator run
--task-id ID --output OUTPUT --stdin-control` in the executing worker's owned
foreground `exec_command` session with `tty=true` and `yield_time_ms=1000`;
read its actual ready event, retain the session ID and
keep it alive across model-thinking gaps. End with `v1 end\n` through that
session or the exact task helper's `end` command. End the exact
task helper on completion or abort. Its monitor/epoch binding and bounded
lease must hide it after disconnect/stop, without taking keyboard focus.
Do not launch it as an unrelated permanent daemon or mark the user's other
monitor. The indicator is lifecycle maintenance; desktop input still uses MCP.

Optional `weasel_decisions.desktop_decide` supplies fast predicate/choice
evidence using `gpt-6-luna`, separately from free action planning. Use a fresh
bounded task-relevant crop or text, explicit safe candidates and the existing
budget ledger. Its probability/choice never authorizes input or replaces fresh
verification. Do not call it when deterministic readback already answers the
question, and do not replay a paid request after an uncertain response.

The owned `weasel_desktop` MCP entry preapproves this desktop transport. Tool
annotations describe effects; they do not expand the user's task authorization.
After a managed configuration change, prove the connection in a fresh ordinary
agent session. If a tool is blocked by client approval policy, preserve global
Codex settings and report/reconnect the specific integration.

Start with `desktop_status`. Expected startup `capture_not_attempted=true` is
not capture failure and does not block an already authorized startup resume.
Use the shared `resume_input_readiness` for the backend's 300ms startup/recent
activity checks, ready physical monitor and known released controls. It is a
snapshot, not permission or actor release. A recorded `capture_failed` retains
its category until a successful fresh observation; input remains blocked until
that observation. Resume itself does not require a previous capture.
Every backend start initially latches input, and a
restart preserves any prior takeover cause. Inspect
`takeover_persistence.reason.source`: for `backend_startup`, a current user
request authorizing desktop work permits an explicit `desktop_resume` once the
actor is released and its input monitor is ready and quiet. Do not request a
second generic permission for that already authorized work. A physical or
explicit takeover waits for the user to return control; a backend restart does
not grant that return. Never automatically clear `physical_escape` or
`explicit_desktop_takeover`. Older `physical_input_activity` markers remain
preserved across upgrade and need one current user-authorized explicit resume;
ordinary input under the new policy does not create them. Controlled evdev
simulation is test evidence only.
Use the current `takeover_latched` and `takeover_persistence.marker_active`
booleans to decide whether a stop is active. Historical `last_reason` or an
older backend's retained `reason` with both booleans false is not a live stop.
Do not request another resume for an already resumed actor; ordinary recent
input only requires fresh grounding and release, not permission or resume.
A resume refusal requires bounded status checks or capability repair, and a
successful resume always requires a fresh observation before input.
For an active stop, pass `expected_epoch=status.epoch` and
`expected_session_id=status.session_id` identifying the exact stop the user has
authorized resuming. Use the current backend session, not the retained
`takeover_persistence.reason.session_id` from a prior backend. The proxy requires
`resume_binding_revision=1` before forwarding any transition; an older idle,
unlatched backend can return only a read-only no-op snapshot. A stale
binding means a new stop/cancellation or backend intervened: inspect its cause
and honor the new return-of-control requirement, never refresh and retry
blindly. Empty arguments are allowed only for the idempotent unlatched case.
Active real Escape/explicit stop causes cannot be reclassified by controlled
simulation, startup or legacy paths. An explicit takeover from a test shares
the human takeover interface and has no proven task ownership; a later test
resume must never clear a newer human stop.

Read `desktop_windows` to identify the exact app instance by Niri ID, PID,
app ID and contents. `desktop_observe` captures one named output and reports
actual image dimensions, fractional display geometry, focus and capabilities.
For an authorized app start, resolve its installed launcher from PATH and the
user profile before declaring it missing. NixOS user applications can live in
`/etc/profiles/per-user/<user>/bin` without a system-profile launcher. Verify
the resolved program and use a disposable profile when required; a missing
guessed path is not proof that the app is unavailable.
Pointer coordinates are local to that screenshot, not global compositor
coordinates. Niri may omit window bounds; never derive them from invented
geometry or Cua's window-local accessibility frames.
Use a complete direct semantic snapshot and an exact showing, enabled node
with the required typed-action capability before choosing a visual click.
A returned action name alone does not make a disabled node actionable.
For visual targeting, treat a full-output image larger than 1200 pixels in
either dimension as an overview. The actor refuses the whole batch before any
input if any move, click, scroll or drag uses a view larger than 1200 pixels in
either dimension. Before pointer input, capture a fresh region
containing the target with both crop dimensions at most 1200 pixels; also crop
small or crowded controls on smaller images. Select the region from visible
pixels in the observation, not guessed absolute window bounds. If necessary,
inspect overlapping smaller regions until the intended control is unambiguous.
Read the returned crop's actual `capture.image_width`, `image_height` and
`view`, and ground x/y in that exact crop. Do not estimate coordinates from a
chat thumbnail, monitor resolution, fractional display scale or an assumed
2048-pixel preview. If the client explicitly reports different prepared image
dimensions, convert the visual point independently on each axis using
x * capture.image_width / prepared_width and
y * capture.image_height / prepared_height; never guess those prepared sizes.
If the image is clipped, letterboxed or its mapping is unknown, obtain a smaller
fresh crop instead. Send crop-local coordinates; the actor adds its origin.
A crop changes the coordinate frame; never reuse full-output coordinates in it.
Record observation ID, target identity, view dimensions and selected point in a
compact action receipt. Verify the new focus and intended UI change after the
click. `window_id` validates the focused instance, but cannot prove an arbitrary
pixel belongs to it when Niri supplies no absolute window bounds. A different
focused window is a wrong-target failure: stop the batch, inspect possible
effects, then focus the intended instance separately and ground it afresh.
Reobserve after animation, layout, modal and focus changes.

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
Labels can remain readable during ordinary input or held controls. Treat
`available`/`limited` as tree availability and inspect `input_ready`,
`action_ready` and `fresh_semantic_snapshot_required_for_input` separately.
Non-actionable snapshots deliberately issue no handles. After release, obtain
a fresh complete semantic snapshot and current visual observation before acting;
ordinary input does not require a resume. Escape and cancellation remain stops.
Use only a complete snapshot and a showing, enabled node whose meaning matches the fresh
UI. `semantic_set_value` replaces its complete editable buffer with a complete
prior-text precondition; `semantic_click` invokes the node's exact named action.
`semantic_focus` is standalone and uses an actionable opaque handle with
`capabilities.focus`. It calls AT-SPI GrabFocus once, revalidates the exact
object/window/context, and separately checks fresh FOCUSED state. Acceptance
alone does not prove focus. Before dependent keyboard input, observe and query
semantics again to confirm the intended text object has `focused:true`.
Selection, copied content and saved bytes still require their own checks.

If the actual `desktop_semantic_direct` schema exposes
`include_text_selection`, pass `include_text_selection:true` after a guarded
selection action when whole-buffer replacement requires selection proof.
Identify the same exact text object and require `elements_complete:true`,
current matching input generation, released controls and `action_ready:true`.
Its `text_selection` must be `status:"available"`, `stable_readback:true`,
`full_text_selected:true` with one nonempty range [0,character_count).
The provider count is in Unicode codepoints, not UTF-8 bytes or UTF-16 units.
This proves sampled range coverage, not text identity or an atomic snapshot;
verify the exact current document/content separately. Missing metadata or
unsupported/error/multiple selections is no proof; use a freshly verified
visual route or report the remaining capability gap. Keep raw text and terminal
LF unchanged; do not trim or infer selection from focus/Ctrl+A acknowledgement.
Default false adds no selection reads. Discover the new field through a fresh
tool connection after activation; never assume an old server supports it.

If exact-window mapping is ambiguous, this route stays unavailable; preserve
the identity guard and use a verified visual route or an explicitly isolated
owned app instance. Never treat toolbar colour or click acknowledgement as
proof that the text buffer has keyboard focus.
Raw D-Bus paths, Cua indices and guessed coordinates are never direct semantic
targets. After an edit changes the semantic window context, read fresh semantics
before a dependent Save-button action. Incomplete trees remain read-only; use
the bounded diagnostic recovery below before declaring the bridge unusable.
An unsupported or still-incomplete route requires a verified alternative and
fresh result verification. A failed action may already have effects; inspect
its report instead of replaying it.

To narrow the returned direct elements, pass `query` as a string alongside
its required actual `window_id`, for example `query: "Save"` when that label
was observed. The filter lowercases the query and each emitted node's JSON
and performs a literal substring match across that JSON, including metadata.
It is not a label-only, role-selector, fuzzy or regex query. Omitted or empty
`query` returns all nodes from the captured subtree. Default traversal limits
are 1000 nodes and depth 40; `max_elements` and `max_depth` are capped at those
values. Filtering narrows returned elements, not traversal or visibility scope.
For `elements_complete=false`, inspect `traversal_diagnostics`, its effective
bounds and `incomplete_reasons`; null/missing diagnostics mean the cause is
unknown. If a lower requested bound was cut off (`max_depth_cutoffs` or
`max_nodes_cutoffs`), make one fresh read of the same exact window with
`max_depth:40,max_elements:1000`. On an older backend without diagnostics,
one such full bounded read is also reasonable if the previous limits were
lower; do not claim a proven cutoff. Keep `query` a literal string matching
an observed target, or omit it when the intended field is not yet identified.
Do not repeat an unchanged incomplete request or increase already capped
bounds. Larger limits do not repair mapping, visibility or owner errors;
preserve those refusals and choose a supported alternative deliberately.

The daemon builds the full snapshot and retains its handles before filtering.
Inspect `niri_window_id`, PID/title, `semantic_scope`, `visibility_traversal`,
`elements_complete`, `total_element_count` and `returned_element_count`.
An empty filtered result means no substring match in that snapshot; it does
not establish that the control is absent. Change the query or inspect the
unfiltered snapshot without changing windows or treating a limited tree as
complete. Filtering does not extend handle freshness or change action guards.

Before acting, require `elements_complete=true`, the fresh intended window
identity and a nonempty daemon handle for a showing, enabled node whose
label/role/description match the task. For replacement also require
`editable=true` and `capabilities.set_value=true`, with the complete prior-text
precondition. For a named action require `capabilities.click=true` and choose
an exact entry from `action_names`. A query match or role alone grants no
capability. Inspect a fresh result after the action; dependent context changes
still require fresh semantics. Use visual input when the bridge cannot supply
a valid target, preserving the existing independent result checks.
On the tested Zen 1.21.8b bridge, `SetTextContents` acknowledged a no-op.
Use fresh named actions and guarded keyboard input for browser editing;
an acknowledgement does not prove focus or text. If a named `activate` action
is used to focus an entry, read fresh semantics and confirm its focused state
before dependent typing. The adapter reads individual action names and bounded
text ranges because Gecko's bulk action names and oversized ranges were faulty.
Do not repeat an uncertain setter; inspect the actual result and change route.

Before content typing, paste or buffer-wide editing shortcuts, prove the
intended text buffer has focus separately from top-level window focus. Prefer
a fresh complete semantic read showing `focused:true` on the exact intended
text object, with its label/role and document or field identity. If that route
remains unavailable, use an app-supported document/field-focus command or a
fresh tightly grounded crop, then confirm a visible caret or selection in the
identified buffer before editing. A blank area, placeholder link, toolbar
colour or focus/click acknowledgement is not that proof. If focus remains
uncertain, pause the content step and report the verified partial state;
do not test it by typing. A new modal or focus change requires fresh proof.

Focus the identified window with a separate action, then observe again.
Focus requires an observation younger than 60 seconds and a fresh matching
Niri inventory identity (ID, PID, app, workspace and layout). A changed or
unknown target refuses before dispatch; observe again instead of guessing.
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

If `actor_release_confirmed` is false after the actor and queue are idle,
`desktop_recover_release` offers one explicit release-only retry with a shared
200–2000 ms budget (default 1500 ms). It refuses busy writers and never presses,
moves, creates an actuator or replays completed work. Check the returned stages
and fresh status. Success retains the original failure and any takeover cause;
it clears old captures/handles, so obtain a new observation. It does not return
control after a human takeover. Continued failure requires inspection and a
deliberate reconnect of only this owned backend with the latch preserved.

The cooperative input policy reserves physical **Esc** for explicit desktop
abort. Ordinary local keyboard/mouse activity does not latch takeover: it
invalidates stale observations and may interrupt a colliding action batch.
For `input_conflict`, inspect completed/possible effects, confirm release,
wait until `held_state_known=true` and `held_controls=0`, obtain a fresh
observation and recover only the unfinished step after input is quiet. Reprove
text focus before dependent editing; never replay an already completed effect.
This is recovery within the same task, not a task abort. Held physical
modifiers/buttons refuse input temporarily; releasing them permits fresh
continuation without `desktop_resume`.
Do not end the goal, end its indicator or request desktop permission merely
because ordinary input changed focus, selected another tab, or added unexpected
text. A failed batch and a stopped goal are separate states. Read the actual
partial effects and current contents, preserve human edits, and replan the
remaining step from that state. If a disposable test needs an exact baseline,
keep the interrupted buffer as evidence and continue in a fresh owned test
document; do not silently erase the user's text or classify the conflict as
Escape. For ordinary real work, reconcile the requested change with the current
contents rather than replacing the whole buffer with an older snapshot.
Keep the same goal and task indicator through this recovery. Explicit
cancellation/takeover stops the goal. An unrecoverable capability failure or
genuinely ambiguous intended work requires a clearly reported pause with the
verified partial state; do not announce goal cancellation or success. Merely
unexpected ordinary input is not such a blocker. A newer user instruction takes precedence over
older stored advice to stop on every unexpected UI change.
Once the remaining operation is known and its earlier effects are resolved,
avoid another model round between unchanged grounding and dispatch: a bounded
code execution may read fresh status, observe and the required focused semantics,
explicitly check the exact window/document/contents and then send that one
remaining operation. If any check fails, return the evidence to planning instead
of acting or looping blindly. This preserves the same backend guards and never
replays an uncertain edit merely because the original request was valid.
Ordinary input may leave a captured image non-actionable: inspect `input_ready`
and `fresh_observation_required_for_input`; do not use an old image's generation
for input. A read-only image can still support planning. Two quick collisions
are not sustained contention and must not end the whole task. Give the user a
brief progress update, keep the task indicator alive, and wait with bounded
status checks for a short release/quiet interval before observing again. Use a
reasonable time budget (up to 30 seconds for one contention episode) rather
than escalating clicks or counting two failed frames as an abort. True Esc,
explicit cancellation and actual capability loss still stop promptly.
Never replay an uncertain edit, copy, move or submission without checking its
actual state. Keep recovery bounded and report sustained contention instead of
fighting for focus. Physical Esc or an explicit takeover stops the task and
requires the user to request continuation before resume. Synthetic agent Esc
for dialogs does not count as physical abort. Backend startup/legacy takeover
markers remain explicit and require the current user-authorized resume.
The independent emergency chord **Ctrl+Alt+Escape** remains available.
Normal T3/Codex tool cancellation is forwarded to the actor;
this requires the installed scoped-cancel Codex build in the actual client
process. A local Stop acknowledgement alone does not prove actor release.
Use priority desktop cancel/takeover and check release if it remains active.
The owned MCP entry enables parallel calls so priority control is not queued
behind a long client-side tool wait; the daemon still serializes physical input.
After changing that entry, use a fresh client connection. German shortcuts use a persistent canonical
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

T3's inherited `LD_LIBRARY_PATH` is for T3 itself. On the tested laptop it made
Meld load two incompatible GLib/AT-SPI library sets and fail before opening a
window. For an authorized task-owned Meld launch, remove only that variable
from the child environment (`env -u LD_LIBRARY_PATH /run/current-system/sw/bin/meld
OWN_FILE`); retain the graphical-session variables and let Meld's own wrapper
select its libraries. A transient user service must likewise omit the inherited
T3 library path. Do not change T3's or the user's global environment, and verify
the actual new app/window and GUI result after launch.
