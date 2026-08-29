# Hermes recovery operations

- Work/Kanban is the canonical operational record. Read the current task and run before acting; record concise, redacted evidence rather than creating a parallel ledger.
- Start with read-only diagnosis. Distinguish a local service failure from an overlay, Internet, provider, or cloud-control-plane outage before changing anything.
- The audited Ansible broker is the source of truth for hephaestus provisioning. Do not replace it with direct system changes.
- Preserve the last-known-good bundle and checksum evidence before any approved recovery. A stable PID is not health: require the declared liveness window and service-level probes.
- Do not restart-flap. If a recovery attempt does not have a bounded health gate and rollback owner, stop and escalate.
