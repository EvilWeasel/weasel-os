# Contributing to the hephaestus recovery console

This bundle is intentionally narrow. The only acceptable default contribution is
sanitized, offline-operable documentation or validation that preserves the
human-invoked recovery boundary.

Before proposing a change, read `README.md`, `SANITIZATION.md`, and
`CODEX-OPERATING-CONTRACT.md`. Do not access Blain/workplace resources or ingest
raw Hermes state, chat/session content, unrelated personal files, credentials,
private keys, or secret values to produce a contribution.

Changes that add authority, authentication, a network connection, a cloud/API
operation, service action, SSH/overlay policy, or secret placement are outside
this staged repository work. They require Tobi's separate explicit approval
with the exact effect, risk, rollback, and recovery owner stated first.

Run the local checks named in `SANITIZATION.md` before review. Report only
redacted results and failures. Do not copy a failing line, secret candidate, or
prohibited payload into a commit message, issue, or Work/Kanban record.
