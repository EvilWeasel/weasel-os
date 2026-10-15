# Task-owned Computer Use monitor indicator

This is presentation beside the Rust desktop actor. A small C/GTK3 renderer uses
the already available GTK layer-shell library; it contains no screenshot,
accessibility, focus, input, model, API or credential code. The Python standard
library helper owns its lifetime and reads actor status. GTK is isolated here so
the Rust capture/input core does not gain a GTK dependency or another Cargo tree.

The indicator has four solid blue 4-logical-pixel edge surfaces and a compact top
label: **Computer Use · Esc zum Abbrechen**. All five surfaces request the overlay
layer, explicitly disable keyboard focus, use empty input regions, and reserve no
workspace. A single helper owns one renderer per connected enabled Niri output,
including full-screen windows. `--output` remains the task's anchor identity;
it no longer limits indicator coverage. Disabled outputs have no drawable surface.
READY is aggregate: it is emitted only after all five surfaces on every output
have mapped and the full output inventory has been revalidated. Its `outputs`
list and total `surfaces` count describe that exact inventory.

This implementation needs live Niri validation. Successful compilation, fixture
tests and the renderer's `ready` event do not prove visible edges, click-through,
correct physical output, full-screen stacking, or the real T3 Stop lifecycle.

## Ordinary worker-owned session

After the user grants control, explicitly resume the actor and verify it is idle,
released and unlatched. Run this in the actual worker's own `exec_command` session
with `tty=true` so stdin is held open:

```sh
weasel-computer-use-indicator run \
  --task-id demo-luna-r1 --output DP-6 --stdin-control
```

Wait for the concise `ready` event before desktop actions. Retain the command's
session ID. The helper deliberately stays foreground and keeps the indicator
alive while the model thinks between desktop batches. Do not detach it into an
unrelated always-running service. Do not substitute the broad shared T3 appserver
PID for a task's actual lifetime. Default parent-process identity is checked; an
explicit owner requires both `--owner-pid` and its exact `/proc` starttime field
through `--owner-start-ticks`.

End on workflow completion, client cancellation or failure:

```sh
weasel-computer-use-indicator end --task-id demo-luna-r1
```

Alternatively send `v1 end\n` through the retained session's stdin, or terminate
the exact owned helper process. The `end` command acknowledges the request; the
foreground helper's final `ended` event and process completion confirm renderer
exit. It reports the cleanup duration separately. The indicator does not itself
cancel desktop input; the actor's explicit Escape/Stop path owns cancellation.

```sh
weasel-computer-use-indicator status --task-id demo-luna-r1
```

Only the exact task ID and same-user Unix peer can control the session. Private
mode-0600 task socket/lease files are under
`$XDG_RUNTIME_DIR/weasel-computer-use/indicators`. One indicator owner per connected output
is enforced through locks acquired in sorted output order. Any output addition,
removal or geometry change ends the whole presentation scope; a new complete
READY is required before further admitted control. An existing task identity is never silently replaced. Metadata
contains only task/process/actor identities, timing, target geometry and the
private control reference. It contains no credentials or app/window content.

## Lifecycle contract, revision 1

The renderer accepts a held stdin pipe with these exact newline-terminated lines:

```text
v1 begin
v1 heartbeat
v1 end
```

Arguments fix output name, task ID and the freshly obtained Niri logical rectangle
for the lifetime. Its GDK monitor must match that rectangle uniquely; fractional
scaling may differ by one logical pixel in width or height, while position stays
exact. Once selected, any change to the original GDK geometry ends the renderer;
the helper independently requires unchanged Niri geometry. There is no
default-output fallback. All surfaces begin hidden. A 1-second helper heartbeat
keeps the renderer alive. The renderer hides on end, EOF, malformed protocol,
signal, monitor invalidation/layout change, or a heartbeat gap exceeding
4 seconds. Startup also expires if no begin arrives. Namespace:
`weasel-computer-use-indicator`.

The helper's private control socket uses one bounded JSON line per connection:

```json
{"revision":1,"event":"end","task_id":"demo-luna-r1"}
```

`event` is `status` or `end`; both require exact task identity and same-user
`SO_PEERCRED`. Replies and stdout lifecycle events also carry revision 1.
Stdout events include a monotonic timestamp; timeout events additionally report
the owned request start/elapsed time without exporting the actor payload.

The helper registers one actor-owned task scope when its visible indicator
starts and closes it on normal end, disconnect, stop or expiry. That scope
keeps physical Escape effective across model-thinking gaps. The fixed 20-minute
scope is never renewed; expiry only drops stale scope ownership and cannot
resume any task. A resume warning returns an ownership `scope_token`; pass it
to `run --scope-token` with that exact task ID. Ordinary new tasks may omit the
option and the helper creates a fresh token. Each `desktop_act` call must carry
the indicator's exact task ID; multiple batches within that scope remain
allowed. The helper reads the actor's internal
`desktop_indicator_lifecycle` contract, revision 3 with `complete=true`:
session, cancellation epoch, task ID and owner token, takeover latch, active
flag, task-scope state, queue count and confirmed release. Begin, status and end
are bound to the exact session/epoch/token tuple; an uncertain begin ACK still
attempts matching cleanup. It excludes full `last_result`,
images, display modes and capture/input-readiness inventories. Unknown endpoint,
revision, incomplete or malformed replies fail closed; there is no full-status
fallback. This endpoint is internal, not another agent action tool.

After a valid startup response, exactly one nonblocking probe runs through the
helper's existing selector on a bounded 100 ms cadence. Each probe has a total
300 ms connect/send/read deadline, including fragmented responses. One timeout
may retry once with the same bound; a second consecutive timeout ends the frame.
No heartbeat is renewed while the response is pending or authority is unknown.
Only a fresh valid response for the original session/epoch and an unlatched actor
allows renewal. Startup timeout, EOF and other capability/contract errors have
no retry. Explicit end, stdin end/EOF, signals and parent identity checks remain
reachable while the probe is pending; closing it cancels only this read socket.

The helper ends on epoch or backend session change, takeover latch, idle
unconfirmed release, unavailable lifecycle, owner PID/starttime change, explicit
end, stdin EOF (when requested), SIGTERM/SIGINT/SIGHUP, target output/layout
change, or a hard maximum of 20 minutes. Active actions may legitimately have
unconfirmed release; that transient state does not hide the indicator. The
renderer still expires after 4 seconds without heartbeats. There is no automatic
resume or action replay, no replacement-backend reconnect, and no renewal beyond
the hard runtime bound. Shorter bounds can be requested with
`--max-runtime-seconds 1..1200`.

Lifecycle and output queries are read-only. Raw status, window titles,
environment, command arguments and credentials are never logged. The helper's
termination and the renderer lease do not establish that the actor has released
input: inspect fresh actor status independently after Stop/Escape.

## Component verification

```sh
python3 -m unittest discover -s packages/computer-use-indicator -p test_indicator.py -v
```

The tests use a fake actor, Niri inventory and renderer. They cover thinking gaps,
explicit end, cancellation epochs, takeover, backend replacement, active versus
idle release state, refused initial latch/owner mismatch, signal cleanup, hard
expiry and one output's competing ownership. Delayed and fragmented lifecycle
fixtures cover the single timeout recovery, second-timeout shutdown, no renewal
while unknown, known stop responses, unknown contract rejection, and end/parent
exit during a pending socket. These are private process/socket tests, with a fake
renderer; they do not prove visible monitor edges or ordinary T3 task cancellation.
The Niri geometry subprocess remains bounded by its existing 1-second timeout;
that independent query can still delay local event processing. Core lifecycle
reads retain the active-state mutex and may time out while release recovery holds
it; the bounded retry does not redefine such release/capability uncertainty.
Root must still prove the real monitor rendering, click-through and task Stop
including a model-thinking gap from ordinary T3/Codex sessions.

## Narrow package delivery

Package version `0.1.1` includes the revision-3 actor client and runs both the
C monitor matcher and the Python lifecycle fixtures in its Nix `checkPhase`.
The helper/renderer control protocol remains revision 1; that is separate from
the actor's `lifecycle_revision=3`, `complete=true` requirement.

Build this package on the existing Namespace `namespace-profile-ci-builder`
runner from the exact reviewed candidate commit, without a host-system build:

```sh
nix build --impure --no-link --print-out-paths --expr '
  let
    flake = builtins.getFlake (toString ./.);
    pkgs = import flake.inputs.nixpkgs { system = "x86_64-linux"; };
  in pkgs.callPackage ./packages/computer-use-indicator { }
' > indicator.store-path
```

Retain the commit, locked input hashes, build/check log, exact output path and
closure transport checksum with the CI artifact. Export the complete closure
on that runner using `nix-store --export` and its `--query --requisites` list;
Integration imports those verified bytes on the laptop. This package does not
need a NixOS switch, actor restart, microphone service or local compilation.
The current `namespace.yml` workflow has only both-host evaluation/build and
storage-probe inputs; it does not export this targeted closure. A workflow
dispatch acknowledgement is therefore not evidence of package delivery.

Integration must give its sole desktop worker the qualified output's absolute
`bin/weasel-computer-use-indicator` path and verify that exact executable. A
different `command -v` result still identifies the old installed package and
must be reported as such. Before input, the worker must observe a real READY
event on the selected output using the current desktop skill. Fixture success
alone does not establish READY, rendering, input readiness or permission to
clear a physical Escape/explicit takeover. Keep the existing package path for
rollback; selecting another indicator binary must never restart or resume the
actor. End the owned helper normally before any binary selection change.

Primary API references:
[GTK layer-shell](https://github.com/wmww/gtk-layer-shell),
[layer-shell API](https://wmww.github.io/gtk-layer-shell/),
[GTK input shape](https://docs.gtk.org/gtk3/method.Widget.input_shape_combine_region.html).
GTK3 layer-shell is maintained; it was selected to reuse this laptop's available
small presentation stack. A future Rust/voice application can replace this
renderer while preserving the task/lease boundary.

The all-display helper does not authenticate T3 thread/run/turn identities or
provide an external dispatch permit. Its aggregate presentation READY must be
joined to the shared actor/host control contract before advertising cross-adapter
control readiness. Existing actor lifecycle revision 3 alone does not implement
that contract. The maximum presentation lifetime and heartbeat timeout only end
presentation; they never authorize resume or clear a stop.
