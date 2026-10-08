# Own VPS credentials in Proton Pass

The own-infrastructure admin key is a native ED25519 SSH-key item named
`weasel-own-infra-admin-20261008` in the dedicated **Own Infrastructure SSH**
vault. Its public fingerprint is
`SHA256:223qRj+Bgp8GbqAZuobBSAB5zQtqG7qMDQjH899zHPg`.
Proton generated and stores the private key; the laptop has only its public
identity file at `~/.ssh/weasel-own-infra-admin.pub`.

The user service `weasel-proton-infra-ssh-agent.service` runs the pinned Proton
Pass CLI with that vault's exact share ID. Its socket is
`/run/user/1000/proton-infra-ssh-agent.sock`. The existing SSH agent continues
to serve other SSH/Git identities. The VPS fragment selects the Proton socket,
the public identity file and `IdentitiesOnly yes` for these aliases:

| Alias | Account and route | Admin access |
| --- | --- | --- |
| `hephaestus-netbird` | `hermes@100.96.10.221` | Hermes service account |
| `hephaestus-root` | `root@100.96.10.221` | Hephaestus administrator |
| `iris`, `iris-aidan` | `aidan@46.225.77.36` through `hephaestus-root` | `sudo -n` on Iris |

Iris keeps `PermitRootLogin no` and its existing allowed-user policy. Its SSH
firewall continues to accept the established Hephaestus route. Host keys are
pinned, and agent forwarding is disabled. The new Hephaestus key is restricted
to the laptop's personal NetBird source address `100.96.62.207`; its root entry
allows TCP forwarding only to `46.225.77.36:22`, and the Hermes entry allows no
port forwarding. The Iris entry accepts the Hephaestus egress address
`167.233.244.111` and disables agent/X11 forwarding. Existing authorized keys
remain available.

Routine checks and use:

```sh
env PROTON_PASS_LINUX_KEYRING=dbus pass-cli info
systemctl --user status weasel-proton-infra-ssh-agent.service
env SSH_AUTH_SOCK=/run/user/1000/proton-infra-ssh-agent.sock ssh-add -l
ssh hephaestus-netbird
ssh hephaestus-root
ssh iris 'sudo -n id -un'
```

The native agent requires an authenticated Proton CLI session and access to
the user's unlocked desktop keyring. The service supplies the DBus backend,
runtime directory and session bus explicitly and retries startup failures.
After unlocking the desktop keyring, `systemctl --user restart
weasel-proton-infra-ssh-agent.service` reconnects the agent. An expired Proton
login still requires the normal Proton login flow. See the official
[Proton SSH-agent documentation](https://protonpass.github.io/pass-cli/commands/ssh-agent/).

The initial setup built and installed the exact immutable Home Manager unit,
then enabled it through `systemctl --user`. Its source and CLI dependency are
protected by the single GC root
`~/.local/state/weasel-infra/proton-agent-unit-root` until the declarative home
generation also references them. The declaration permits replacing only this
new task-owned unit during the OS bootstrap. Other Home Manager settings were
not activated as part of the key setup.

The original encrypted `~/.ssh/evilweasel.cloud` key and its public file are
also backed up, unchanged, in a **Personal** secure note named
`evilweasel.cloud encrypted SSH backup 20261008`. The note contains a JSON
object with `private_key_encrypted`, `public_key`, `original_path` and
`passphrase_stored: false`. Its ED25519 fingerprint is
`SHA256:JM2klAvABVcusLbr7qCH2HAD37ZOUeF5Mq5H8ZGtc30`; the existing
`aes256-ctr` passphrase protection remains intact. Recovering that legacy key
requires its existing passphrase. The working Proton admin key is independent
of that passphrase.

Exact item references are recorded outside Git in
`~/.local/state/weasel-infra/credentials.json`, with a `0700` parent directory
and a `0600` file. It contains item references, public fingerprints and paths,
with no private-key or passphrase values. The native key's `/private_key`
secret reference was compared against the item privately. Proton's field-read
command returns the field as raw text even with `--output json`; integrations
must capture that result in process memory. Normal SSH uses the native agent
and needs no private-key export. The official
[item documentation](https://protonpass.github.io/pass-cli/commands/item/)
describes native keys and stdin templates.

Validation on 2026-10-08 covered the scoped agent's single public identity and
real logins using a separate config that offered only the new Proton identity:
Hephaestus `hermes`, Hephaestus `root`, and Iris `aidan` followed by
`sudo -n id -un`. Each server accepted the expected public fingerprint. The
legacy backup's private and public bytes matched after retrieval, and the
original file's inode and permissions were preserved.

The permanent user unit was observed enabled and active, and all three logins
passed again after it replaced the temporary native daemon. The socket has
mode `0600` under the user's `0700` runtime directory. Both Hephaestus roles
rejected a forwarding request to `127.0.0.1:22` as administratively prohibited;
the permitted Iris jump succeeded. The module was formatted and parsed, its
exact unit derivation was built, and laptop toplevel evaluation passed with
`--no-write-lock-file`.

During setup, automatic approval rejected an agent using the entire AI vault;
the dedicated vault resolved that scope issue. It also rejected the CLI's
empty custom-template command after an earlier missing-keyring invocation
attempted logout. The encrypted legacy backup used the documented secure-note
stdin template with the verified DBus session instead. No local Proton data
was deleted or authentication reset.
