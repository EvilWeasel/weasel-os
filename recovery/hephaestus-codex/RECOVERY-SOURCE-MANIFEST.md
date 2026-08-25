# Sanitized recovery source-of-truth manifest

Discovery date: 2026-08-25
Scope: read-only source discovery for the proposed human-invoked recovery console.

## Operational truth

- Recovery owner: Tobi. The laptop is a human console, never an autonomous cloud controller.
- The independent recovery-controller design is staged only. It is not evidence of deployed SSH access, a service principal, a token, a mesh enrollment, or cloud mutation authority.
- No laptop session, SSH connection, network authentication, ACL change, package activation, service action, or infrastructure mutation was performed during this discovery.
- `codex` is not on this worker host's `PATH`. That observation is **not** evidence about `nixy-laptop`.
- Current laptop runtime state, Codex-auth/config existence and modes, and live NetBird/Tailscale identity/status are **unavailable**: this task deliberately did not contact or authenticate to the laptop.

## Authoritative inputs

| Concern | Authoritative source | Owner / expected access | Observed fact | Recovery-console use |
| --- | --- | --- | --- | --- |
| Laptop configuration composition | `flake.nix`, `flake.lock`, `flake/modules/nixos-configurations.nix`, `hosts/nixy-laptop/config.nix`, and the recovery-module import in `hosts/nixy-laptop/home.nix` | `weasel-os` Git repository; current local tree is `hermes:hermes`, private | The flake lock pins inputs. The laptop config declares a personal NetBird client, `systemd-resolved`, and a narrow Tailscale/NetBird compatibility unit. | Read declarations only; do not infer live runtime state. |
| Recovery bundle package definition | `programs/hephaestus-recovery-console.nix` | `weasel-os` Git repository; private local worktree | Defines an opt-in Home Manager module, package default `pkgs.codex`, and declarative installation of `recovery/hephaestus-codex`. Its option is defined but no enabled declaration was found. | Authoritative intended activation shape, not activation proof. |
| Recovery contract and operator runbook | `recovery/hephaestus-codex/README.md`, `CODEX-OPERATING-CONTRACT.md`, `bin/codex-recovery`, and `skills/*.md` | Bundle is intended for the laptop user after review and activation | The bundle is staged design/review material. It declares strict read-only-first handling, independent recovery ownership, bounded cloud design, and dual-overlay preservation. | Primary operator context; render it through the launcher rather than copying mutable context. |
| Codex installation and auth/config metadata check | `recovery/hephaestus-codex/bin/smoke-test` | Laptop user, after explicit module activation; auth/config remain provider-managed | Smoke test is designed to require `codex --version` and inspect only existence/mode of the conventional Codex auth/config files; it does not read their content. Expected protection is mode 0600 when present. | Run locally only after activation; record pass/fail and modes, never values or file content. |
| Personal overlay declaration | `hosts/nixy-laptop/config.nix`; reusable Tailscale baseline in `profiles/system/base.nix` | `weasel-os` Git repository | NetBird and Tailscale are configured to coexist; NetBird is the policy boundary. The declared compatibility unit waits for both overlay services. | Preserve both overlays as separate failure domains; no ACL, route, firewall, enrollment, or DNS mutation. |
| Hephaestus provisioning source of truth | `/srv/hermes/admin/ansible/README.md`, `site.yml`, `inventory.yml`, and role directories | Private `hermes:hermes` Ansible repository; local `hephaestus` path uses the audited broker | `site.yml` asserts local Fedora `hephaestus`; durable changes go through reviewed commit, broker check, approval where required, apply, and zero-drift check. | Cite role sources and use the broker runbook only after explicit approval for a mutation. |
| Service map | `/srv/hermes/admin/ansible/site.yml` and role task files under `roles/` | Same Ansible source of truth | Declared personal roles include gateway, realtime voice, NetBird client, Work QA, inbox, Factorio backup, and Tailscale repository management. | Use as a map, then verify live state independently; declaration is not health. |
| Gateway last-known-good / rescue path | `roles/hermes_gateway/tasks/main.yml`, `roles/hermes_gateway/files/hermes_gateway_watchdog.py`, `hermes-gateway-rescue-runbook.md`, and `hermes-kanban-resume.sh` | Ansible-controlled root deployment; source is readable to the private repo owner | Gateway changes prepare a content-addressed LKG candidate, preflight as service user, arm independent verification before restart, and abort back to LKG on failure. The role requires stability across a restart interval and exercises bounded recovery drills. | Canonical recovery references. Never treat a newly restarted process as its own verifier. |
| Work / Kanban | Native Hermes Kanban task/run state via `kanban_*` tools; diagnostic source is deployed from the `hermes_gateway` role | Hermes service-owned runtime state; task metadata through the tool interface | Work is native Hermes state. The recovery contract requires capturing only current task/run and concise redacted status. | Use current task/run metadata only. Do not read raw database bodies, comments, logs, attachments, chats, or memories. |
| Realtime recovery boundary | `roles/aidan_realtime_voice/tasks/main.yml` and its documented actuator record | Ansible-controlled root deployment; private service runtime | The intended actuator has fixed scope and an audit boundary; credentials and engine logs are protected inputs. | Use only sanitized service status and documented restart recovery record after approval; never inspect credentials or private logs. |
| Factorio backup / restore evidence | `roles/factorio_backup/tasks/main.yml` and its documented restore verifier/runbook | Ansible-controlled service account and root deployment | Backup storage is separated from the game service, private, timer-driven, and includes restore verification. | Refer to verifier status and runbook, never save contents. |
| Cloud migration design | `recovery/hephaestus-codex/iris-broker/README.md`, `skills/cx43-rescale-safety.md`, and `README.md` | Versioned staged design material | Design limits a future broker to a fixed protocol, a separate service principal, explicit one-time approval, an exact action journal, and a bounded health gate. No broker deployment or cloud authority was observed. | Treat as design only. Every cloud mutation requires a fresh explicit approval and independent preconditions. |
| Older architecture/migration notes | `docs/target-architecture.md`, `docs/migration-plan.md` | Versioned repository documentation | They describe WeaselOS modularization targets and historical migration assumptions, not current service truth. | Background only; do not use to decide recovery actions. |

## Availability and confidence

- **Observed from local source only:** repository structure, private ownership metadata, Git tracking status, module declarations, Ansible roles, and documented recovery controls.
- **Not observed:** laptop generation, package installation, Codex version on the laptop, Codex auth/config presence or permissions, SSH alias resolution on the laptop, live overlay peer identity, service health, cloud state, watchdog/LKG presence on a running host, or backup freshness.
- **Important working-tree caveat:** the recovery module and bundle were not Git-tracked at discovery time. They are useful staged inputs but become an authoritative reviewed artifact only after normal review and commit.

## Explicit exclusions

Do not ingest, copy, summarize, place, or send any of the following into the console context, manifest, prompts, journals, or diagnostics:

- raw Hermes memory, chat/session stores, task bodies/comments/logs/attachments, or unrelated personal documents;
- Codex auth/config contents, private keys, SSH agent material, host keys, browser data, tokens, certificates, passwords, or secret environment files;
- Discord, Cloudflare, NetBird enrollment/API, Hetzner, dashboard, Work QA, Realtime, or other credentials;
- any workplace/Blain system, configuration, alias, route, VPN, credential, document, SaaS, network, or data;
- unredacted service logs, save contents, or cloud API responses.

The mixed laptop Home Manager file contains non-recovery material outside this task boundary. Its recovery-module import is placement evidence only; downstream recovery work must not inspect or use the unrelated portions.

## Read-only confirmation

This manifest was produced using local file metadata and source reads only. No remote host was contacted, no authentication was attempted, and no state, permissions, secrets, packages, services, ACLs, filesystems, network configuration, or infrastructure was changed. The only artifact created was this sanitized Markdown manifest.
