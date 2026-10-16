# Niri computer use

A persistent Rust desktop actor and stdio MCP bridge for the actual Wayland session.

When the live tool schema exposes `close_window`, a caller can request closure
of one freshly observed, focused, task-owned window by its explicit Niri ID.
It is a standalone action with matching top-level and action IDs. Prove safe
saved state before requesting it; the actor cannot attest document ownership
or unsaved buffers. A request acknowledgement is not window disappearance:
inspect a fresh full inventory and any save dialog. Never use shared process
termination as window cleanup. This source path still needs live qualification.

The cooperative desktop policy treats physical Esc as an abort only while a
Computer Use task is live: its actor action is queued/preparing/running, or its
task-owned indicator scope is open across model-thinking gaps. An idle Esc still
advances the physical input generation and invalidates old observations, but
does not latch a takeover or persist a marker. An in-scope Esc advances the
cancel epoch immediately, stops preparation and queued actions, releases owned
keys/buttons, and persists `physical_escape`. Completed/partial effects remain
reported and are never replayed. A real explicit desktop takeover remains a
separate, stronger persistent stop and has higher cause priority than a later
Escape.

The indicator opens an actor-owned task scope when it begins and closes it on
end, disconnect, stop or lease expiry. Its fixed 20-minute bound is not renewed;
expiry only drops stale scope ownership and never resumes work. A latched
`physical_escape` can be cleared only by a fresh, explicitly requested Computer
Use task with a new task ID and current backend session/epoch binding. The first
resume call returns a visible two-second `rearm_warning` and a unique
`scope_token`; wait that interval and retry once with the same task ID and
binding. Esc during the warning keeps or refreshes the stop. A successful
resume binds the indicator scope to the new task before clearing the old stop;
start the indicator with that task ID and returned `--scope-token`. Include the
same task ID on every `desktop_act` call. A live indicator permits multiple
batches for its one task; stale, ended, reused or mismatched IDs are refused.
Resume also requires released controls and
the existing 300 ms quiet gate, and always requires a fresh observation before
input. Explicit takeover
and legacy persisted markers keep their existing explicit-return policy. No
stopped task or queued action is resumed or replayed.
Authoritative bounded evdev key snapshots retain only the aggregate number of
held physical controls. Held modifiers/buttons or unknown input state temporarily
refuse dispatch, without latching takeover; release and fresh observation allow
continuation. Raw key bitmasks are discarded immediately.
The laptop Home Manager module installs the package, graphical-session service,
additive Codex MCP entry and the `niri-computer-use` skill. T3 and ordinary Codex
share the existing Codex home and the same single physical writer. Existing
clients need their supported MCP reconnect or a fresh agent session after config
changes. Source and service installation alone are not live acceptance.
For task-owned Meld launches from T3, omit only the inherited `LD_LIBRARY_PATH`
in that child process. The tested GI import otherwise loads conflicting T3 and
Meld GLib/AT-SPI versions. Preserve graphical-session variables and rely on
Meld's own package wrapper; actual window/edit/save verification remains required.

T3 desktop execution defaults to one delegated GPT-6-luna Codex worker with
medium reasoning; the parent conversation can retain its selected model.
The worker receives the full task and is the sole input owner. Optional
`desktop_decide` uses the separately budgeted Decisions endpoint for bounded
predicate/choice checks, rather than free action planning. Deterministic
readback should avoid unnecessary paid model checks.

A separate small GTK3/layer-shell indicator marks the selected output with a
blue rim and `Computer Use · Esc zum Abbrechen`. It is click-through and never
takes keyboard focus. The owned workflow helper spans model-thinking gaps,
binds the actor session/epoch, and closes on end, disconnect, explicit abort or
lease expiry. The renderer is C and the lifecycle helper is Python; capture,
input, freshness and cancellation remain in Rust. This is an explicit workflow
lifetime, not a claim that a per-action active flag covers an entire task.

The managed `mcp_servers.weasel_desktop` entry uses
`default_tools_approval_mode = "approve"` for the explicitly authorized desktop
control. This is a policy for this owned server only; global Codex approval and
sandbox settings and other MCP servers retain their existing configuration.
Tool annotations identify observation tools as read-only, actions as potentially
destructive writes, and cancel/takeover/resume as local control mutations. Use
these tools within the user's requested task. After activation, verify the
connection in a fresh ordinary agent session and complete an authorized workflow.
The owned entry enables `supports_parallel_tool_calls` so status and priority
control can reach the daemon while an action is waiting. The daemon still owns
the single physical input queue. Existing Codex clients need a fresh connection
to load this setting. The laptop's [source-built Codex](../codex-source/README.md)
also forwards interrupted MCP requests; an agent's local Stop acknowledgement
alone does not establish actor release.

## Operations and boundaries

Pointer actions require a displayed view no larger than 1200 pixels on either
axis. Larger screenshots remain available as overviews. The actor validates
every move, click, scroll and drag before admitting the batch, so a later
oversized pointer target cannot follow earlier typing or other batch effects.
The error asks for a fresh target crop and crop-local coordinates. Smaller
crowded targets still require appropriate tighter grounding by the planner;
this size bound alone does not establish target identity or UI success.

Protocol schema 1 exposes status, real window/output/workspace inventory,
observations, Cua accessibility reads, direct AT-SPI reads, typed actions,
priority cancel, latched takeover and explicit resume. Observations carry a
unique session/observation ID, monotonic timing, actual PNG/crop dimensions,
Niri identity, fractional output geometry and capabilities. Coordinates are local
to the returned screenshot or crop. Cua bounds are not screenshot coordinates.

Direct AT-SPI labels remain readable during ordinary input or held controls.
The standalone `semantic_focus` action targets an actionable opaque handle.
It invokes Component.GrabFocus once, repeats exact context validation and reads
FOCUSED on the same object. A boolean acknowledgement alone is insufficient.
Fresh visual and semantic observations must confirm the desired text focus
before dependent keys; selection, clipboard and artifact checks remain separate.
Duplicate window-title mappings retain their existing refusal.

When the live MCP schema exposes `include_text_selection`, direct semantics
can opt into bounded selection metadata for one focused, showing, enabled,
unprotected Text object. Its provider character count and Unicode-codepoint
[start,end) range are sampled twice, with focus readback. Only
`status: "available"`, `stable_readback: true` and
`full_text_selected: true` attest a nonempty whole-object selection.
These samples are not atomic and `text_identity_verified` remains false:
check the exact document/content, complete tree, current generation and
input readiness separately. Missing metadata, unsupported/error, multiple
selections or stale state supply no proof. Default false adds no selection
reads. This optional schema needs a fresh tool connection and actual
GTK/Electron bridge qualification; it does not normalize a terminal LF or
change input/cancel permissions.

Direct snapshots also expose versioned `traversal_diagnostics`: effective node
and depth bounds, the existing soft elapsed-time checkpoint budget, and counters
for actually encountered cutoffs, read failures and visibility contradictions.
Counters describe observed checks, not a count of omitted descendants. Legacy
snapshots publish `null`, which means the producer supplied no diagnosis.
These fields do not grant handles or change completeness or input readiness.
If an explicitly lower bound caused truncation, one fresh read at the supported
defaults (depth 40, 1000 nodes) can clarify the result. Persistent read errors,
visibility contradictions or deadlines require a deliberate alternative route;
increasing limits does not establish a valid semantic target. The 3000 ms value
remains a soft checkpoint boundary, not a per-call or atomic timeout guarantee.
`status: "available"` or `"limited"` describes the tree, while `input_ready`
and `action_ready` describe the separate readiness snapshot. Incomplete or
initially/finally non-actionable trees issue no new handles or mutation
capabilities. A conflict removes only this read's newly staged handles;
Escape, deadline and local cancellation remain errors. After controls are
released, obtain a new complete semantic snapshot and a fresh visual observation
before input. Native MCP cancellation of this read remains limited by its
existing `Other` request classification; the action cancellation path is separate.

The visual guard keeps one bounded decoded reference image: at most 16 MiB of
pixels and 4 MiB of original PNG bytes. A hit still rereads and compares the exact
reference bytes and checks the observation, session, epoch and input generation.
Click, scroll and drag still capture and decode fresh current pixels before
dispatch. Move retains its existing absence of a current-pixel comparison.
Decode and file I/O do not hold the cache mutex; stop and recovery invalidate
the reference. These storage limits describe retained payload, not process RSS.
The cache is an implementation optimization; live timing and successful task
outcomes are required before claiming a speed improvement.

Startup status distinguishes `capture_state: "not_attempted"` from a failed
capture. `capture_available: false` by itself does not establish a failure or
prevent an authorized startup resume. Inspect the current latch, actor release,
queue and `resume_input_readiness`; readiness is advisory, not permission.
An active `desktop_resume` requires `expected_epoch` and
`expected_session_id` from the current backend status for the stop the user has
authorized resuming. Do not use the historical cause's session or automatically
refresh a stale binding after another stop. The proxy checks binding support
and forwards a distinct bound wire method so an older replacement backend cannot
ignore these fields. An idle, released, already-resumed actor permits a read-only
no-op without changing the epoch or cached targets.
Both action and resume MCP requests have request-scoped cancellation ownership.
A cancellation can still arrive after a transition has completed; inspect fresh
status rather than assuming reversal. Active physical Escape has priority over
test, startup and explicit takeover markers, and every new accepted stop gets
its own cause identity. A failed persistence or rollback remains a visible stop.

For visual input, the skill treats images over 1200 pixels on either axis as
overviews and requires a fresh crop no larger than 1200 pixels on either axis.
Small or crowded targets also need crops. Ground points in the actual returned
crop dimensions and view; do not infer a model's prepared image dimensions from
monitor scale or a chat thumbnail. The actor checks freshness and nearby pixels,
but cannot prove that an arbitrary point belongs to the named window when Niri
does not provide absolute bounds. Check the new focus and intended UI effect;
a wrong window requires a separate focus and fresh grounding before recovery.

Input uses output-bound wlr virtual pointers and a canonical German Wayland
keyboard for app shortcuts. Every app chord refreshes and acknowledges the keymap.
`key` accepts `key_scope: "app" | "compositor"`, defaulting to `app`.
Super/meta/logo automatically select the compositor route. Niri's current
Wayland virtual-keyboard handler sends chords directly to the focused app and
does not run the compositor shortcut filter, so global shortcuts use an owned
persistent uinput keyboard. Preparation verifies the authenticated Niri process
has opened that exact device, then rechecks layout, observation, focus and stop
state before input. Device readiness is not evidence that a shortcut worked;
verify the resulting UI. A new proxy rejects a global batch against an older
backend before any action, requiring `global_keyboard.routing_revision = 2`
and the same session, epoch and observation. Capability failure has no blind
Wayland fallback. Release cleanup tracks possible partial writes and destroys
the owned device if necessary; unconfirmed release blocks further input.
Focus is a separate
action and requires fresh observation. The actor revalidates focus, window
identity, geometry, workspace/output binding and pointer target pixels. It does
not invent Niri window bounds or prove a coordinate belongs to a named control:
the planning client must ground the actual intended target from the observation.

`desktop_act` accepts at most 32 stable actions with a whole-operation deadline.
Queue, validation, subprocesses, input and post-action capture share that budget;
release cleanup retains its own bounded budget. Default post-action settle is
80 ms and adjustable to 0–1000 ms. It is not proof of repaint. The returned
`after_observation` and image may feed the next action directly. Changed or slow
UI needs a bounded fresh result check rather than replaying toggle input.
Effects, partial effects, release status and failures remain explicit.
At the stdio MCP boundary, observation/action replies abbreviate exact known
explanatory prose and replace valid display mode catalogs with the exact selected
mode, original index and catalog fingerprint. All window identities, geometry,
guards, effects, errors, timings and image bytes remain. Control fields precede
large inventories in JSON text. `detailed: true` returns the original complete
envelope; `desktop_windows` also retains full mode catalogs. Internal observations,
actor state, event receipts and ordinary CLI replies are not projected.
When the live MCP schema exposes `compact`, `compact:true` additionally narrows
the window inventory in observation/action replies. It retains focused,
capture-active, explicitly targeted, urgent, floating and unfamiliar windows,
and reports omitted IDs, original count, an inventory fingerprint and
`windows_complete:false`. All other state and PNG bytes remain unchanged.
Use `desktop_windows` to discover the complete window set or `detailed:true`
for the full reply. A missing window in this opt-in subset is not evidence
that it is closed. This is a payload optimization, not a measured model-latency
or reliability improvement; the actor continues using its full observations.
Fields must match the selected action kind. An unknown or misplaced field
rejects the complete batch before input. In particular, `restore_clipboard`
belongs to `paste`; `type` always requests preservation of the prior selection.

If a bounded cleanup receipt fails, new input remains refused. When the actor is
idle and the queue is empty, `desktop_recover_release` explicitly retries only
release/receipt on existing owned actuators. It never creates a device, moves the
pointer, presses a key or replays an action. Its shared timeout is 200–2000 ms
(default 1500 ms); busy locks refuse immediately. A successful retry preserves
the takeover latch, cause and epoch, retains the original failed result, and
invalidates captures and semantic targets. Check status, then obtain a new
observation before input; a human takeover still requires the user's return of
control. A genuinely broken connection remains unconfirmed and needs a deliberate
repair of this owned backend. Receipt confirmation is separate from UI success.

Auto text uses plain clipboard for verified Electron IDs and text over 1000
characters; other shorter input uses wtype. Electron keyboard text is known to
lose physical keycodes and supplementary Unicode on this laptop. Clipboard
preservation uses a bounded RAM-only snapshot from one data-control offer and
fresh source identity checks. Supported text/rich payloads and original Chromium
custom data/provenance are restored together; the temporary agent text never
carries original Chromium source tags. Duplicate MIME names are normalized.
`SAVE_TARGETS` and `GTK_TEXT_BUFFER_CONTENTS` are intentionally omitted without
reading, with each omission reported. The latter is GTK's SAME_APP pointer
optimization; replaying that address from another process would be invalid.
The exact `application/x-gtk-text-buffer-rich-text` representation is preserved
as bounded opaque bytes together with the text formats. This follows
[GTK3's own clipboard persistence rules](https://github.com/GNOME/gtk/blob/3.24.51/gtk/gtktextbuffer.c#L3809-L3812).
Unknown, sensitive, portal-handle or oversized
formats refuse before replacement. Restoration remains best effort because
Wayland provides no atomic selection CAS, and is skipped after cancellation,
takeover or ownership loss. A separate owned user scope holds the restored
source until a new copy or graphical-session stop; live restart persistence
still requires runtime verification. `paste` with `restore_clipboard=false` is deliberate replacement,
appropriate only when authorized and the previous selection is understood.
Do not suggest unreliable keyboard text as an Electron fallback. Caps/Num lock
state is not supported. VS Code's tested isolated profile uses keyCode dispatch;
other profiles need actual shortcut verification.

Direct AT-SPI uses immutable unique-owner D-Bus object identities and daemon-owned
opaque handles, not integer indices or caller-supplied object paths. Handles bind
to the observed Niri instance, bus generation, epoch and expiry. Mutations
revalidate role, interfaces, ancestry, enabled/showing state, modal membership
and visible text context. Traversal retains the selected window root and
descendants whose ancestor chain reports SHOWING. Hidden branches are omitted;
immediate visibility contradictions, unknown states, budget exhaustion or a
hidden selected root make the result read-only. Completeness applies to this
versioned visible scope, not inactive tabs or unvisited hidden descendants.
Pruning counters and scope metadata are returned explicitly. Other long text
fields contribute bounded excerpts; set-value checks the target's complete prior
buffer. Missing bridges require the verified visual path, not blind retries.
Individual action names and CharacterCount-bounded text reads avoid the tested
Gecko bulk-action/range defects. The tested Zen 1.21.8b setter still acknowledged
a no-op, which exact readback reported as uncertain. Browser editing therefore
uses verified keyboard input; semantic activation/press needs separate live
proof. Advertised interfaces alone are not an app capability guarantee.

Capture failure invalidates old observations/semantic handles until a successful
fresh capture. Hotplug/global removal refreshes capabilities and refuses stale
connections. One lifetime flock spans socket paths; a second daemon cannot own
physical input. Normal-client disconnect/cancel applies only to its own request;
explicit cancel/takeover stops the shared pending queue. Physical evdev Esc
press latches takeover; other activity advances observation generation without
retaining event contents or permanently stopping the task. Controlled
input simulation is not a claim of real human takeover.

## Start, stop and handover

```sh
systemctl --user status weasel-computer-use.service
weasel-computer-use call desktop_status '{}'
weasel-computer-use call desktop_cancel '{}'
weasel-computer-use call desktop_takeover '{}'
```

Physical **Esc** requests abort only during a live Computer Use task scope;
idle Esc invalidates old observations without latching the actor.
**Ctrl+Alt+Escape** remains a separate explicit takeover through Niri.
Synthetic agent Escape for dialogs does not trigger physical abort. Check
confirmed input release; completed effects persist. A latched physical Escape
can be cleared only for a newly requested task after its 2-second warning,
current session/epoch binding and quiet/released gates; use the returned
`scope_token` with the indicator and the task ID with every action. An explicit
takeover still requires the user's return of control and cannot use the
physical-Escape re-arm path.
Repair only this owned backend; do not
restart T3, the compositor or foreign clients as chaos tests.

Typical requests: edit and save a specified test document in an identified app;
fill a local form in an existing browser test tab; copy a specified selection
between identified apps and verify the destination. Preserve original tabs,
profiles and documents. Authentication and locked-session bypass are unsupported.

## Future Rust/voice boundary

Capture/Input stay separate from model planning. `observe` produces identity,
geometry, semantic data, image references and timings; `act` binds task/action
intent to an observation and deadline. Verification consumes a *new* observation
and independent artifact evidence and yields success/failed/uncertain in the
planning client; input acknowledgement is not verification. `cancel/takeover`
preempt pending execution and report completed effects. Private schema-1 events
record request/progress/capability/action/result/timing and failure metadata.
This version provides no voice implementation. Speech processing must not block
the actor or priority stop operations.

The optional Python UI Decisions evaluator has its own service, API credentials
and persistent authorized budget ledger. The Rust actor has no model credentials
or API access. See the evaluator README for explicit start and cost boundaries.

## GUI application lifetime

A background command owned by a Codex `exec_command` session can be finalized
when that agent run ends. This happened to our three isolated Calc test profiles,
after their verified files were already saved. For an app that should remain
open, launch its own transient user service with `systemd-run --user --collect
--unit=weasel-cu-app-<unique-task> --service-type=exec --property=ExitType=cgroup
<absolute-app-command> <explicit-own-profile-and-files>`. Keep its unit, profile,
process and window identities together. An existing shared application may
forward to its earlier process; the launcher unit alone does not establish
window ownership. Use a supported per-app profile/new-instance option where
needed, and verify the actual result after the agent exits. Do not stop shared
user apps or their services to clean up a launcher.

Meld's GtkSource buffer omits an implicit final LF while loading, then restores
it on Save. Native Select-All/Copy therefore may omit that file byte. For an
exact file-transfer task, compare the genuinely pasted/saved result before
normalizing it: only when the sole difference is one required final LF, move
to the destination's end, insert one Return and Save through the UI. Report
that normalization; other differences require investigation.

## Verification status

Offline Rust subprocess/deadline/capture/transport regression is reproducible
with the locked Cargo files. Nix host builds check packaging. Real application,
client, restart, takeover and multi-display evidence belongs to the private
acceptance matrix and demo; builds and fixtures alone do not complete acceptance.

### Connected-output admission

Observation and normal post-focus capture accept any connected, enabled output
in the current Niri inventory with a nonempty valid name and positive integer
logical dimensions. Launch admission rechecks current inventory membership,
focus identity, active workspace and exact observed geometry immediately before
spawn. Post-focus capture still requires the selected output to be focused.
`desktop_status.desktop_launch` reports `output_policy` as
`all_connected_enabled_niri_outputs`, the current valid `outputs`, and whether
the inventory was available; unavailable inventory reports no allowed outputs.
This policy does not change task/indicator ownership, privacy, physical Escape
or explicit takeover, generation checks, or the single desktop writer.

### Shared ESC-only lifecycle contract: source boundary checkpoint

Authoritative requirement: `COMPUTER-USE-ALL-DISPLAYS-ESC-ONLY-01` (2026-10-15).
The monitor admission checkpoint is independent of this contract. The following
mapping describes current source, not installed acceptance or new public APIs.

| Existing boundary | Actual ownership/fence | Missing shared-contract behavior |
| --- | --- | --- |
| `core/src/main.rs::indicator_lifecycle`, public `desktop_indicator_lifecycle` | Revision 3; events `begin/status/end`; `task_id`, `scope_token`, `session_id`, `expected_epoch`; begin requires unlatched idle/released actor; end removes only its matching scope and never clears takeover | Responsible thread/run/turn, exact target binding, all-display renderer readiness and external per-action admission |
| `main.rs::authorize_action_task`, `act_inner`, public `desktop_act` | Current task ID, retained observation, epoch/input generation, focused window/workspace/output geometry; same admission for pointer/keys and typed `semantic_click`, `semantic_set_value`, `semantic_focus` | No external CDP/MCP/HTTP/A2A app-control permit; task ID alone does not authenticate an external adapter |
| `main.rs::physical_activity`, `core/src/input_policy.rs` | Physical Escape fences epoch/latch and clears live scopes; synthetic events excluded; ordinary activity invalidates observation generation and currently ends a bound batch | Ordinary activity must only require target revalidation, without task abort; separate stop generation from target generation |
| `main.rs::record`, `core/src/takeover.rs` | JSONL envelope `schema`, `monotonic_ms`, `monotonic_system_ms`, `event`, `data`; stop data includes epoch/source/cause ID/persistence; marker retains cause across startup | No responsible-agent delivery/acknowledgement or retained stopped-scope owner; JSONL alone is not notification |
| `main.rs::desktop_resume` handler | Explicit session/epoch-bound operation; physical-Escape rearm currently has two-call 2-second warning | New policy requires a distinct explicit user decision, never elapsed time as permission; current runtime latch cannot be inferred away |
| `../computer-use-indicator/indicator.py`, `renderer.c` | One selected `--output`, process-identity ownership, renderer READY, click-through surfaces, lifetime/heartbeat checks | All-connected-output aggregate READY, blue border/ESC hint and hotplug coverage |

Proposed transport-independent envelope (contract revision 1, **not yet a public
implemented endpoint**):

```json
{
  "contract_revision": 1,
  "scope_id": "unique-never-replayed",
  "scope_token": "opaque-owner-capability",
  "session_id": "actor-instance",
  "stop_generation": 1,
  "target_generation": 1,
  "responsible": {"thread_id": "actual-thread", "run_id": "actual-run", "turn_id": "actual-turn"},
  "target": {"adapter": "actual-transport", "identity": "adapter-specific-exact-target"},
  "action_id": "unique-within-scope"
}
```

`stop_generation` fences every transport of the same scope. `target_generation`
is independent: normal human activity invalidates old targets but does not stop
the ownership scope. Target identity must include the actual authority boundary
(window/process/session for desktop; actual application/connection/document or
resource identity for semantic/API control). A URL or model-supplied label alone
is insufficient. Ownership comes from the real consumer thread/run/turn; an
adapter must not invent native origin metadata. Tokens are private capabilities,
not fields for logs. No existing token or task ID is implicitly upgraded.

The bounded consumer handshake is:

1. Begin a single owned scope while the shared stop fence permits it. Bind real
   responsible identity and exact target; obtain scope/session/generation binding.
2. Wait for aggregate indicator READY covering every currently connected enabled
   display with click-through blue border and ESC hint. Missing renderer, output
   hotplug coverage or renderer failure refuses new mutations until readiness is
   established. READY is presentation evidence, never successful app control.
3. Immediately before each mutation, revalidate scope/session/stop generation,
   target generation/identity and shared single-writer ownership. Ordinary stale
   targets require a fresh target observation; they do not terminate the task.
   External adapters need shared fenced admission spanning the actual dispatch
   boundary and an in-flight receipt. A precheck followed by an unfenced external
   request cannot claim this contract. Unsupported adapters remain unsupported;
   direct CDP/HTTP/A2A calls cannot bypass the fence.
4. Physical ESC first fences new mutations and releases owned held controls, then
   emits a durable scoped stop event containing event/cause ID, physical source,
   session, prior/new stop generation, affected scope, real responsible owner,
   target/action identity and in-flight disposition. Controlled simulation and
   agent-synthesized Escape remain distinct; neither proves physical acceptance.
   Stop delivery failure retains the fence and pending notification. The owning
   agent acknowledges the event, stops further affected task tools and asks the
   user before continuing. Background reads/builds are outside this scope.
5. Receipts distinguish `not_dispatched`, `possibly_dispatched`,
   `cancel_supported` (capability only, with separate cancel attempt/outcome), and
   `completed` (transport completion, with independent result verification).
   Uncertain network/transport outcomes never imply rollback or safe replay.
6. End/release is terminal cleanup only and cannot clear a stopped latch. Only a
   separately explicit authorized resume decision bound to the current stop may
   create a new scope/generation; no timer, cooldown or old queue revival.

Implementation split, requiring exact Root leases before broader edits:
`main.rs` ownership/admission/stop-delivery and resume handlers plus embedded
fixtures; `input_policy.rs` separate target invalidation from stop fencing;
`takeover.rs` only if durable stopped-owner/event identity is added to its
validated marker schema. Indicator work separately needs `indicator.py`,
`renderer.c`, `test_indicator.py`, and `README.md`; existing monitor matcher is
reused unless an evidenced mismatch requires its own lease. Consumer adapters
and app-owned stop notification delivery remain their respective owners' paths.
No queue, workflow, system configuration, dependencies or runtime mutation is
part of this contract checkpoint. Hosted actor tests and indicator fixtures,
then separately authorized runtime/visual acceptance, are required before
claiming the shared contract implemented.

### Shared-control state core (host bridge unavailable)

The `core/src/shared_control.rs` module (aliased as `control_scope`) implements typed state
transitions: `Fence::begin(TrustedOwner, ExplicitContinuation, scope_id, token,
Target) -> Binding`, `indicator_ready(Binding, mapped, current)`,
`admit(Binding, Target, action_id, outputs, cancel_supported)`,
`crossing_send_boundary(Binding, action_id, Target, current_outputs)`, `complete(Binding, action_id)`,
`cancel_result(Binding, action_id, outcome)`, `stop(source) -> StopEvent`,
`delivered(event_id, TrustedOwner)`, `acknowledge(event_id, TrustedOwner)` and
`end(Binding)`. These are internal Rust methods, **not public JSON endpoints or
remote dispatch permits**. Private trusted owner/explicit continuation types
have no production JSON constructors. A model cannot register a trusted owner.

`desktop_status.shared_control` exposes revision 2 with `available=false`, no
supported transports, and explicit unavailable trusted-host, dispatch-bridge and
responsible-turn-delivery fields. Existing lifecycle revision 3 is not silently
upgraded. The state core separates stop generation from target invalidation,
requires exact aggregate display coverage before admission, retains in-flight
uncertainty and makes delivery/ACK independent from resumption. Existing legacy
batch input guards and resume warning remain unchanged until the authenticated
consumer bridge and per-action revalidation path are composed and qualified;
this checkpoint does not claim the complete new ESC-only behavior.

`core/src/takeover.rs` persists optional validated `control_stop` metadata in the
existing private stop marker, with responsible thread/run/author-turn, exact
target, operation disposition and delivery/ACK state. Startup restores only the
stop, never its live scope/token. Pending events cannot be replaced or regressed,
and unacknowledged control events prevent clearing the marker. Acknowledgement
persistence itself never clears the latch. Ten new embedded state/Store-free
marker tests are for hosted execution, not real host identity or GUI proof.

The real T3 seam identified by Integration is authenticated
`McpInvocationContext` from `McpHttpServer`/registry: it binds thread/provider
session/instance/environment, but lacks current run and author-turn. Direct
`weasel_desktop` is currently outside that authenticated context. T3 must supply
the canonical live producer binding and durable active-turn delivery, potentially
through its existing `ThreadManagementService.dispatch` steering path with exact
target run and inactive rejection. Queue acceptance alone is not stop delivery
or acknowledgement. Consumer adapters must not build against provisional wire
signatures or bypass this missing bridge.

### Jarvis browser-click platform kernel, revision 2

This source checkpoint extracts the historical e9ad state core into
`core/src/shared_control.rs`. It adds an actual **private Rust callback kernel**;
it does not add a public MCP action, HTTP endpoint, native browser adapter or
trusted-owner JSON constructor. `shared_control.available` stays false with
empty supported transports until the real producer/channel/native probe exists.
The hosted e9ad 183-Rust/32-indicator result is historical evidence, not a test
result for this new source. Indicator source is unchanged.

The source-callable boundary is:

```text
Controller::dispatch_browser_click(
  &self, owner: &TrustedOwner, scope: &Binding,
  command: &BrowserClickCommand, cancel: Arc<AtomicBool>,
  execute: impl FnOnce(&mut BrowserSendBoundary) -> R<()>
) -> R<BrowserDispatchResult>

BrowserSendBoundary::send_native(
  &mut self, current: NativeBrowserSnapshot, cancel_supported: bool,
  send: impl FnOnce(&SendFence) -> NativeSendOutcome
) -> R<()>
```

`BrowserClickCommand` retains assigned job/action/capability/operation/revision,
Jarvis-local `author_session_id`, conversation/parent-turn/tool-call identity,
the exact prepared candidate and ActionContext. These remain separate from
`TrustedOwner`: local Pi/App attribution never becomes T3 authority. Scope tokens
are not returned in dispatch receipts or stored in stop metadata. The canonical
T3 native attribution additionally includes environment, attempt/root, provider
instance/session/thread, native turn/call and runtime incarnation. Copied fields
are attribution only: the private trusted owner has no production constructor.

Browser targets retain adapter/surface/element, numeric target generation,
context/observation and opaque registry-generation token. A native observation
must additionally bind connection incarnation, native session/CDP target, frame,
document and remote object. The native snapshot has no public fields/JSON
constructor; no production probe currently issues it. Missing evidence refuses
before invoking any send callback. A numeric surface generation is insufficient.

The authenticated host must hold its canonical owner/policy critical section
around the synchronous `execute` callback until actual crossing acknowledgement.
It must revalidate the original private owner at that point, not obtain a
precheck token and later send independently. The platform performs no inverse
callback to acquire the host lock. Its one writer gate also covers existing
physical/semantic actor batches and release recovery. Waiting browser commands
are reserved with their immutable identity before the host callback; a physical
ESC fences the independent atomic signal without waiting for actor state locks
or a remote response. Normal human activity only stales target grounding in
this kernel and does not stop the owned scope. Legacy public batch/resume rules
remain separate and do not silently gain this contract.

Immediately adjacent to native dispatch, the kernel rechecks scope/generations,
fresh exact native target and aggregate display readiness, then records
`PossiblyDispatched` before entering the actual send callback. No callback means
`NotDispatched`; lost/uncertain replies remain possibly sent. `Completed` is a
transport receipt requiring independent verification. Unsupported cancellation
and cancellation acknowledgement never imply rollback. An unknown operation
keeps the writer reservation until a real outcome/owned cleanup resolves it.
Action identity is consumed even on pre-send rejection; no automatic replay.

A stopped event retains the original owner/job/native-call, exact command and
original operation disposition. Later completion/cancellation information is
separate `latest_operation`; it cannot rewrite the original stop identity.
`cleanup_binding(original_owner, event_id)` produces a private cleanup capability
that requires neither current-run capture nor transfer to a newer run.
`Controller::record_durable_delivery(cleanup, DurableDeliveryProof, persist)`
records the exact original canonical cancel command/outcome and durable
acceptance identity; it returns its private `StopAckBinding` only after the
platform persistence callback succeeds.
`Controller::acknowledge_retained(StopAckBinding, persist)` authenticates that
same original identity/outcome and persists ACK; it cannot begin, send, clear a
latch or resume. `DurableDeliveryProof` has no production JSON constructor:
Jarvis App's in-memory CommandAck or cooperative cancel watch is not such proof.

Current producer gaps are source-backed and block product availability:

- T3 source 42f0c36 has real `RunExecutionService` native capture through
  `TrustedAppControlInvocation` and `CodexAdapterV2`, but only for Observatory.
  It has no actor consumer/channel injection. PM535's inherited duplex transport
  remains a proposal, not an implemented spawn/authentication seam.
- Jarvis source b3ef8fe (reviewed d6a2093) uses PiAssistantAuthor -> PiWorker
  stdin/stdout JSONL `host.call` -> PiAuthorTools. Its registered App author/turn
  does not carry a T3 native owner. This route needs a real authenticated
  issuer-domain/producer decision and private capability injection; neither
  model arguments nor runtime UID can manufacture it.
- Jarvis `targets.rs`/`cdp_browser_adapter.rs` provide page candidates, surface
  generation and ephemeral object references, but no supported fresh native
  frame/document/connection probe propagated to the platform. Existing owner
  leases cover only their allocated work; this kernel does not widen them.
- Jarvis CancelJob/cancel_author_job is cooperative/in-memory; responsible-agent
  durable physical-stop notification/acceptance and its authenticated delivery
  channel are still missing. The platform owns retained-event/ACK semantics,
  but cannot infer acceptance from App ACK or socket write.

Eleven new fake-native callback regressions cover correlation/replay, missing
producers, frame/document/object/registry changes, ordinary input, pre-cancel,
waiting ESC, priority stop during blocked remote response, original cleanup ACK
after run end/restart, conflicting outcomes, shared writer ownership and failed
persistence. They do not prove real host authority, CDP, native-vs-synthetic ESC
or fresh-process transport bootstrap. Compilation and full tests remain hosted
Blacksmith work of the existing Integration owner; runtime/visual acceptance
needs its separate authorized lane.

The callback result separates crossing from long completion: `NativeSendOutcome::Crossed`
returns a `BrowserDispatchResult` containing the correlated `receipt` and an
opaque `pending` completion capability. The host releases its canonical lock
after this bounded crossing acknowledgement; it must not await a long network
response inside that lock. `Controller::complete_browser_operation(pending,
NativeCompletion, persist)` later accepts only that original capability and
command, including after the live run is terminal. Completion metadata does not
repeat a send or authorize a new scope. Stop ACK and later outcome updates retain
the original stop command/disposition separately. Identical completed replies
return the original receipt; conflicting replies refuse.

A bounded in-memory receipt ledger returns the same original disposition for
identical action/owner/scope/command replay without invoking the callback. A
conflicting body or binding refuses; exhaustion refuses before new effects. This
is a receipt ledger, not a pending-work queue or automatic retry mechanism.
After process restart old live scope/capabilities never revive. A new-process
authenticated cleanup bootstrap is still unimplemented and is not proven by
same-process restart fixtures.

Cancellation fences precede fallible bookkeeping: `desktop_cancel` and
`desktop_takeover` advance the legacy epoch and trip the shared atomic stop
before shared-state/task-scope locks. Takeover also sets its latch first. A
poisoned lock reports failure after fencing, never a successful durable stop ACK.
Two hosted-only regression tests cover poisoned shared and task-scope locks for
both commands; no local test execution is implied.

PM541 partitions the product issuer from T3 native capture: Jarvis PiWorker's
registered host session/turn/tool-call must establish its own authenticated
host-origin issuer and private spawn/dispatch capability. This checkpoint has
no production Pi acceptance seam. `NativeExecution` is native-route attribution,
not a way to synthesize T3 IDs for Pi. Issuer authentication, incarnation,
revocation, exact call/body/job correlation and restart cleanup bootstrap remain
unimplemented. No owner is accepted from JSONL model arguments or process UID.
The existing `takeover::Latch::retain_control_stop` store retains original stop
metadata; it is not a recipient notification inbox. No durable recipient
acceptance API exists here. A future acceptance proof must bind the original
event/command/outcome and recipient identity, survive author termination and
persist before ACK success; App CommandAck and socket-write success do not prove
that acceptance. No new store or public wire is introduced by this checkpoint.

PM546 correction: delivery/ACK updates are staged under the controller state lock,
persisted, then published; failed persistence leaves prior metadata unchanged.
The takeover marker also restores only optimistic control-stop metadata on a
store failure, retaining its stop latch and persistence error. Failed delivery
or ACK cannot unlock explicit continuation after cleanup. Physical Escape now
advances the legacy epoch before bookkeeping locks, including while idle; idle
Escape invalidates old epochs/targets without creating a persistent takeover.
New source fixtures cover held-lock fencing, failed-store state invariance and
blocked continuation, followed by exact successful persistence. They remain
hosted-only verification; no runtime acceptance is inferred.
