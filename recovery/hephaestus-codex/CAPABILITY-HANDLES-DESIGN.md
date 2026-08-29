# Recovery capability handles — security design

Status: **staged design only**. This document provisions nothing: no credentials,
SSH keys/accounts, NetBird/Tailscale ACLs, services, sockets, token files, or
Hetzner changes. Every implementation and activation action below is blocked
pending Tobi's exact approval after review of its effect, risk, and rollback.

## Operational truth

Recovery owner: **Tobi**. Codex on `nixy-laptop` is a human-invoked,
unprivileged assistant, never an autonomous controller. `hephaestus` may be the
failed system, so it cannot be the sole recovery authority. `iris` is proposed
as the independent one-shot cloud-control broker. The existing project-wide
Hetzner token remains root-protected and must never become readable by Codex,
the recovery SSH account, its processes, logs, environment, Git checkout, or
socket responses.

A capability handle is a fixed protocol with less authority than its backing
system. It is not a claim that the backing identity is narrowly scoped. If the
provider token can do more than the protocol, containment depends on the broker
host, dedicated service principal, fixed client, and fail-closed validation.
That residual risk must be accepted explicitly before activation.

## Common invariants

All handles share these properties:

- Default deny: unknown commands, fields, peers, identities, expired material,
  malformed input, unavailable audit storage, missing locks, and ambiguous
  provider results fail closed with a non-zero status and sanitized reason.
- No handle shells out from user-provided text, follows user-provided URLs,
  accepts a hostname/server ID/token path, or returns secrets or raw provider
  responses.
- Every mutating request needs a one-time approval produced outside Codex and
  bound to principal, exact canonical request hash, action, target, not-before,
  expiry, and intended effect. The broker atomically consumes it before the
  external call. An approval expires after 15 minutes; its request envelope and
  pinned controller-artifact hash expire after two hours.
- A durable, append-only, sanitized audit record contains UTC time, handle
  version, caller key fingerprint/principal, request ID/hash, approval ID,
  fixed target, outcome class, provider action ID (when present), and redacted
  error class. It contains no token, request payload beyond fixed fields, shell
  command, or raw HTTP response. The audit sink must be writable before an
  action starts; failure is denial, not a reason to operate quietly.
- The action lock is held from approval consumption until a terminal outcome is
  journaled. A startup recovery reconciles the exact outstanding provider action
  ID read-only before accepting another mutation. There is no retry loop for
  power/type changes.
- All handles are independently rate limited and log denials. Repeated denial
  is an incident signal, not an invitation to loosen validation.

## Handle H1: normal overlay SSH diagnosis

Purpose: diagnose `hephaestus` through already approved private overlays; this
is not an SSH-management capability.

Proposed caller: a recovery-console principal using only the existing strict
host-key alias `hephaestus-netbird`, with Tailscale used separately only through
an already declared strict alias. The console never supplies an address, user,
identity file, proxy command, `StrictHostKeyChecking` override, or SSH option.

Allowed effect:

| Class | Exact operation | Effect |
| --- | --- | --- |
| Read-only diagnosis | fixed, reviewed diagnostic command set or an interactive human SSH session under the existing account policy | reads service/network/overlay health needed to classify local vs overlay/provider failure |
| Explicitly absent | SSH config/key changes, account changes, package/service actions, firewall/DNS/ACL/route changes, port forwarding, file transfer, agent/X11 forwarding | denied |

The preferred implementation is a documented read-only command allowlist for
routine diagnostics (`systemctl` inspection, journal reads, overlay status,
filesystem/memory/boot evidence), each with fixed arguments and output caps.
If an interactive session remains necessary, it is a human session outside
Codex automation, using the same existing least-privilege account; Codex must
not be given a new key or an unrestricted SSH execution bridge.

Precondition: identify the failure domain with at least two observations (for
example, an iris probe over NetBird and independently over Tailscale). A failed
overlay does not prove a host, Internet, or provider outage. The handle refuses
any write command; diagnosis cannot turn a vague outage into authority to
restart, change routing, or rescale.

Risk and rollback: read access can disclose operational metadata. Limit output,
redact before Kanban, use a dedicated recovery principal if the existing account
is broader than diagnosis, and revoke/remove that principal/key to restore the
prior access boundary. Before activation, Tobi reviews host-key pinning, caller
key fingerprint, exact command list, output redaction/caps, and a denial test
for forwarding and write commands.

## Handle H2: audited `hephaestus` Ansible broker

Purpose: expose declarative, audited **check/diff only** recovery evidence while
preserving the existing Ansible broker as the root-equivalent authority.

The broker has high authority because it can apply Aidan-controlled playbooks.
Codex therefore receives no repository write access, no privileged broker
credential, no direct `sudo`, and no generic command runner. The recovery handle
may invoke only these fixed broker modes against the already committed,
allowlisted local `hephaestus` inventory:

| Handle command | Exact effect | Denial condition |
| --- | --- | --- |
| `ansible-check <pinned-commit>` | run `hermes-host-admin-request check` for a reviewed, clean, signed/approved revision | revision not in allowlist, dirty tree, wrong inventory/host, unreviewed diff, broker busy, or non-zero check |
| `ansible-diff <pinned-commit>` | return a bounded/redacted diff and predicted-change summary for that same revision | as above, or output fails secret/redaction rules |
| `ansible-status` | report broker result metadata and current committed revision only | metadata unavailable or inconsistent |

`apply` is deliberately not a capability command. Any later apply remains a
separate Tobi-approved human operation using the existing broker workflow:
review exact repository diff, commit, `check`, explain effect/risk/rollback,
apply, then independent health checks and zero-drift check. The recovery handle
cannot stage or mutate a Git revision, alter `remote_tmp`, pass extra Ansible
arguments, select other hosts, read secret files, or invoke an arbitrary role or
tags.

Implementation boundary: use a small root-owned broker adapter that accepts a
structured request over a local socket, maps it to constant argv (never a shell),
uses a read-only checked-out worktree or immutable commit object, and runs under
the existing audit path. The adapter verifies the exact repository path,
localhost-only inventory, no uncommitted changes, and allowlisted revision
before requesting a check. It serializes operations with a lock and writes a
sanitized invocation/result digest before and after execution. If the existing
broker cannot support this separation without granting repository writes or
broad root execution, do not activate H2; retain human-only broker use.

Risk and rollback: check/diff may reveal configuration metadata and themselves
exercise read paths. There is no intended host mutation. Disable the adapter
socket/unit and remove its caller key/group through reviewed Ansible to restore
the previous human-only broker boundary. Tobi must approve the exact allowlisted
revisions/commands, redaction schema, service-account permissions, rate limit,
concurrency behavior, and a test proving `apply`, extra args, other inventories,
secret paths, and dirty revisions are refused.

## Handle H3: iris forced-command Hetzner one-shot broker (preferred)

Purpose: independently observe or perform a separately approved CX43 migration
while `hephaestus` is unavailable. The complete staged wire validation is in
`iris-broker/validate-request.py`; this section is the activation contract.

The forced-command SSH key has all interactive and forwarding paths disabled:
`command=` points to a root-owned validator/client, `no-pty`,
`no-agent-forwarding`, `no-port-forwarding`, `no-X11-forwarding`, no
`permitopen`, and no shell. It reads a single bounded JSON request from stdin;
it ignores and never evaluates `SSH_ORIGINAL_COMMAND`. The forced command can
reach only a Unix socket owned by the dedicated broker service. The SSH account
cannot read the token or journal directory.

| Operation | Fixed target/effect | Approval rule |
| --- | --- | --- |
| `status` | read status for server numeric ID `162472190` only | non-mutating; still authenticated, audited, rate limited |
| `poweron` | request power-on for that ID only when no lock/action exists | one-time exact request-hash approval |
| `shutdown` | request graceful shutdown for that ID only when no lock/action exists | one-time exact request-hash approval |
| `change_type` | only `cpx22` or `cx43`; always `upgrade_disk=false` / keep disk | one-time exact request-hash approval; type rollback only after declared health gate exit 20 |

No server creation/deletion, rebuild, rescue, snapshot, image, volume, network,
firewall, load-balancer, SSH-key, placement-group, DNS, pricing, location, IP,
user-data, labels, generic API endpoint, or token operation exists in the
protocol. `change_type` rejects every value except `cpx22` and `cx43` and
requires JSON boolean `false` for `upgrade_disk`. The operation must be a
canonical version-1 request naming exactly server `162472190`, a random request
and approval ID, and the short validity window. Duplicate request/approval IDs
are rejected permanently.

Token alternative and credential boundary:

1. Preferred: Tobi creates a new temporary Hetzner token only if the provider
   documents scope sufficient for this exact target/action set. Store it only in
   a dedicated broker-service secret location, mode 0600, with a root-owned
   parent directory and service confinement that denies the forced-command
   account/Codex any traversal or read path.
2. If Hetzner cannot issue an appropriately narrow token, treat the token as a
   project-wide write credential. Do not copy, mount, proxy, or expose the
   existing project token. A broker may be proposed only as an explicit
   exception after Tobi accepts that the token's provider-side blast radius
   exceeds the handle; defense then relies on a sealed, reviewed iris broker.
3. The broker uses a pinned client artifact/config, pinned API base URL, fixed
   TLS verification, no proxy inherited from caller environment, and a deny-all
   outbound policy except the documented Hetzner API endpoint. It never logs
   request headers or environment.

Concurrency and ambiguous outcomes: a single lock covers status-action
reconciliation and mutation submission. Before power/type operations the broker
checks server ID, expected location/name/IP/firewall/disk invariants, unlocked
state, and no active action. It journals intent, submits once, journals returned
action ID, then polls only that ID with bounded backoff. Timeout, API mismatch,
lock loss, journal failure, lost connectivity, or unknown action state returns
indeterminate; the broker becomes observation-only and tells Tobi to use the
cloud console/support rather than issue a second operation.

Risk and rollback: power and rescale can cause outage; an incorrect type action
can reduce capacity; provider-side token breadth can affect more than intended;
and iris compromise can misuse its service principal. Rollback is not automatic:
only the predeclared post-boot gate exit `20`, with intact disk/network/firewall
invariants, permits one approved `cpx22` change retaining disk. Otherwise stop
at observation. After a one-shot run, disable/remove the forced-command key,
socket and service, delete the temporary token, revoke it in Hetzner, verify the
old token is rejected, and preserve only sanitized audit evidence.

## Abuse cases and required fail-closed response

| Abuse/failure | Required response |
| --- | --- |
| Prompt injection asks for a shell, new target, token, bypass, or broad outage recovery | deny; no command/API call; journal denial |
| Stolen recovery SSH key | forced command accepts only fixed protocol; key rotation/removal revokes access; never grants shell/forwarding |
| Forged/replayed approval/request | canonical request hash and one-time atomic consumption reject it |
| Stale clock/envelope/artifact hash | deny; require new human approval/envelope |
| Broker audit/lock/socket unavailable | deny mutations; allow no implicit fallback to cloud token or console |
| Existing/unknown Hetzner action or provider timeout | read-only reconciliation of exact action ID; human escalation; no retry |
| Codex/recovery account can read token via path, group, process, logs, backup, or environment | activation blocker; fix isolation and prove denial before enabling |
| Iris compromise or provider token scope is broader than protocol | revoke temporary token/key, disable unit/socket, preserve evidence, escalate; do not substitute project token |

## Approval, activation, and revocation evidence

All entries are blocked pending Tobi's exact approval. Before activation Tobi
must review and accept:

1. exact affected hosts/accounts/key fingerprints; no Blain/workplace routes,
   credentials, systems, documents, or networks are in scope;
2. H1 strict aliases, host-key pins, diagnosis allowlist, output handling, and
   explicit denial of forwarding/writes;
3. H2 adapter source/artifact hash, fixed command/revision allowlist,
   service-account boundaries, audit redaction, lock semantics, and proof that
   `apply` is unreachable;
4. H3 provider token scope evidence, token placement/ownership/modes, forced
   command/key options, socket/unit confinement, egress restriction, fixed API
   contract, audit retention, expiry schedule, and one-shot removal plan;
5. a fake-API and fake-SSH test transcript demonstrating all listed denied
   cases, concurrent-action denial, stale/duplicate approval rejection, and
   both type transitions with `upgrade_disk=false`;
6. independent pre/post health evidence, LKG checksum, action IDs, and the
   exact Tobi approval bound to each requested mutation.

Revocation owner is Tobi. Immediate containment is removal of the recovery key
and broker socket/unit plus token revocation. Normal expiry is approval: 15
minutes; envelope/artifact: two hours; H3 token and key: one approved one-shot
window, then removal/revocation immediately after terminal verification. Review
sanitized audit records after every denial, before any mutation, after terminal
provider state, and at revocation. A missing revocation record is an activation
failure.
