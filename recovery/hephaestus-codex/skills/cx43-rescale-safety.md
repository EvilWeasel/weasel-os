# CX43 rescale safety

- The iris controller is independent because hephaestus is intentionally unavailable during its graceful shutdown. The laptop is a human console, not an autonomous controller.
- The fixed target is only server `162472190`: cpx22 to cx43, then cpx22 rollback if and only if the declared post-boot gate exits 20. Both changes retain the 80 GB disk with `upgrade_disk=false`.
- Each Cloud operation needs its own one-time human approval, a valid short-lived envelope, matching request hash, no active action, no lock, bounded polling of the exact action ID, and a sanitized append-only journal.
- Exit 0 accepts CX43. Exit 20 permits the bounded rollback. Every other result is indeterminate: observe, preserve action IDs and evidence, and escalate. Never race an active action with a power or rollback request.
- Codex has no Hetzner token. The future forced-command broker is a narrow capability handle, not blanket cloud authority.
