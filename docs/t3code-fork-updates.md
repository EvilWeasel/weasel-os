# T3 Code fork on NixOS

Both hosts declare `weasel.t3Fork.enable = true`. Home Manager owns the fork launcher,
updater and hourly user timer. The updater downloads prebuilt x86_64 Linux releases
from `morrowbyte/t3code`, verifies GitHub's SHA-256 digest and packages them for NixOS.
The installer and packaging recipe are pinned to an immutable source revision and
fixed hashes in `programs/t3code-fork.nix`; release versions follow the selected
channel. This deliberately trades a fixed application version for automatic updates.

The fork retains its existing profile at `~/.local/share/t3code-weasel` and uses
`t3code-weasel`; the upstream `t3code` and `mtcode` remain separate applications.
No application, agent or server is restarted by an update. A successful update
changes an atomic pointer, so the next launch uses the prepared version. Failed
fetches, checksums or package builds leave the current version in place. Version
packages have permanent Nix GC roots and remain available for rollback.

After applying the host configuration:

```sh
t3code-weasel-update --check       # release metadata only
t3code-weasel-update --update      # prepare the selected channel now
t3code-weasel-update --status      # installed version, no network
t3code-weasel-update --rollback VERSION
systemctl --user status t3code-fork-update.timer
journalctl --user -u t3code-fork-update.service
```

The default channel is nightly. Stable is supported only for releases explicitly
published as `Weasel Stable`; it never silently selects a nightly/upstream release.
To hold a rollback, set `weasel.t3Fork.autoUpdate = false` declaratively; otherwise
the next hourly check can move it forward again. Old roots are retained, not
silently garbage-collected by the updater.

Windows continues to use the fork's Electron updater and release repository
`morrowbyte/t3code`. Ordinary Linux uses the AppImage updater. This Nix module is
specific to x86_64 NixOS; a macOS fork release has not yet been qualified.
