# Human-invoked Codex recovery console for hephaestus

Status: staged for review. It is not enabled, installed, authenticated, granted
SSH access, enrolled in NetBird, or allowed to modify Hetzner. The recovery
owner is Tobi; the external CX43 controller owner is the future `iris` one-shot
runner, after its separate approvals.

## What this is

A small versioned prompt/runbook repository installed declaratively on
`nixy-laptop` only after `weasel.hephaestusRecoveryConsole.enable = true` is
reviewed and switched. It uses `pkgs.codex` from the existing flake lock, not a
curl/npm bootstrap. Existing mode-0600 Codex CLI auth/config are checked only
for existence and permissions by the smoke test; neither their paths' contents
nor values are copied into this repository.

The bundle deliberately contains no credentials, private keys, SSH host-key
material, NetBird setup key, Discord/Cloudflare data, raw Hermes memory, chats,
or unrelated personal files. It cannot create authority by documentation.

`SANITIZATION.md` is the contribution boundary and denylist; its offline checker
is `bin/verify-sanitized-tree`. `CONTRIBUTING.md` restates the approval and
redaction rules for reviewers. The launcher-loaded
`CODEX-OPERATING-CONTRACT.md` is the accepted instruction contract for this
staged bundle; the protected standard `AGENTS.md` path is deliberately not
bypassed. `PACKAGE-REVIEW.md` is the integrated review decision, residual-risk
register, activation gate, expiry/audit schedule, offline fallback, rollback,
and credential-revocation procedure.

## Activation gate — not performed by this task

Before enabling the Home Manager module, Tobi must review the exact effect:
install the locked `codex`, `git`, and `ssh` client packages and deploy this
read-only bundle at `~/recovery/hephaestus-codex`.

Risk: the locally authenticated Codex CLI can send the reviewed recovery context
to its configured provider; a compromised or overbroad prompt could cause unsafe
commands. `bin/codex-recovery --start` explicitly presents and supplies
`CODEX-OPERATING-CONTRACT.md` plus the selected sanitized skills as Codex's
initial context, but that is not a security boundary. No network identity,
credential, or service changes occur during activation.

Rollback: set the option back to `false` and switch the laptop generation; then
remove `~/recovery/hephaestus-codex` if Home Manager leaves the old managed path.
Codex auth remains untouched. Verify rollback with `command -v codex` and
`readlink ~/recovery/hephaestus-codex` from a fresh login.

## Expected architecture and service map

- `nixy-laptop`: human console only; it may sleep or lose connectivity and is
  never the autonomous CX43 controller.
- `hephaestus` (Hetzner server ID `162472190`): Hermes messaging gateway,
  recovery controller, Discord Voice runtime, Factorio, and the audited local
  Ansible broker. Factorio is the only intentional public application and must
  retain UDP `34197` without new public listeners.
- `iris` (Hetzner server ID `163123673`): proposed independent one-shot CX43
  controller. It survives a hephaestus shutdown and uses an existing pinned
  `aidan` SSH path; it is not an automatic recovery system.
- NetBird and Tailscale coexist. Both are management/recovery overlays until
  NetBird is independently healthy. A failure on one is not evidence that the
  other or the public Internet has failed. Do not alter their ACLs, firewall, or
  routes from this console.
- Work/Kanban is native Hermes state. Capture the current task/run and concise
  redacted status, not an invented parallel ledger.

## Offline and degraded-mode procedure

1. Do not improvise credentials, enroll a new mesh peer, disable firewalls, or
   use workplace routes.
2. Preserve the last known-good recovery bundle, its checksum manifest, and the
   current local Git revision. Use the runbook and console/provider support path
   as the human fallback when both overlays are unavailable.
3. If `hephaestus` is unreachable but `iris` is available, the future fixed
   controller may only observe an already-recorded action ID. It must not submit
   a competing power/change action while the server is locked or an action runs.
4. If the cloud console is the last path, Tobi performs console/support actions.
   Codex cannot treat a vague outage as permission for a rescale or rollback.

## CX43 fixed contract and health gates

The target is server `162472190` (`hephaestus`), `cpx22` to `cx43` in `nbg1`,
with x86/local storage and exactly 80 GB retained by API
`upgrade_disk=false` (`hcloud --keep-disk`). The target capacity is exactly
8 vCPU and 16 GB RAM. Any runner must use numeric IDs, a two-hour envelope,
exclusive lock, append-only sanitized journal, graceful shutdown, bounded
polling of the exact action ID, and one safe power-on only when no action is
active and the server is unlocked.

The post-boot gate is fixed: exit `0` = accept CX43; exit `20` = only then a
bounded CPX22 rollback with `upgrade_disk=false`; every other exit =
indeterminate, read-only observation and human escalation. It must reject a
missing/expired/hash-mismatched baseline and never call Hetzner itself.

Acceptance requires all of these bounded domains:

1. Cloud/OS: running/unlocked cx43, 80 GB disk, no active action; two SSH probes
   from iris; stable new boot ID for five minutes; no new failed unit, filesystem
   error, root-device error, or OOM.
2. Capacity: three samples over five minutes show 8 CPUs, 15,000,000–17,000,000
   KiB MemTotal, 79.5–80.5 GiB stable root backing device, and Cloud disk 80 GB.
3. Network: unchanged server ID/name/location, stable IPs, firewall IDs/rules,
   host route/address/nftables hashes, and only the existing Factorio UDP 34197
   listener.
4. Overlays: five one-minute samples of active, same-identity NetBird and
   Tailscale plus fresh iris probes through each overlay, never public fallback.
5. Services: gateway, recovery controller, Voice, and Factorio active/enabled
   and stable for five one-minute samples; only pre-provisioned non-destructive
   Discord/Voice/Work fixtures are valid.
6. Stability: fixed benchmark, no new OOM/restarts, mean CPU steal <=1% with no
   sample >5%, normalized load <=0.75, then audited Ansible broker `check` with
   zero drift and repeated lightweight health reads after five minutes.

Only a persistent exact CPU/memory capacity mismatch or a type-correlated boot
failure may produce exit 20, and only if disk/root identity, network/firewall,
server state, envelope, and journal invariants match. Disk, IP/firewall,
overlay, fixture, performance, or drift problems are indeterminate. Boring is
correct here; live migrations dislike improv.

## Smoke test

After activation, from `~/recovery/hephaestus-codex` run:

    ./bin/smoke-test

It checks the directory is a Git worktree, the operating contract and selected
skills are present, and `bin/codex-recovery --dry-run` renders their exact
effective context. It then checks Codex is installed, any existing auth/config
files are mode 0600 without reading them, and the approved
`hephaestus-netbird` SSH alias resolves with strict host-key checking. It does
not contact a host, invoke Codex against a provider, read credentials, or make
a change.

Before a review or activation decision, run the offline bundle guard as well:

    ./bin/verify-sanitized-tree
    ./bin/verify-document-links
    ./bin/review-smoke-test

It rejects denylisted paths and common secret-like material without printing
candidate contents. The link checker validates relative Markdown targets
offline. The review smoke test exercises synthetic accepted and denied requests
against the local validator; none of these commands inspect provider-managed
auth/config files or contact a provider.

To open the human-invoked console after the smoke test:

    ./bin/codex-recovery --start

The launcher first writes the exact operating contract and selected sanitized
skills to the terminal, then passes that same immutable bundle context as the
initial prompt to Codex. `--dry-run` is the safe deterministic context test;
`--print-context` renders only the context for review.

## Credential revocation

1. Disable the module and switch/roll back the laptop generation; verify the
   console bundle is gone or unlinked.
2. Revoke Codex CLI authorization only through its official interactive logout
   on the laptop. Do not print or edit auth-file contents; remove only the
   provider-managed auth state after Tobi confirms the impact.
3. For a future CX43 run, delete the mode-0600 temporary token from `iris`,
   revoke it in Hetzner, and verify that the old token no longer authenticates.
   Do not substitute the root-protected project token or move it to the laptop.
4. Preserve the sanitized journal, checksums, action IDs, and result in the
   native Work/Kanban task; do not preserve secret values.
