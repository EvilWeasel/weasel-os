# Proposed iris forced-command broker — staged design

Status: design and validation material only. No SSH key, account, authorized_keys
entry, systemd unit, secret, Hetzner token, or Cloud action is created by this
repository.

## Security model

Codex must not receive a Hetzner token. A future `iris` broker is the only
process allowed to read its temporary token, under a dedicated local service
principal separate from the forced-command SSH principal. The broker accepts a
small fixed protocol for server `162472190` only:

- `status`
- `poweron` or graceful `shutdown`
- `change_type` to exactly `cx43` or exactly `cpx22`, always with
  `upgrade_disk=false`

There are no user-supplied hostnames, server IDs, shell commands, headers, URLs,
token paths, disk options, firewall operations, or arbitrary action names.

The SSH account used by the recovery console has an `authorized_keys`
`command=` restriction, no PTY, no agent forwarding, no port/X11 forwarding,
no `permitopen`, and no interactive shell. Its forced command invokes the
validator and broker request socket; it never executes `$SSH_ORIGINAL_COMMAND`
as a shell. The service principal exposes only a Unix socket/group boundary to
that forced command. Token access is denied to the SSH account and to Codex.

A request is valid only when all are true:

1. It is canonical JSON with protocol version, random request ID, exact allowed
   operation, timestamp, expiry <= 15 minutes, and the required fixed constants.
2. It has a human-issued, one-time approval ID bound to the exact operation and
   request SHA-256. The approval is created outside Codex and recorded in native
   Work/Kanban; a stale, duplicate, foreign, or already-consumed approval fails.
3. The broker sees no active action/lock before a new operation and journals the
   request/action IDs before and after API submission.
4. The run envelope and controller binary hash are valid and within their
   separate two-hour lifetime.

The forced command is a capability handle, not blanket Cloud authority. It can
observe all the time but cannot mutate until a matching one-time human approval
exists. Even then it cannot race an existing action.

## Secure temporary token placement — runbook for a separately approved deployment

This sequence requires Tobi's explicit approval before execution because it
creates a secret location and external authority. It is not performed here.

1. Tobi creates a new token only after checking whether Hetzner offers a scope
   narrow enough for this fixed server/action set. If the provider has no
   suitable scope, treat it as a project-wide write credential and stop for a
   fresh risk decision; fixed client code does not reduce the credential's API
   authority.
2. Install the broker from a reviewed, checksummed artifact under a dedicated
   service account. Create a root-owned (or service-principal-owned) mode-0700
   state directory and a mode-0600 token file. The Codex SSH account, its group,
   home, working directory, logs, environment, command line, and Git checkout
   must have no read path to that file.
3. Mount only the broker's narrow runtime socket for the forced command. The
   socket protocol validates the request above; it never returns token material
   or raw API responses.
4. Log only UTC time, request ID, approval ID, operation, fixed server ID,
   action ID, result class, and redacted HTTP error code. Make journal append
   only to the service principal; retain checksums and action IDs.
5. Test with a fake local API and a fake SSH connection first. The test must
   prove rejection of arbitrary commands, IDs, types, stale/duplicate approvals,
   expired envelopes, missing hashes, token-readable paths, active actions, and
   lock races. It must also prove `upgrade_disk=false` on both type changes.
6. After the one-shot run, revoke/delete the token, verify the old token fails
   authentication, remove the temporary approval material and forced-command
   key, and retain only sanitized evidence.

## Rollback

Before any Cloud run, remove the dedicated SSH key/account/socket/unit and token
file through the reviewed configuration; this removes the handle without
changing hephaestus. During an active Cloud action, do not remove the broker or
submit a competing operation: leave it read-only until the exact action reaches
a terminal state or human console/support takes over.
