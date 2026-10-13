# Namespace CI

The GitHub repository is `morrowbite/weasel-os`. Namespace runner profile: `namespace-profile-ci-builder`.
GitHub App installation and profile readiness must be confirmed before execution.

Set repository variable `CI_ENABLED=true` only after Namespace onboarding.
`CI_RUNNER` defaults to `namespace-profile-ci-builder` (8 vCPU,
16 GB RAM). This gate keeps jobs from waiting indefinitely during onboarding.

Pushes and pull requests evaluate both hosts and the locked flake. To build both
systems, dispatch **Namespace Nix CI** with **build** selected. The runner profile supplies a persistent Nix store cache;
protect cache writes to trusted branches in Namespace. Build jobs are
bounded to 180 minutes and never activate a system or update the lockfile.

This cache accelerates subsequent GitHub jobs. It is not a laptop-accessible
binary cache and does not speed up local rebuilds automatically.

Runner reference: https://namespace.so/docs/solutions/github-actions
