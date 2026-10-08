#!/usr/bin/env python3
"""Merge declarative shared-context guidance without replacing user instructions."""

import argparse
import fcntl
import os
from pathlib import Path
import stat
import tempfile


BEGIN = "<!-- weasel-os:shared-agent-context:start -->"
END = "<!-- weasel-os:shared-agent-context:end -->"


def managed_block(codex_home):
    memories = codex_home / "memories"
    user_home = Path.home()
    return f"""{BEGIN}
# Shared local knowledge for Codex clients

The existing local knowledge is in `{memories}`. For nontrivial work that may
depend on earlier decisions or workspace history, read `memory_summary.md`
there if its content was not already supplied by the client, then search
`MEMORY.md` with relevant project paths and task terms. Read
only the relevant referenced notes; simple self-contained requests do not need
a memory lookup. Recheck facts that can drift, and identify memory-derived
claims that were not verified against current state. Preserve the user's
existing memory-citation instructions when the client supplies them.

Treat those memories as read-only unless the user explicitly asks to update
them. If an update is requested, add one concise dated note under
`{memories / 'extensions/ad_hoc/notes'}`; do not overwrite the existing registry
or summaries.

Use the existing skills in `{codex_home / 'skills'}` and
`{user_home / '.agents/skills'}`. Read a relevant `SKILL.md` before
following its workflow. Keep credentials in their existing private stores and
resolve them only for an authorized task; never copy keys into instructions,
project metadata, generated context, or Git.

Client setup and project registration do not resume paused work. The Factorio
Companion at
`{user_home / 'Documents/Codex/2026-09-22/ma/outputs/factorio-coop-agent-plan'}`
remains paused unless the user explicitly reopens it. Before work there, read
its `AGENTS.md`, top `HANDOFF.md`, and `docs/handoff-2026-09-27-paused.md`; do not
start its game, workers, model calls, or deploy helpers merely because the
project is available in a new client.
{END}"""


def merge(existing, block):
    starts, ends = existing.count(BEGIN), existing.count(END)
    if starts != ends or starts > 1:
        raise ValueError("Shared-context markers are incomplete or duplicated; preserve AGENTS.md and repair them explicitly.")
    if starts:
        start = existing.index(BEGIN)
        end = existing.index(END)
        if end < start:
            raise ValueError("Shared-context markers are out of order; AGENTS.md was not changed.")
        return existing[:start] + block + existing[end + len(END):]
    separator = "" if not existing or existing.endswith("\n") else "\n"
    return existing + separator + block + "\n"


def read_existing(path):
    if path.is_symlink():
        raise ValueError("AGENTS.md is a symlink; update its existing owner instead of replacing it.")
    return path.read_bytes().decode("utf-8") if path.exists() else ""


def configure(codex_home, check=False, dry_run=False):
    path = codex_home / "AGENTS.md"
    original = read_existing(path)
    updated = merge(original, managed_block(codex_home))
    if original == updated:
        print("Shared Codex knowledge guidance is current.")
        return 0
    if check or dry_run:
        print("Shared Codex knowledge guidance would be updated.")
        return 1 if check else 0
    codex_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_fd = os.open(codex_home / ".weasel-os-context.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Cooperating activations serialize; also preserve intervening edits by
        # clients or the user instead of replacing a stale initial read.
        original = read_existing(path)
        updated = merge(original, managed_block(codex_home))
        if original == updated:
            return 0
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=codex_home, prefix=".AGENTS-weasel-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(updated.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(mode)
            if read_existing(path) != original:
                raise ValueError("AGENTS.md changed during activation; preserve it and rerun the context merge.")
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    print("Updated the managed knowledge block in global Codex instructions.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))))
    parser.add_argument("--check", action="store_true", help="Report drift without writing anything")
    parser.add_argument("--dry-run", action="store_true", help="Describe a change without writing anything")
    args = parser.parse_args()
    try:
        return configure(args.codex_home.expanduser().absolute(), check=args.check, dry_run=args.dry_run)
    except (OSError, UnicodeError, ValueError) as error:
        # Errors concern paths and managed markers; never read or print config,
        # credentials, or memory content as part of this activation.
        print(str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
