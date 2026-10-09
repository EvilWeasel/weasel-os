#!/usr/bin/env python3
"""Merge only the managed desktop MCP entry, preserving the mutable Codex config."""
import argparse
import fcntl
import os
from pathlib import Path
import stat
import tempfile
import time
import tomllib

BEGIN = "# weasel-os:computer-use:start"
END = "# weasel-os:computer-use:end"


def merge(original, command):
    starts, ends = original.count(BEGIN), original.count(END)
    if starts != ends or starts > 1:
        raise ValueError("Desktop MCP markers are incomplete or duplicated; configuration preserved")
    if starts:
        start, end = original.index(BEGIN), original.index(END)
        if end < start:
            raise ValueError("Desktop MCP markers are out of order; configuration preserved")
        remainder = original[:start] + original[end + len(END):]
    else:
        remainder = original
    parsed = tomllib.loads(remainder)
    if "weasel_desktop" in parsed.get("mcp_servers", {}):
        raise ValueError("An unmanaged weasel_desktop MCP entry exists; configuration preserved")
    # The command is a Nix store/per-user absolute path, never a secret.
    import json
    block = f'''{BEGIN}
[mcp_servers.weasel_desktop]
command = {json.dumps(command)}
args = ["mcp"]
startup_timeout_sec = 10
tool_timeout_sec = 135
# Explicitly authorized desktop control, scoped to this owned server.
default_tools_approval_mode = "approve"
{END}'''
    if starts:
        updated = original[:start] + block + original[end + len(END):]
    else:
        updated = original + ("" if not original or original.endswith("\n") else "\n") + "\n" + block + "\n"
    tomllib.loads(updated)
    return updated


def configure(codex_home, command):
    codex_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = codex_home / "config.toml"
    if path.is_symlink():
        raise ValueError("Codex config is a symlink; use its existing declarative owner")
    lock_path = codex_home / ".weasel-computer-use.lock"
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, "a") as lock:
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        original = path.read_text() if path.exists() else ""
        updated = merge(original, command)
        if original == updated:
            print("Desktop MCP configuration is current.")
            return
        backup_dir = codex_home / "private-backups"
        if backup_dir.exists() or backup_dir.is_symlink():
            info = backup_dir.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError("Private backup path is not an owned directory; configuration preserved")
        backup_dir.mkdir(mode=0o700, exist_ok=True)
        os.chmod(backup_dir, 0o700)
        if path.exists():
            backup = backup_dir / f"config-before-desktop-{time.time_ns()}.toml"
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=codex_home, prefix=".desktop-mcp-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(updated)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600)
            if (path.read_text() if path.exists() else "") != original:
                raise ValueError("Codex configuration changed during merge; rerun without overwriting")
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    print("Configured the desktop MCP entry; unrelated configuration was preserved.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--command", required=True)
    args = parser.parse_args()
    try:
        configure(args.codex_home, args.command)
    except (OSError, ValueError) as error:
        # TOML parse messages can contain the original input; don't expose it.
        if isinstance(error, tomllib.TOMLDecodeError):
            print("Existing Codex TOML could not be parsed; it was preserved.")
        else:
            print(str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
