#!/usr/bin/env python3
"""Parse the exact generated candidate Niri configuration as an ordinary user.

The fixture contains generated Home Manager files and frozen candidate DMS
files. This gate never launches a compositor or connects to the live session.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

STORE_ROOT = Path("/nix/store")
MAIN_NIRI = Path("/home/evilweasel/weasel-os/programs/niri")
MAXIMUM_FILE = 4 * 1024 * 1024
MAXIMUM_FILES = 256


class NiriGateError(RuntimeError):
    def __init__(self, message, receipt=None):
        super().__init__(message)
        self.receipt = receipt


def absolute_path(value):
    if not isinstance(value, (str, Path)):
        raise NiriGateError("Expected an absolute filesystem path")
    text = str(value)
    if not text.startswith("/") or "\0" in text or any(part in {".", ".."} for part in text.split("/")):
        raise NiriGateError("Relative or traversing filesystem path refused")
    return Path(text)


def open_parent(path, *, create_missing=False):
    path = absolute_path(path)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parent.parts[1:]:
            try:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create_missing:
                    raise
                os.mkdir(component, 0o700, dir_fd=fd)
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise


def read_file(path, *, immutable=False):
    parent = open_parent(path)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAXIMUM_FILE:
            raise NiriGateError("Configuration source is not a bounded regular file")
        if immutable and stat.S_IMODE(before.st_mode) & 0o222:
            raise NiriGateError("Store configuration source is writable")
        parts = []
        size = 0
        while True:
            part = os.read(fd, min(65536, MAXIMUM_FILE + 1 - size))
            if not part:
                break
            parts.append(part)
            size += len(part)
            if size > MAXIMUM_FILE:
                raise NiriGateError("Configuration source grew beyond its bound")
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after):
            raise NiriGateError("Configuration source changed while being copied")
        return b"".join(parts)
    finally:
        os.close(fd)


def store_path(value):
    path = absolute_path(value)
    try:
        relative = path.relative_to(STORE_ROOT)
    except ValueError as exc:
        raise NiriGateError("Configuration source is outside the immutable Store") from exc
    if not relative.parts or not re.fullmatch(r"[0-9a-z]{32}-[A-Za-z0-9.+_?=-]+", relative.parts[0]):
        raise NiriGateError("Malformed Store path")
    return path


def source_bytes(value, frozen_source):
    """Follow Store-only links, redirecting Main Niri links before reading Main."""
    path = store_path(value)
    for _ in range(40):
        relative = path.relative_to(STORE_ROOT)
        current = STORE_ROOT
        for index, component in enumerate(relative.parts):
            current /= component
            info = current.lstat()
            if not stat.S_ISLNK(info.st_mode):
                continue
            link = os.readlink(current)
            # Sources must use explicit absolute links. Existing HM DMS links do.
            target = absolute_path(link)
            tail = relative.parts[index + 1:]
            target = target.joinpath(*tail)
            if target.is_relative_to(MAIN_NIRI):
                suffix = target.relative_to(MAIN_NIRI)
                if not suffix.parts:
                    raise NiriGateError("Main Niri directory link is not a configuration file")
                return read_file(frozen_source / "programs/niri" / suffix), "frozen-source"
            path = store_path(target)
            break
        else:
            return read_file(path, immutable=True), "immutable-store"
    raise NiriGateError("Store configuration symlink chain exceeds its bound")


def evaluation_expression(source):
    uri = json.dumps("path:" + str(absolute_path(source)))
    return ('let f = builtins.getFlake ' + uri + '; c = f.nixosConfigurations.nixy-laptop.config; '
            'files = c.home-manager.users.evilweasel.xdg.configFile; '
            'names = builtins.filter (name: builtins.substring 0 5 name == "niri/" '
            '&& (files.${name}.enable or true)) (builtins.attrNames files); '
            'in builtins.toJSON { app = toString c.programs.niri.package; '
            'sources = builtins.listToAttrs (map (name: { inherit name; value = toString files.${name}.source; }) names); }')


def private_environment(run_dir, nix):
    paths = {name: run_dir / name for name in ("home", "cache", "data", "state", "runtime")}
    for path in paths.values():
        path.mkdir(mode=0o700)
    return {"HOME": str(paths["home"]), "XDG_CONFIG_HOME": str(run_dir / "fixture"),
            "XDG_CACHE_HOME": str(paths["cache"]), "XDG_DATA_HOME": str(paths["data"]),
            "XDG_STATE_HOME": str(paths["state"]), "XDG_RUNTIME_DIR": str(paths["runtime"]),
            "PATH": str(Path(nix).parent), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def trusted_nix():
    found = shutil.which("nix")
    if not found:
        raise NiriGateError("Nix evaluator is unavailable")
    pinned = Path(found).parent.resolve() / Path(found).name
    store_path(pinned)
    store_path(pinned.resolve())
    return str(pinned)


def run_command(argv, environment, directory, *, timeout):
    try:
        result = subprocess.run(argv, env=environment, cwd=directory, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise NiriGateError("Configuration gate command exceeded its time bound") from exc
    return result


def validation_arguments(executable, config):
    return [str(executable), "validate", "--config", str(config)]


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def probe(source, run_dir):
    if os.getuid() == 0 or os.geteuid() == 0 or os.getuid() != os.geteuid():
        raise NiriGateError("Niri configuration gate requires an ordinary user")
    source, run_dir = absolute_path(source), absolute_path(run_dir)
    source_parent = open_parent(source)
    try:
        source_fd = os.open(source.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=source_parent)
        os.close(source_fd)
    finally:
        os.close(source_parent)
    parent = open_parent(run_dir, create_missing=True)
    try:
        try:
            os.mkdir(run_dir.name, 0o700, dir_fd=parent)
        except FileExistsError as exc:
            raise NiriGateError("Niri fixture path must be fresh") from exc
    finally:
        os.close(parent)
    receipt = {"schema": 1, "kind": "niri", "ok": False, "coverage": "config-parse-only; hardware, rendering and live session unobserved"}
    try:
        nix = trusted_nix()
        environment = private_environment(run_dir, nix)
        fixture = run_dir / "fixture"
        fixture.mkdir(mode=0o700)
        lock_before = read_file(source / "flake.lock")
        evaluated = run_command([nix, "eval", "--raw", "--impure", "--no-write-lock-file", "--expr", evaluation_expression(source)],
                                environment, run_dir, timeout=600)
        if evaluated.returncode:
            raise NiriGateError("Generated Niri configuration evaluation failed")
        if read_file(source / "flake.lock") != lock_before:
            raise NiriGateError("Niri evaluation changed candidate flake.lock")
        if len(evaluated.stdout) > 1024 * 1024:
            raise NiriGateError("Generated Niri configuration metadata exceeds its bound")
        metadata = json.loads(evaluated.stdout)
        if not isinstance(metadata, dict) or set(metadata) != {"app", "sources"}:
            raise NiriGateError("Unexpected generated Niri configuration metadata")
        app = store_path(metadata["app"])
        if app.parent != STORE_ROOT or app.is_symlink() or not app.is_dir():
            raise NiriGateError("Niri package is not an immutable Store root")
        if stat.S_IMODE(app.stat().st_mode) & 0o222:
            raise NiriGateError("Niri package Store root is writable")
        executable = app / "bin/niri"
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise NiriGateError("Built Niri executable is unavailable")
        store_path(executable.resolve())
        sources = metadata["sources"]
        if not isinstance(sources, dict) or not 0 < len(sources) <= MAXIMUM_FILES or "niri/config.kdl" not in sources:
            raise NiriGateError("Generated Niri files are incomplete or exceed their bound")
        hashes, origins = {}, {}
        for name, value in sorted(sources.items()):
            if not isinstance(name, str) or not re.fullmatch(r"niri/[A-Za-z0-9_./-]+", name) or any(p in {"", ".", ".."} for p in name.split("/")):
                raise NiriGateError("Generated Niri target escapes the private fixture")
            relative = name.removeprefix("niri/")
            data, origin = source_bytes(value, source)
            target = fixture / relative
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            write_private(target, data)
            hashes[relative] = hashlib.sha256(data).hexdigest()
            origins[relative] = origin
        receipt.update(app=str(app), files=hashes, file_origins=origins)
        validated = run_command(validation_arguments(executable, fixture / "config.kdl"), environment, run_dir, timeout=60)
        write_private(run_dir / "validate.stdout", validated.stdout)
        write_private(run_dir / "validate.stderr", validated.stderr)
        if validated.returncode:
            raise NiriGateError("Generated Niri configuration validation failed (exit " + str(validated.returncode) + ")")
        receipt.update(ok=True, validation_exit_code=0, receipt_path=str(run_dir / "receipt.json"))
        return receipt
    except (OSError, ValueError, RuntimeError) as exc:
        receipt["error"] = str(exc)[:300] if isinstance(exc, NiriGateError) else "Niri configuration fixture could not be verified"
        raise NiriGateError(receipt["error"], receipt=receipt) from exc
    finally:
        write_private(run_dir / "receipt.json", (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = probe(args.source, args.run_dir)
    except (NiriGateError, OSError, ValueError) as exc:
        receipt = getattr(exc, "receipt", None)
        print(json.dumps(receipt if receipt is not None else {"ok": False, "kind": "niri", "error": "Niri configuration gate refused"}))
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
