# CI runners

The owner migrated `morrowbyte/weasel-os` from Namespace to Blacksmith on 2026-10-15. This supersedes previous Namespace-only guidance. All compilation, packaging and full checks stay on remote GitHub Actions runners, never the laptop or Hephaestus.

`CI_ENABLED=true` enables the existing workflow. `CI_RUNNER=blacksmith-8vcpu-ubuntu-2404` is the normal runner. Full system builds explicitly use `blacksmith-16vcpu-ubuntu-2404`, whose larger disk avoids the previous Namespace cache-volume exhaustion. No purchased capacity or new subscription is provisioned by the workflow.

The existing `namespace.yml` workflow path remains stable for callers; its display name is **Blacksmith Nix CI**. Pushes and pull requests evaluate both locked host configurations. Manual `build=true` builds both systems; `probe_only=true` inspects runner storage. Builds never activate a host or update flake.lock.

The Namespace cache-volume action was replaced by the pinned upstream `nix-community/cache-nix-action`, using Actions cache transport. Evaluation caches are separated by host and bounded to 8 GiB before saving; pull requests do not save caches. Full system builds skip store caching so complete closures and build temporaries use runner disk. Blacksmith's transparent Actions cache is not a laptop-accessible binary cache.

Runner reference: https://docs.blacksmith.sh/blacksmith-runners/overview.
