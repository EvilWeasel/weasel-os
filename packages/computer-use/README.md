# Niri computer use

A persistent Rust desktop actor and stdio MCP bridge for the actual Wayland session.
The laptop Home Manager module installs the package, graphical-session service,
additive Codex MCP entry and the `niri-computer-use` skill. T3 and ordinary Codex
share the existing Codex home and the same single physical writer. Existing
clients need their supported MCP reconnect or a fresh agent session after config
changes. Source and service installation alone are not live acceptance.

## Operations and boundaries

Protocol schema 1 exposes status, real window/output/workspace inventory,
observations, Cua accessibility reads, direct AT-SPI reads, typed actions,
priority cancel, latched takeover and explicit resume. Observations carry a
unique session/observation ID, monotonic timing, actual PNG/crop dimensions,
Niri identity, fractional output geometry and capabilities. Coordinates are local
to the returned screenshot or crop. Cua bounds are not screenshot coordinates.

Input uses output-bound wlr virtual pointers and a canonical German Wayland
keyboard. Every chord refreshes and acknowledges the keymap. Focus is a separate
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

Auto text uses plain clipboard for verified Electron IDs and text over 1000
characters; other shorter input uses wtype. Electron keyboard text is known to
lose physical keycodes and supplementary Unicode on this laptop. Clipboard
preservation uses a bounded RAM-only snapshot from one data-control offer and
fresh source identity checks. Supported text/rich payloads and original Chromium
custom data/provenance are restored together; the temporary agent text never
carries original Chromium source tags. Duplicate MIME names are normalized.
`SAVE_TARGETS` is an X11 clipboard-manager marker and is intentionally omitted,
with that omission reported. Unknown, sensitive, portal-handle or oversized
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
explicit cancel/takeover stops the shared pending queue. Physical evdev activity
latches takeover when available, without retaining event contents. Controlled
input simulation is not a claim of real human takeover.

## Start, stop and handover

```sh
systemctl --user status weasel-computer-use.service
weasel-computer-use call desktop_status '{}'
weasel-computer-use call desktop_cancel '{}'
weasel-computer-use call desktop_takeover '{}'
```

**Ctrl+Alt+Escape** independently requests takeover through Niri. Check confirmed
input release; completed effects persist. Resume only when the user returns
control, then obtain a fresh observation. Repair only this owned backend; do not
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

## Verification status

Offline Rust subprocess/deadline/capture/transport regression is reproducible
with the locked Cargo files. Nix host builds check packaging. Real application,
client, restart, takeover and multi-display evidence belongs to the private
acceptance matrix and demo; builds and fixtures alone do not complete acceptance.
