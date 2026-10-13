# Blacksmith CI

The GitHub repository is `morrowbyte/weasel-os`. Blacksmith's GitHub App is
installed on the organization. Runner execution requires Blacksmith account
verification; installation alone does not prove that a runner is available.

Set repository variable `BLACKSMITH_ENABLED=true` only after verification.
`BLACKSMITH_RUNNER` defaults to `blacksmith-8vcpu-ubuntu-2404` (8 vCPU,
32 GB RAM). This gate keeps jobs from waiting indefinitely during onboarding.

Pushes and pull requests evaluate both hosts and the locked flake. To build both
systems, dispatch **Blacksmith Nix CI** with **build** selected. Each host has a
separate Nix store cache; only trusted non-PR runs save caches. Build jobs are
bounded to 180 minutes and never activate a system or update the lockfile.

This cache accelerates subsequent GitHub jobs. It is not a laptop-accessible
binary cache and does not speed up local rebuilds automatically.

Runner reference: https://docs.blacksmith.sh/blacksmith-runners/overview
