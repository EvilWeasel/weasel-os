# Jarvis typed desktop launch

Source-only feature branch `jarvis/typed-desktop-launch`, bound worktree
`/home/evilweasel/.mt/worktrees/weasel-os/jarvis-typed-desktop-launch`.
Fetched baseline: `73e953ad44387d51b1f0b38422e8c5fff5614a76`.
Actor last modification: `8b6a1bd`; original `main.rs` SHA-256:
`ebfbb93f0971ad3ecc266b4ee0466b226fbf89969f9f41aac0306663d02f0126`.

Owned source: `packages/computer-use/core/src/main.rs`, new sibling `launch.rs`,
focused inline tests, this handoff directory; one final append-only learning.
No Nix, manifest, lock, Jarvis repository or unrelated settings edits.

## Host wire contract

Use ordinary existing stdio MCP `desktop_act`, not a separate tool/daemon.
Its `actions.items.anyOf` advertises these closed, standalone tagged objects:

```json
{"kind":"launch_app","app":"zed"}
{"kind":"launch_app","app":"chrome"}
{"kind":"editor_open_project","project":"jarvis"}
{"kind":"editor_open_file","project":"jarvis","relative_path":"README.md"}
```

Every object rejects unknown fields. File paths are 1..4096 UTF-8 bytes, existing
regular files, relative to the exact canonical
`/home/evilweasel/source/personal/jarvis`; reject empty components, dot/dot-dot,
absolute paths, NUL, backslash, colon/position syntax and symlink escape. Recheck
containment at the spawn boundary. There is no caller executable, argv, shell,
environment, profile or root parameter.

Submit exactly one action with a retained fresh `observation_id` and `task_id`.
Optional top-level `window_id` must match retained focus. Actor result metadata
contains `task_id`, `observation_id`, and `accepted_actions` (the exact accepted
objects). Correlation is required before recording a Host result.

`desktop_status.desktop_launch` and
`desktop_observe.capabilities.desktop_launch` advertise revision 1, pin
presence, output allowlist and isolation/receipt limits. The action union in
`tools/list` remains the authoritative schema. Old actors reject unknown action
variants; new frontend advertisement alone is not installed actor availability.

## Execution and receipts

Launch participates in the existing shared serialized actor, retained observation,
60-second age, epoch, client cancellation, generation, released physical controls
and Escape takeover checks. Require a ready physical monitor and observed focused
active workspace on DP-6/eDP-1, current focus identity and output geometry.
The actor reconstructs fixed arguments, creates a new private mode-0700 profile
exclusively, and rechecks immediately before the bounded-command spawn syscall.
No status-then-external-spawn path exists.

`effects[].details.spawn` distinguishes no spawn (`spawn_committed=false`), OS
spawn committed (PID retained), and spawn ACK (`spawn_acknowledged=true`).
`verification_required=true` after any committed spawn. Errors after commit are
uncertain; no automatic retry. ACK only attests OS spawn, not app readiness,
window/output placement or opened project/file. Cancellation caught immediately
after spawn kills only that new owned process group; later Escape prevents future
actor actions and does not automatically terminate apps. The usual non-atomic
physical-event/spawn collision limit remains; no policy framework was added.

Post-focus/post-launch automatic observation checks DP-6/eDP-1 and focus/output
mapping before capture; DP-5 is not captured by that result path. A changed or
protected output produces `after_observation_error`, not automatic redirection.
ASUS/ROG DP-5, YouTube, Alarm and existing user app profiles/windows are reserved.

## Pinned isolation

Zed 1.22.0 uses exact installed CLI and app Store paths, `--zed`, `--foreground`,
`--new`, and a fresh `--user-data-dir`. Upstream [v1.22.0 CLI source](https://github.com/zed-industries/zed/blob/v1.22.0/crates/cli/src/main.rs)
confirms the private data-dir socket namespace and foreground app invocation;
[paths source](https://github.com/zed-industries/zed/blob/v1.22.0/crates/paths/src/paths.rs)
confirms a separate config namespace. [CLI reference](https://zed.dev/docs/reference/cli)
documents the new-workspace and custom-directory options.

Chrome 155.0.8059.39 uses its exact installed Store wrapper,
`--user-data-dir=<new-private-directory> --new-window --no-first-run
--no-default-browser-check about:blank`. Chromium's [user-data directory documentation](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/user_data_dir.md)
describes profile separation. Actor-created paths never select the user profile.
Absent pins or an unprovable private parent/exclusive directory return capability
unavailable. Fixed child environment removals preserve graphical-session variables.
Committed profiles remain for deliberate owned-app verification/cleanup; this
feature does not delete running profiles or operate on reserved windows.

## Evidence and remaining gates

Device-free test source covers typed/schema agreement, fake pre/postcommit
barriers, queue stop/client cancel, stale epoch/generation/observation/focus,
held/unreleased controls, protected output, private profile exclusivity,
file traversal/symlink escape and preservation of reserved identities.

Initial source pin: `git diff --check` passed. Cargo, Nix evaluation/build and
runtime validation have NOT run at this source pin. Request the single heavy-host
reservation from Jarvis Integration after signing, fresh resource evidence,
maximum jobs 2. Run the focused tests and exact affected-laptop eval/build once;
inspect uncached dependencies before building. Independent Root review and checks
precede auto-merge through a linked feature PR, never a direct main push.

Installed runtime remains unavailable/unqualified for these new actions until the
reviewed build is deliberately deployed and inspected. This thread must not run
GUI, capture, input, microphone, activation/reboot/service or takeover-marker
changes through 04:00 UTC or actual merge. Physical Escape is active and must
never be cleared by this thread. No runtime success is claimed from source or
fake executor evidence.
