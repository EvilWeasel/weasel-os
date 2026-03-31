# Secrets

Host-secrets live under `secrets/hosts/<host>/secrets.yaml` and are managed with `sops-nix`.

Current state:

- the repository is prepared for encrypted host secrets
- the operator recipient is already configured in `.sops.yaml`
- each server still needs its own bootstrap Age recipient added before first deployment

Expected host secret contents for `ew-cloud`:

- `tailscale.auth_key`
- later optional service secrets for `openclaw`
