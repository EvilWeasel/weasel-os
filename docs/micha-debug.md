# Micha Debug Workflow

Use the full flake path when rebuilding from a fresh install or VT:

```bash
sudo nixos-rebuild switch --flake /home/micha/weasel-os#michapc
sudo nixos-rebuild switch --flake /home/micha/weasel-os#michapc-debug
```

If `nh` is available, the equivalent commands are:

```bash
nh os switch --hostname michapc /home/micha/weasel-os
nh os switch --hostname michapc-debug /home/micha/weasel-os
```

## Recommended order

1. Try `michapc` first. This is the target architecture with DMS enabled.
2. If login still fails after DMS starts, reboot into a working generation.
3. Switch to `michapc-debug` if you want plain `niri` without post-login DMS.
4. Run the collector command from any working shell and send the resulting folder.

## VT-safe debug commands

Capture a full bundle:

```bash
weasel-collect-session-debug
```

The command prints the output folder path. Bundles are stored under:

```text
~/weasel-debug/<host>-<timestamp>/
```

Useful files inside the bundle:

```text
journal-filtered.txt
journal-user-boot.txt
journal-greetd-boot.txt
processes-interesting.txt
coredumps-interesting.txt
```

## Persistent DMS logs

For hosts that start DMS, persistent session logs are written to:

```text
~/.local/state/weasel-debug/dms/
```

Latest files:

```text
~/.local/state/weasel-debug/dms/latest.log
~/.local/state/weasel-debug/dms/latest.env
```
