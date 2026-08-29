# Staged recovery-console package review

Review date: 2026-08-25
Status: **not approved for activation**. This is a review of staged source only.
Recovery owner: **Tobi**. The proposed independent cloud-control owner is a
future `iris` one-shot broker, not Codex and not `hephaestus`.

## Decision

The package is internally consistent as a **documentation and offline-fixture
bundle**. Its sanitization guard, link checker, launcher context rendering,
request validator, and synthetic broker fixture pass locally. It is not an
activated or enforceable recovery control plane. Activation must remain blocked
until the exact checklist below is fulfilled and Tobi grants an explicit,
time-bounded approval for each activation/mutation boundary.

No authentication, SSH, NetBird ACL, secret placement, Codex activation, or
Hetzner mutation occurred during this review. No provider, host, overlay, or
cloud endpoint was contacted.

## Proposed effect if separately approved

Enabling `weasel.hephaestusRecoveryConsole` on `nixy-laptop` would install the
flake-locked `codex`, `git`, and `openssh` packages and deploy the sanitized
read-only bundle at `~/recovery/hephaestus-codex`. It does not itself change an
SSH key, alias, NetBird/Tailscale ACL, secret, system service, broker, or
Hetzner resource.

The later H1/H2/H3 handles described in `CAPABILITY-HANDLES-DESIGN.md` are
separate deployments. H1 is read-only diagnosis; H2 is Ansible check/diff only;
H3 is limited to server `162472190` status/power/type actions and needs a
one-time hash-bound approval for every mutation. None exists in this package.

## Validation evidence

The following all passed locally and offline from this repository:

- `bash -n` for all five bundle shell programs, including the added link and
  synthetic-fixture checks.
- `bin/verify-sanitized-tree`: denylisted-path, private-key, token-like,
  opaque-value, and prohibited workplace operational-reference scan passed.
- `bin/verify-document-links`: all relative Markdown targets in the bundle
  resolved. External URLs are intentionally not fetched.
- `python3 -B -m py_compile` for the request validator and its test module.
- `python3 -B -m unittest -v iris-broker/test-validate-request.py`: 5/5 passed;
  wrong server, disk growth, arbitrary operation, and expired approval are
  rejected.
- `bin/review-smoke-test`: synthetic fixed CX43 request received an `ACCEPT`
  response; a synthetic wrong-server request received `REJECT wrong server_id`.
  The fixture uses only a temporary local file and no network.
- `bin/codex-recovery --dry-run`: effective contract and selected sanitized
  skills rendered without starting Codex or contacting a provider.
- `git diff --check`: passed.

The activation-only `bin/smoke-test` deliberately failed at its first live
prerequisite: `Codex CLI is not installed` on this Fedora staging worker. That
is expected and correctly fail-closed; it is not evidence about `nixy-laptop`.
The Nix/Home Manager evaluation and the post-activation laptop smoke test have
not run because this worker has neither Nix nor authority to authenticate to
the laptop.

## Security review and hard blockers

1. **Blain/workplace boundary is not technically enforced by this bundle.** The
   staged contract forbids it, but the existing `hosts/nixy-laptop/home.nix`
   contains an unrelated `hermes-blain-tunnel` SSH service. A Codex process in
   the normal laptop user context is not OS-sandboxed from that pre-existing
   configuration. Do not activate the console in that account until a reviewed,
   technically enforced isolation design proves that Codex cannot invoke the
   alias, read its usable credential path, or reach workplace resources.
2. **No H1/H2/H3 broker is implemented.** The Python code validates a proposed
   request format only. It does not prove forced-command confinement, approval
   consumption, locks, audit append semantics, token unreadability, provider
   egress restrictions, or fake-SSH/fake-API denial behavior.
3. **No root-protected Hetzner-token denial test ran.** The package contains no
   token and the staging worker has no broker. Token placement and access must
   be proven with a dedicated service account, root-owned parent directory,
   mode 0600 secret, and negative read/traversal/process/log tests before H3.
4. **No laptop evaluation or live Codex smoke test ran.** Nix evaluation, exact
   package pin resolution, mode checks on the provider-managed auth/config
   files, and strict-host-key alias evaluation remain pre-activation gates.
5. **Prompt text is not a permission system.** It cannot prevent a locally
   authenticated model from proposing or attempting unsafe commands. Real
   containment needs a separate account/sandbox plus fixed capability handles.

## Exact approval questions for Tobi

Before enabling the read-only bundle, approve or reject:

1. The laptop account/isolation model that prevents Codex access to Blain/workplace
   resources and unrelated credentials, with an independently verified denial
   test and rollback to the present configuration.
2. Installing the flake-locked packages and deploying the bundle on
   `nixy-laptop`; effect, provider-context disclosure risk, and rollback are as
   described above.
3. The exact approved recovery SSH identities, aliases, host-key pins,
   diagnostic command allowlist, output caps/redaction, and proof that writes,
   forwarding, and arbitrary commands are denied.
4. For H2, the root-owned adapter artifact, fixed revision/command allowlists,
   no-`apply` proof, socket permissions, sanitized audit schema, and teardown.
5. For H3, temporary token provider scope, service-account/token placement,
   forced-command options, socket/egress confinement, audit retention, expiry,
   fake-API/fake-SSH denial tests, and post-use revocation.
6. For every future `shutdown`, `change_type`, `poweron`, or eligible rollback,
   the canonical request hash, 15-minute approval window, 2-hour envelope,
   exact effect/risk/rollback, and current no-active-action evidence.

## Activation checklist

All boxes are mandatory; unchecked means activation stays off.

- [ ] Tobi approves the reviewed laptop isolation design and its negative
      Blain/workplace-access test; normal shared-user activation is not accepted.
- [ ] The final Nix module and lock inputs are evaluated on `nixy-laptop`
      without writing `flake.lock`.
- [ ] The Home Manager generation is reviewed; only the package/bundle effect is
      present, with no auth/SSH/ACL/secret/service mutation.
- [ ] `verify-sanitized-tree`, `verify-document-links`, unit tests, synthetic
      fixture, and `codex-recovery --dry-run` pass from the installed bundle.
- [ ] The local smoke test passes on the laptop: Codex is present, any existing
      auth/config metadata is mode 0600, and the recovery alias preserves strict
      host-key checking. It must not print credential contents or contact a host.
- [ ] If H1 is proposed, its fixed read-only commands and denied forwarding/write
      tests pass under the isolated recovery principal.
- [ ] If H2 is proposed, check/diff/status-only tests prove `apply`, arbitrary
      args, other hosts, dirty revisions, and secret paths are denied.
- [ ] If H3 is proposed, fake-SSH/fake-API tests prove fixed target/type/disk,
      one-time approval consumption, expiry/replay/lock denial, audit failure
      denial, token unreadability, no shell/forwarding, and no broad egress.
- [ ] LKG checksum, Factorio restore proof, independent controller health, and
      the runbook's preflight evidence are current before any cloud approval.
- [ ] Tobi gives an exact, separate approval for each live activation and each
      cloud mutation. A previous design decision is not a mutation approval.

## Expiry and audit review schedule

- Approval record: maximum 15 minutes; atomically single-use.
- Broker envelope and pinned controller artifact: maximum 2 hours.
- H3 temporary key/token: one approved one-shot window only; remove/revoke
  immediately after terminal verification.
- Audit review: inspect sanitized records after every denial, before a mutation,
  after the exact provider action reaches terminal state, and during revocation.
  Audit unavailability, missing terminal record, or missing revocation record is
  a fail-closed activation failure.
- Retention: retain only sanitized UTC timestamps, principal/fingerprint,
  request/approval/action IDs and hashes, outcome class, redacted error class,
  and LKG/health checksums in native Kanban. Never retain token values, raw API
  responses, raw logs, private keys, or provider auth files.

## Offline fallback and rollback

If Codex, the broker, an overlay, or a provider path is unavailable: preserve
local Git revision, LKG checksums, sanitized journal, and exact action IDs;
classify the failure domain through the runbook; and stop mutations on any
ambiguity. Tobi uses the static runbook and, if required, Hetzner console/support
for reconciliation. Do not copy a token to the laptop, enable public access,
retry a cloud action, or restart-flap a locally healthy service.

Rollback of bundle activation: set the module option false, switch/roll back the
laptop generation, remove an old managed bundle path if necessary, and confirm
from a fresh login that the launcher/package path is absent as expected. This
does not alter Codex provider auth.

Rollback of a future CX43 change is never automatic: only runbook health-gate
exit 20 plus a new exact Tobi approval can request `cx43` to `cpx22` with
`upgrade_disk=false`. All other outcomes are observation-only.

## Credential revocation procedure

1. Disable the recovery module and remove the one-shot recovery SSH key/socket/
   unit through reviewed declarative configuration.
2. Delete the temporary broker secret from its root-owned mode-0600 location and
   revoke that token at Hetzner; verify the revoked credential is rejected
   without logging it. Never substitute or expose the project-wide token.
3. Remove the associated broker service account/key access and prove the former
   caller cannot invoke the forced command or read the audit/secret paths.
4. If provider access itself must be revoked, use Codex's official interactive
   logout on the laptop after Tobi approves its impact; do not print or edit
   provider-managed auth contents.
5. Record sanitized revocation evidence in the current Kanban task. Missing
   evidence leaves the capability disabled and the incident open.
