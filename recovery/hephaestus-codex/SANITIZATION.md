# Sanitization and contribution boundary

This directory is a versioned, documentation-first recovery bundle. It is not a
credential store, an inventory database, a general workstation backup, or an
autonomous controller. The recovery owner is Tobi.

## Absolute exclusions

Never add, summarize, derive from, or reference in a way that exposes content
from any of the following:

- Blain/workplace systems, hosts, routes, VPNs, aliases, SaaS, documents,
  credentials, networks, or data;
- raw Hermes memories, chats, sessions, task bodies, comments, logs,
  attachments, databases, or browser data;
- unrelated personal files or documents;
- passwords, tokens, API keys, cookies, certificates, private keys, SSH agent
  material, host keys, secret environment files, or Codex auth/config contents;
- raw service logs, Factorio saves, cloud API responses, or backup contents.

Use placeholders such as `<REDACTED_ACTION_ID>` and `<APPROVAL_REFERENCE>` only
when an example needs a value. A placeholder must not resemble a real secret.

## Allowed material

Contributions may contain only reviewed, sanitized operational guidance:

- declarative source locations and ownership boundaries;
- fixed capability contracts, health gates, rollback criteria, and escalation
  conditions;
- metadata-only examples with synthetic IDs marked as examples;
- offline commands that do not authenticate, contact a provider, or alter state.

A source declaration is not proof of live state. Do not turn an unavailable
observation into an asserted fact.

## Contribution procedure

1. Keep the change offline and documentation-only unless Tobi separately
   approves a scoped live action after its effect, risks, and rollback are
   stated.
2. Add no new network endpoint, credential path, SSH configuration, overlay
   enrollment, ACL, firewall rule, service action, or cloud mutation.
3. Run `bin/verify-sanitized-tree`, `bin/codex-recovery --dry-run`, and
   `bash -n bin/codex-recovery bin/smoke-test bin/verify-sanitized-tree`.
4. Review the diff for identifiers, paths, and examples that could reveal a
   prohibited source. Keep evidence in native Work/Kanban as concise redacted
   metadata, never by copying raw records here.
5. Require review before activation. Human invocation remains mandatory:
   `bin/codex-recovery --start` is the only console launch path and it must not
   be run by timers, services, or unattended automation.

`CODEX-OPERATING-CONTRACT.md` is the launcher-loaded instruction contract.
The standard `AGENTS.md` filename is intentionally not added: a prior protected
instruction-file gate could not be approved through the canonical channel, and
its replacement is explicitly accepted as non-blocking staged design. Do not
bypass that gate.

## Denylist

The repository rejects secret-like file names and checks the bundle for common
private-key, bearer-token, long opaque-token, and assignment-like secret
patterns. These are defense-in-depth checks, not a license to include material
that happens to evade a pattern. If in doubt, exclude it and escalate to Tobi.
