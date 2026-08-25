# Hephaestus CX43 migration: human recovery and rollback runbook

Status: staged procedure; it does not create cloud authority or prove that the
laptop console, iris broker, token, SSH path, overlays, backups, or cloud state
currently exist. Recovery owner: Tobi. The laptop is a human console; the
proposed iris one-shot broker is the only possible independent controller while
hephaestus is down.

This runbook applies to exactly Hetzner server ID `162472190` (`hephaestus`) in
`nbg1`, changing `cpx22` to `cx43` while retaining its exactly 80 GB disk. The
only permitted type rollback is `cx43` to `cpx22`, also retaining the disk. No
other server, location, disk option, power action, or configuration change is
in scope.

## 0. Non-negotiable control plane

- Every cloud mutation needs a separate, fresh, one-time Tobi approval bound to
  its canonical request SHA-256. An approval expires in at most 15 minutes; the
  run envelope and pinned controller artifact expire in at most two hours.
- The broker must have one exclusive lock spanning status reconciliation and
  mutation submission. It journals intent before submission and the exact action
  ID after submission. It polls **only that action ID**.
- Use the fixed broker protocol only: `status`, `shutdown`, `poweron`, and
  `change_type`. Never give Codex a Hetzner token. Never use a project token,
  cloud-console retry, direct CLI command, or second runner as an implicit
  fallback while an action may be active or unknown.
- Both type transitions must encode JSON `"upgrade_disk": false` (the API
  equivalent of `hcloud --keep-disk`). A missing field, string `"false"`, or
  `true` is a hard stop. Snapshots, rescue mode, rebuild, volume/network/
  firewall/IP/DNS/ACL/key changes, and server creation/deletion are outside the
  fixed protocol.
- Preserve NetBird and Tailscale independently. A broken overlay is not proof
  of an Internet/provider outage. Factorio UDP `34197` remains the only
  intentional public listener.
- Record only UTC time, operator, request/approval IDs, request hash, action ID,
  terminal result class, redacted error code, boot ID, checksums, and health-gate
  results in the native Work/Kanban task. Do not record token material, raw API
  responses, auth files, private keys, logs, save contents, or chat/memory data.

## 1. Source of truth and evidence packet

Before approving any mutation, place a sanitized evidence packet in the current
Kanban task. It must identify the exact Git revisions/checksums, but never copy
secrets.

| Domain | Source of truth / evidence |
| --- | --- |
| Fixed migration contract | `README.md` §§ "CX43 fixed contract and health gates" and `skills/cx43-rescale-safety.md` |
| Broker protocol and request shape | `iris-broker/README.md`, `iris-broker/validate-request.py`, `CAPABILITY-HANDLES-DESIGN.md` Handle H3 |
| Sanitized availability caveats | `RECOVERY-SOURCE-MANIFEST.md` |
| Hephaestus durable configuration | `/srv/hermes/admin/ansible/site.yml`, `inventory.yml`, and affected role sources; apply only through `hermes-host-admin-request` |
| Gateway LKG/watchdog | `roles/hermes_gateway/files/hermes-gateway-rescue-runbook.md` and `roles/hermes_gateway/files/hermes_gateway_watchdog.py` |
| Factorio backup proof | `roles/factorio_backup/tasks/main.yml`; current restore proof must meet that role's assertions |
| Work record | current native Kanban task/run; no parallel ledger |

The packet is valid only if all are true:

1. The proposed iris broker deployment has passed its fake-API/fake-SSH tests,
   including rejection of arbitrary commands, wrong IDs, stale/duplicate
   approvals, active-action/lock races, token-readable paths, and both
   `upgrade_disk=false` type transitions.
2. The broker reports a pinned artifact hash and a valid <=2 hour envelope.
   The forced-command key has no shell, PTY, forwarding, or token read path.
3. A status response for numeric server ID `162472190` establishes unchanged
   expected name/location (`hephaestus`/`nbg1`), source type `cpx22`, 80 GB
   disk, expected IP/firewall identifiers and rules, unlocked state, and no
   active Hetzner action. Any mismatch is indeterminate; do not normalize it.
4. A pre-change LKG exists and its checksum manifest verifies. Gateway recovery
   status is collected, not assumed. A missing or checksum-failed LKG blocks the
   migration.
5. The latest Factorio backup proof has `restore_verification == "passed"`, a
   `world-YYYYMMDDTHHMMSSZ` directory, `world.zip`, `SHA256SUMS`, `level.dat`,
   positive restored file count, and a 64-character lowercase SHA-256. The
   checksum check must pass. If this evidence is unavailable, stop; this runbook
   does not create snapshots or backups as a shortcut.
6. Read-only baselines are captured: current boot ID; `systemctl` state and
   `NRestarts` for gateway, recovery controller, Voice, Factorio, and watchdog;
   root backing device; disk size; CPU/memory; failed units; filesystem/root
   device/OOM evidence; host route/address/nftables hashes; overlay identities;
   and five-minute service/overlay samples described below.

Safe local/offline gateway inspection, including during DNS, Internet, Discord,
or Hermes CLI outage:

```bash
systemctl status hermes-gateway.service hermes-gateway-watchdog.timer
/usr/local/libexec/hermes-gateway-watchdog status
journalctl -u hermes-gateway-watchdog.service -u hermes-gateway.service -n 120 --no-pager
```

Expected: `status` returns secret-free JSON with local health, LKG/pending
checksum state, bounded recovery budget, and minimal incident metadata. A
locally healthy gateway remains healthy during DNS or Internet failure; do not
restart it merely because an upstream probe fails.

## 2. Read-only diagnosis decision tree

These steps never authorize a mutation.

1. **Cloud status first.** Through the broker's authenticated `status` operation,
   read the fixed server only. If there is an active action, lock, unknown action
   state, provider timeout, or journal failure, make the broker observation-only.
   Preserve the known IDs; wait for the exact action's terminal state or use the
   Hetzner console/support with Tobi. Do not issue power, rescale, or rollback.
2. **Overlay split.** From iris, probe hephaestus twice through NetBird and twice
   through Tailscale using the pinned recovery SSH alias/host-key policy. A
   failure on exactly one path is that overlay's failure domain, not reason to
   change cloud state or fall back to a public route. Failure of both paths plus
   a healthy cloud state is still an access diagnosis, not rescale evidence.
3. **Host split.** Over an approved overlay path, collect the baseline commands
   below. A local application failure with normal OS/disk/network evidence is a
   service recovery problem. Use the watchdog/LKG and audited Ansible rollback,
   not a server-type rollback.
4. **Provider/control-plane split.** If cloud `status` is unavailable, do not
   guess action state. Preserve the last journal record and have Tobi use the
   Hetzner console/support to reconcile the exact action ID. No second client
   may submit a change.

Suggested read-only host collection (capture redacted outputs/checksums, not
secret-bearing logs):

```bash
cat /proc/sys/kernel/random/boot_id
nproc
awk '/MemTotal/ {print}' /proc/meminfo
findmnt -no SOURCE /
findmnt -bno SIZE /
systemctl --failed
systemctl show hermes-gateway.service factorio.service --property=ActiveState --property=SubState --property=MainPID --property=NRestarts --value
ss -H -u -l -n -p
```

The exact service-unit names for recovery controller and Voice are taken from
the reviewed Ansible role at execution time; do not invent names. Expected
baseline: the gateway and Factorio are `active`/`running`, a positive main PID,
and no increment in `NRestarts` across their liveness window. `ss` must show no
new public listener; only the existing Factorio UDP 34197 exposure is allowed.
`systemctl --failed` must be empty or contain only an explicitly pre-existing,
reviewed exception. Any new failure, root-device/filesystem error, or OOM is
indeterminate—not a type rollback trigger.

## 3. Preflight gates and approval checkpoint: CX43 change

Before the **CX43 `change_type` mutation**, Tobi must explicitly approve this
exact statement after reviewing the evidence packet:

> Effect: gracefully stop hephaestus and change only server `162472190` from
> `cpx22` to `cx43`, retaining its 80 GB disk with `upgrade_disk=false`.
> Risks: temporary service/management outage; an unknown provider action,
> boot/access failure, or broader-than-expected credential blast radius.
> Rollback: do not automatically reverse anything. Only an intact post-boot
> gate exit `20` permits one separately approved `cpx22` change with the same
> keep-disk constraint. All other failures remain observation-only and go to
> Tobi/Hetzner support.

The approval must bind the canonical JSON request hash, server ID, source and
target type, `upgrade_disk:false`, bounded time window, broker artifact hash,
and current action/journal state. Expected local fixture validation is:

```text
ACCEPT request_sha256=<64 lowercase hex characters>
```

A `REJECT ...` result, changed hash, expired approval, invalid clock, absent
approval, different server/type, or any action/lock is a stop condition.

Preflight health gate, all required before shutdown:

- Five one-minute samples show both NetBird and Tailscale `active`, the same
  identity each sample, and fresh iris probes through **each** overlay. Never
  use a public fallback.
- Five one-minute samples show gateway, recovery controller, Voice, and
  Factorio active/enabled with no new `NRestarts`; only pre-provisioned,
  non-destructive Discord/Voice/Work fixtures may be used.
- Ansible source is clean/reviewed at the selected revision. Run
  `hermes-host-admin-request check`; it must succeed without a proposed change.
  No `apply` belongs in migration preflight.
- The watchdog/LKG status and backup proof above pass. The current task records
  a recovery owner and independent controller owner.

## 4. Mutation boundary A: graceful shutdown

**Approval checkpoint — separate from rescale:**

> Effect: submit a graceful shutdown for fixed server `162472190` only after
> the preflight gate. Risk: all hosted services and both overlay endpoints become
> unavailable until boot completes. Rollback: no competing power/type action;
> reconcile the exact provider action. A later `poweron` needs its own approval.

Submit exactly one broker `shutdown` request. The broker must journal the
request/approval IDs before it submits and return exactly one action ID. Poll
only that action ID with bounded backoff inside the two-hour envelope. If the
action does not reach terminal state before envelope expiry, cloud connectivity
is lost, lock ownership is lost, or the provider response is ambiguous: stop
mutation, preserve evidence, make the broker read-only, and have Tobi reconcile
via console/support. Do not issue `poweron`, `change_type`, retry, or rescue.

After shutdown completes, re-run broker `status`. Required state: fixed server
ID, expected name/location/IP/firewall identifiers and 80 GB disk unchanged;
server unlocked; no active action. A discrepancy is a stop condition.

## 5. Mutation boundary B: CPX22 to CX43

**Approval checkpoint — separate from shutdown:**

> Effect: change fixed server `162472190` from `cpx22` to `cx43` with
> `upgrade_disk=false`, retaining the existing 80 GB disk. Risk: provider-side
> hardware/boot interruption and capacity change; an incorrect request could
> grow disk or target another resource. Rollback: only the fixed gate exit `20`
> permits one separately approved `cpx22` keep-disk change; otherwise stop and
> reconcile the exact action with Tobi/Hetzner support.

Submit one canonical `change_type` request. It must contain only protocol
version, random request ID, approval ID, fixed server ID, operation, valid
RFC3339 `not_before`/`expires_at`, `server_type:"cx43"`, and
`upgrade_disk:false`. Validate locally, confirm its hash equals Tobi's approval,
then submit once. The expected desired terminal cloud state is `cx43`, 8 vCPU,
16 GB RAM, 80 GB disk, unlocked, no active action. Provider terminal success
alone is not acceptance.

The same timeout/unknown-action stop conditions as boundary A apply. Do not
power on until the exact type action is terminal, status is unlocked, and no
other action is active.

## 6. Mutation boundary C: power on

**Approval checkpoint — separate from type change:**

> Effect: power on only fixed server `162472190` after a completed CX43 action.
> Risk: services may fail during boot or return in a degraded state; premature
> power control can race provider actions. Rollback: do not power-cycle or type
> change automatically. Observe the exact action and run the declared health
> gate; only exit `20` can request the separately approved type rollback.

Submit a single broker `poweron` request only after status shows no active
action and no lock. Record/poll its exact action ID as above. Perform two SSH
probes from iris after cloud state reports running. If either probe fails, wait
only within the two-hour envelope while reading exact action/server state; do
not submit another power operation. When both succeed, capture a new boot ID and
wait five minutes. The boot ID must remain unchanged during that interval.

## 7. Fixed post-boot health gate (exit 0, 20, or indeterminate)

Run this gate from the independent controller using read-only commands and
pre-provisioned non-destructive fixtures. It must not call Hetzner. Each sample
is timestamped in UTC and compared to the preflight baseline.

| Domain | Exact acceptance requirement | Failure classification |
| --- | --- | --- |
| Cloud/OS | `running`, unlocked `cx43`, 80 GB disk, no active action; two iris SSH probes; one stable new boot ID for 5 minutes; no new failed unit, filesystem/root-device error, or OOM | CPU/memory mismatch or type-correlated boot failure may be candidate exit 20; all other failures indeterminate |
| Capacity | Three samples across 5 minutes: exactly 8 CPUs; `MemTotal` 15,000,000–17,000,000 KiB; root backing device 79.5–80.5 GiB and stable; cloud disk exactly 80 GB | Only persistent exact CPU/memory mismatch may be candidate exit 20; disk/root mismatch is indeterminate |
| Network | Server ID/name/location, stable IPs, firewall IDs/rules, route/address/nftables hashes unchanged; no listener except existing Factorio UDP 34197 | Indeterminate |
| Overlays | Five one-minute samples: both overlay services active with identical identities; fresh iris probe through each overlay each minute | Indeterminate |
| Services | Five one-minute samples: gateway, recovery controller, Voice, Factorio active/enabled, no new restart; non-destructive Discord/Voice/Work fixtures pass | Indeterminate |
| Stability | Fixed benchmark completes; no new OOM/restart; mean CPU steal <=1%, no sample >5%; normalized load <=0.75; then `hermes-host-admin-request check` succeeds with zero drift and lightweight reads still pass after 5 minutes | Indeterminate |

Exit rules are deliberately narrow:

- **Exit 0 — accept CX43:** every table row passes. Finalize post-change
  verification and revoke the one-shot recovery capability.
- **Exit 20 — rollback eligible, not automatic:** only a persistent exact
  CPU/memory capacity mismatch or a clearly type-correlated boot failure, while
  disk/root identity, server/network/firewall invariants, action state, envelope,
  journal, and approval evidence are intact. Tobi must separately approve the
  rollback mutation below.
- **Any other result — indeterminate:** overlay failure, IP/firewall change,
  disk/root issue, fixture failure, performance/drift issue, failed checksum,
  provider ambiguity, missing evidence, timeout, or any new OS/service failure.
  Preserve evidence and escalate. No rollback or retry.

## 8. Rollback sequencing (only after exit 20)

**Approval checkpoint — CPX22 rollback:**

> Effect: change fixed server `162472190` from `cx43` back to `cpx22` with
> `upgrade_disk=false`, retaining the 80 GB disk, because the declared gate
> returned exit `20` for `<recorded reason>`.
> Risks: another planned outage and reduced capacity; a wrong action could alter
> disk or resource state. Rollback: this is the final bounded cloud reversal;
> do not submit additional power/type actions if it is ambiguous. Reconcile the
> exact action with Tobi/Hetzner support and use the Ansible/LKG service path
> only after stable host access returns.

1. Reconcile broker `status`: server ID/name/location/IP/firewall/disk
   invariants match, no action is active, server is unlocked, the journal is
   intact, and the original exit-20 evidence is attached to the approval.
2. Submit exactly one validated `change_type` request with
   `server_type:"cpx22"` and `upgrade_disk:false`; record and poll only its
   returned action ID within the existing envelope.
3. If the server is not running after terminal type success, obtain a **new,
   separate** power-on approval using the boundary-C statement with `cpx22`
   substituted. Never submit it while an action/lock exists.
4. Re-run the complete read-only post-boot gate, except expected capacity is
   the documented CPX22 baseline captured during preflight. Confirm disk/root,
   identity, IP/firewall, both overlays, services, fixtures, no restarts, LKG,
   and broker zero drift. A healthy rollback is not proved by a PID alone.
5. If rollback is indeterminate or unhealthy, stop cloud mutations. Preserve
   action IDs and sanitized evidence; Tobi owns console/support escalation.

## 9. Service-specific recovery after access returns

Cloud type rollback is not the repair path for a localized service failure.
After host reachability and the migration gate are stable:

- **Gateway/dashboard:** consult the local offline rescue plane. Its only
  application probe is `http://127.0.0.1:8642/health`; it neither depends on DNS
  nor Internet. It permits at most three ordinary recoveries with cooldown and
  fails closed on LKG checksum failure. Do not edit watchdog state or invoke
  abort speculatively. A candidate rollback restores the immediate verified
  pre-activation snapshot, not an arbitrary old release.
- **Ansible-managed state:** make any durable repair as a reviewed Ansible change
  at `/srv/hermes/admin/ansible`; review and commit it, run
  `hermes-host-admin-request check`, state effect/risk/rollback and obtain Tobi
  approval, run `apply`, then immediately run `check` again for zero drift.
  Direct `sudo`, `systemctl`, or `/etc` edits are not a durable repair path.
- **Factorio:** do not assume a backup is usable. Use the role's restore-proof
  criteria and checksum verifier; verify `factorio.service` is active after a
  backup. Restore requires a separate destructive-data approval and its own
  Factorio restore runbook, not this rescale procedure.
- **Voice/Work fixtures:** use only existing non-destructive fixtures. Missing
  credentials, a failed fixture, or Discord/provider outage is indeterminate;
  do not alter secrets, ACLs, network, or cloud state to make a probe pass.

## 10. Offline, no-Codex, and no-broker recovery

- **Codex absent/unavailable:** the human operates this static runbook. Do not
  install packages, bootstrap a CLI, expose auth material, or treat a model as
  the approval authority. The staged console's `--dry-run` and smoke test are
  local context checks, not infrastructure health.
- **Both overlays unavailable:** preserve local Git revision, LKG checksum
  manifest, action/journal IDs, and last known cloud status. Do not enroll a
  peer, change routes/firewalls, or use workplace paths. Tobi uses Hetzner
  console/support for read-only reconciliation of the exact action.
- **Broker unavailable or its token/socket/journal/lock is unhealthy:** all
  mutations fail closed. Do not move a token to the laptop, inspect it, or use a
  broad project credential. Tobi may request provider support; no retry is safe
  until action state is independently known.
- **No network/control plane:** distinguish it from local host failure with the
  offline watchdog commands. A locally healthy gateway remains healthy; preserve
  evidence and wait/escalate rather than restart-flap.
- **Need a rescue environment/snapshot:** this protocol cannot request one.
  State the exact proposed provider action, risk (outage/data/access impact),
  rollback/irreversibility, and obtain a fresh Tobi approval before any
  out-of-contract console action.

## 11. Closeout and revocation

Acceptance ends only after the exit-0 gate and a final five-minute lightweight
read pass. Then, in this order:

1. Save sanitized pre/post evidence and exact action IDs/checksums to the
   native Kanban task; state whether CX43 was accepted or CPX22 restored.
2. Disable/remove the iris forced-command key, socket, and one-shot broker unit
   through reviewed configuration. Delete the temporary mode-0600 token and
   revoke it at Hetzner; verify the old token is rejected. Tobi owns this step.
3. Confirm the recovery SSH account can no longer invoke the broker and that no
   service/unit/listener or public exposure was added.
4. Retain only the sanitized append-only journal and checksum evidence. Do not
   retain access tokens, approval material, raw cloud response bodies, or
   credential-bearing logs.

If revocation evidence is missing, the migration is not closed. This is dull by
design: the exciting version of a resize runbook is called an incident report.
