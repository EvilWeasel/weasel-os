# Task-owned Computer Use monitor indicator

This is presentation beside the Rust desktop actor. A small C/GTK3 renderer uses
the already available GTK layer-shell library; it contains no screenshot,
accessibility, focus, input, model, API or credential code. The Python standard
library helper owns its lifetime and reads actor status. GTK is isolated here so
the Rust capture/input core does not gain a GTK dependency or another Cargo tree.

The indicator has four solid blue 4-logical-pixel edge surfaces and a compact top
label: **Computer Use · Esc zum Abbrechen**. All five surfaces request the overlay
layer, explicitly disable keyboard focus, use empty input regions, and reserve no
workspace. They target one explicitly selected output, including full-screen
windows. The intended live target on this laptop is `DP-6`; the user's T3 monitor
is not automatically selected.

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
`$XDG_RUNTIME_DIR/weasel-computer-use/indicators`. One indicator owner per output
is enforced. An existing task identity is never silently replaced. Metadata
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
for the lifetime. Its GDK monitor must match that rectangle uniquely; there is no
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

The helper polls `desktop_status` on a bounded 100 ms cadence with a 300 ms socket
deadline. It pins initial actor `session_id` and cancel `epoch`, and ends on epoch
or backend session change, takeover latch, idle unconfirmed release, unavailable
status, owner PID/starttime change, explicit end, stdin EOF (when requested),
SIGTERM/SIGINT/SIGHUP, target output/layout change, or a hard maximum of 20 minutes.
Active actions may legitimately have unconfirmed release; that transient state
does not hide the indicator. There is no automatic reconnect, resume, replay or
renewal beyond the hard runtime bound. Shorter bounds can be requested with
`--max-runtime-seconds 1..1200`.

Actor status and output queries are read-only. Raw status, window titles,
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
expiry and one output's competing ownership. They are helper lifecycle tests.
Root must still prove the real monitor rendering, click-through and task Stop
including a model-thinking gap from ordinary T3/Codex sessions.

Primary API references:
[GTK layer-shell](https://github.com/wmww/gtk-layer-shell),
[layer-shell API](https://wmww.github.io/gtk-layer-shell/),
[GTK input shape](https://docs.gtk.org/gtk3/method.Widget.input_shape_combine_region.html).
GTK3 layer-shell is maintained; it was selected to reuse this laptop's available
small presentation stack. A future Rust/voice application can replace this
renderer while preserving the task/lease boundary.
