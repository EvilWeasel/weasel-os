---
name: proton-pass-cli
description: "Use Proton Pass CLI to provide credentials to an authorized API call or command without exposing their values. Apply when a task needs a secret stored in Proton Pass, or the user requests Proton Pass CLI setup or authentication."
---

# Proton Pass CLI

Resolve only the credential needed for the user's task. Prefer injecting a
`pass://` reference into the target process with `pass-cli run`; keep secret
values out of chat, tool output, shell arguments, generated files, and Git.

## Check the installed CLI and session

```bash
command -v pass-cli
pass-cli --version
pass-cli login --help
pass-cli run --help
pass-cli vault list --help
pass-cli item list --help
pass-cli info
```

The desktop `proton-pass` application and `pass-cli` have separate sessions.
Verify flags against the installed version; current online docs can describe a
newer release. If installation is needed on this NixOS machine, use the
declarative `proton-pass-cli` package from the configured package set. Do not
replace declarative packaging with the vendor's shell installer or self-update.

## Authenticate when needed

Use the existing session first. For a new Linux desktop session, use persistent
Secret Service storage rather than the default kernel keyring, whose key is
cleared at reboot:

```bash
PROTON_PASS_LINUX_KEYRING=dbus pass-cli login
PROTON_PASS_LINUX_KEYRING=dbus pass-cli info
```

The configured GNOME Keyring must be available and unlocked. Show the login URL
returned by the CLI and let the user finish browser authentication; never ask
for an account password, recovery code, or access token in chat. Check that the
login succeeds before dependent operations. Keep the same keyring setting for
later commands; prefer the declarative environment setting when present. Do not
switch an existing session's storage backend, log out, or delete session files
as an authentication shortcut. Do not silently fall back to filesystem keys.

## Locate the exact item

If the task already supplies a secret reference, use it. Otherwise inspect vault
and item metadata, limited to the relevant vault where known:

```bash
pass-cli vault list --output human
pass-cli item list --share-id VAULT_SHARE_ID --output human
```

These list commands provide names and IDs. Use human output for discovery:
older releases can include secret content in JSON item lists. Never add
`--show-secrets`. Match the requested service, then use its exact vault Share ID
and item ID; duplicate names can resolve to an unintended item. Do not browse
unrelated items. If the field name is unknown, inspect only that selected item's
JSON inside a local subprocess with captured output and print an allowlist of
field **names**, never field values, notes, or the raw JSON. Do not run an
unfiltered `item view`, `item get`, or `item read` into a tool's visible output.

The reference format is `pass://VAULT_SHARE_ID/ITEM_ID/FIELD`, with `password` or
the item's actual custom field name as `FIELD`. Store this reference, not its
resolved value, in application configuration when persistence is useful.

## Run the authorized command

```bash
CARTESIA_API_KEY='pass://VAULT_SHARE_ID/ITEM_ID/FIELD' \
  pass-cli run -- /absolute/path/to/authorized-command arguments
```

Replace the example environment variable with the target program's expected
variable. `pass-cli run` resolves references in the child environment and masks
secrets in its stdout and stderr by default. Retain masking; do not use
`--no-masking`, shell tracing, environment dumps, or credential-bearing command
arguments. The child program must avoid logging authorization headers and raw
error bodies that may contain credentials. For SDKs that require an in-memory
value instead of environment injection, capture only the requested field in a
subprocess and consume it locally without printing it or its exception output.

Secret access authorizes neither unrelated API actions nor changes to accounts,
vaults, items, permissions, or tokens. Make those changes only when the user's
task authorizes them. On locked sessions, missing items, ambiguous matches, or
permission errors, report the specific nonsecret blocker and complete any
independent preparation instead of weakening storage or exposing credentials.

## Official references

- [Installation](https://protonpass.github.io/pass-cli/get-started/installation/)
- [Browser login](https://protonpass.github.io/pass-cli/commands/login/)
- [Session and keyring configuration](https://protonpass.github.io/pass-cli/get-started/configuration/)
- [Vault metadata](https://protonpass.github.io/pass-cli/commands/vault/)
- [Item commands](https://protonpass.github.io/pass-cli/commands/item/)
- [Secret references](https://protonpass.github.io/pass-cli/commands/contents/secret-references/)
- [Masked process execution](https://protonpass.github.io/pass-cli/commands/contents/run/)
