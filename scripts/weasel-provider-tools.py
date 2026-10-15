#!/usr/bin/env python3
"""Prepare reviewed Namespace closures; select providers for NEW processes only.

No downloading, building, shell/profile edits, service control or process restart.
The caller supplies the independently reviewed CI receipt hash and source commit.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

STORE = re.compile(r"/nix/store/[0-9a-z]{32}-[A-Za-z0-9+._?=-]+\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
NAR = re.compile(r"sha256-[A-Za-z0-9+/]{43}=\Z")
NAMES = ("codex", "codex-code-mode-host", "codex-acp", "claude")


class Rejected(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(*args):
    return subprocess.check_output(args, text=True, timeout=1800).strip()


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and info.st_mode & 0o077 == 0, "state directory must be private and owned")


@contextlib.contextmanager
def locked(state):
    private_directory(state)
    fd = os.open(state / "update.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and info.st_mode & 0o077 == 0, "invalid update lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def atomic_bytes(path, value):
    fd, temporary = tempfile.mkstemp(prefix=".receipt-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def atomic_json(path, value):
    atomic_bytes(path, (json.dumps(value, sort_keys=True, indent=2) + "\n").encode())


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def link_target(path):
    if not os.path.lexists(path):
        return None
    require(path.is_symlink(), "selector must be a symlink")
    value = os.readlink(path)
    require(STORE.fullmatch(value) is not None, "selector must name an exact Store root")
    return value


def atomic_link(path, target):
    temporary = path.parent / ("." + path.name + "-" + os.urandom(12).hex())
    try:
        temporary.symlink_to(target)
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.lexists(temporary):
            temporary.unlink()


def verify_receipt(receipt, source):
    require(receipt.get("schema") == 1 and receipt.get("repository") == "morrowbyte/weasel-os"
            and receipt.get("system") == "x86_64-linux", "wrong receipt identity")
    require(COMMIT.fullmatch(source) is not None and receipt.get("sourceCommit") == source,
            "reviewed source commit mismatch")
    require(type(receipt.get("ciRunId")) is int and receipt["ciRunId"] > 0,
            "missing Namespace run identity")
    require(receipt.get("role") in ("baseline", "candidate"), "missing bundle role")
    for name in ("archiveSha256", "bundleManifestSha256"):
        require(isinstance(receipt.get(name), str) and HEX.fullmatch(receipt[name]),
                "invalid " + name)
    require(isinstance(receipt.get("storePath"), str) and STORE.fullmatch(receipt["storePath"]),
            "invalid Store root")
    require(isinstance(receipt.get("narHash"), str) and NAR.fullmatch(receipt["narHash"]),
            "invalid Store NAR hash")


def verify_bundle(receipt):
    root = Path(receipt["storePath"])
    require(root.is_dir() and not root.is_symlink(), "provider bundle not imported")
    raw = (root / "provider-tools.json").read_bytes()
    require(sha(raw) == receipt["bundleManifestSha256"], "provider manifest changed")
    metadata = json.loads(raw)
    require(metadata.get("schema") == 1 and metadata.get("system") == "x86_64-linux",
            "wrong provider bundle schema")
    require(metadata.get("role") == receipt["role"], "bundle role mismatch")
    require(metadata == receipt.get("providers"), "provider provenance differs from CI receipt")
    codex = metadata["codex"]
    require(COMMIT.fullmatch(codex["sourceRevision"]) is not None,
            "missing patched Codex source revision")
    require(set(codex["patches"]) == {"codex-v0162-scoped-cancel.patch", "scoped-cancel-memory-tests.patch"}
            and all(HEX.fullmatch(value) for value in codex["patches"].values()),
            "both qualified Codex patches are required")
    require(metadata["acp"]["codexPath"] == codex["storePath"] + "/bin/codex",
            "ACP does not select the same Codex generation")
    require(metadata["claude"]["recipe"] == "locked-stable-nixpkgs/claude-code",
            "Claude recipe identity changed")
    expected = {
        "codex": codex["storePath"], "codex-code-mode-host": codex["storePath"],
        "codex-acp": metadata["acp"]["storePath"], "claude": metadata["claude"]["storePath"],
    }
    for name, package in expected.items():
        require(STORE.fullmatch(package) is not None, "invalid provider package root")
        binary = root / "bin" / name
        require(binary.is_symlink() and os.readlink(binary) == package + "/bin/" + name
                and os.access(binary, os.X_OK), "provider executable identity changed: " + name)
    require(run("nix", "hash", "path", "--type", "sha256", "--sri", str(root)) == receipt["narHash"],
            "bundle NAR hash changed")
    paths = run("nix-store", "--query", "--requisites", str(root)).splitlines()
    require(str(root) in paths and all(STORE.fullmatch(path) for path in paths),
            "incomplete provider closure")
    for path in paths:
        run("nix-store", "--verify-path", path)


def prepare(args, state):
    raw = args.receipt.read_bytes()
    require(HEX.fullmatch(args.receipt_sha256) and sha(raw) == args.receipt_sha256,
            "reviewed receipt hash mismatch")
    receipt = json.loads(raw)
    verify_receipt(receipt, args.source_commit)
    with locked(state):
        require(not (state / "transaction.json").exists(), "activation recovery is required")
        for child in ("prepared", "gcroots"):
            private_directory(state / child)
        # Snapshot and hash the staged archive into private state before import;
        # the caller's artifact cannot be swapped between hashing and reading.
        with tempfile.TemporaryDirectory(prefix=".prepare-", dir=state) as work:
            archive = Path(work) / "closure.nar.zst"
            digest = hashlib.sha256()
            with args.archive.open("rb") as source, archive.open("xb") as output:
                while block := source.read(1024 * 1024):
                    output.write(block)
                    digest.update(block)
            require(digest.hexdigest() == receipt["archiveSha256"], "closure archive hash mismatch")
            with subprocess.Popen(["zstd", "--decompress", "--stdout", str(archive)],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as decoder:
                try:
                    subprocess.run(["nix-store", "--import"], stdin=decoder.stdout,
                                   stdout=subprocess.DEVNULL, check=True, timeout=1800)
                    decoder.stdout.close()
                    require(decoder.wait(timeout=30) == 0, "closure decompression failed")
                finally:
                    if decoder.poll() is None:
                        decoder.kill()
            verify_bundle(receipt)
        root = receipt["storePath"]
        run("nix-store", "--add-root", str(state / "gcroots" / Path(root).name), "--indirect",
            "--realise", root, "--option", "max-jobs", "0", "--option", "builders", "",
            "--option", "substitute", "false")
        atomic_bytes(state / "prepared" / (args.receipt_sha256 + ".json"), raw)
    return {"prepared": args.receipt_sha256, "storePath": root, "selectedUnchanged": True}


def selected_receipt(state, identifier):
    require(HEX.fullmatch(identifier) is not None, "invalid prepared receipt ID")
    path = state / "prepared" / (identifier + ".json")
    raw = path.read_bytes()
    require(sha(raw) == identifier, "prepared CI receipt changed")
    receipt = json.loads(raw)
    verify_receipt(receipt, receipt.get("sourceCommit", ""))
    verify_bundle(receipt)
    return receipt


def activate(args, state):
    require(state.is_dir() and not state.is_symlink(), "no prepared provider state")
    with locked(state):
        private_directory(state / "prepared")
        require(not (state / "transaction.json").exists(), "activation recovery is required")
        old = link_target(state / "current")
        prior = link_target(state / "previous")
        if args.command == "rollback":
            require(prior is not None and prior != old, "no distinct rollback generation")
            candidates = []
            for path in (state / "prepared").glob("*.json"):
                value = json.loads(path.read_bytes())
                if value.get("storePath") == prior:
                    candidates.append(path.stem)
            require(candidates, "rollback receipt is missing")
            # Several reviewed runs can produce the same immutable root.
            receipt = selected_receipt(state, sorted(candidates)[-1])
        else:
            receipt = selected_receipt(state, args.receipt_id)
        target = receipt["storePath"]
        require(old is not None or receipt["role"] == "baseline",
                "first select a qualified baseline to retain a real rollback generation")
        if old is None:
            # Bootstrap BEFORE installing the stable launchers. A newly built
            # version cannot masquerade as the machine's existing baseline.
            for name in ("codex", "claude", "codex-acp"):
                existing = shutil.which(name)
                require(existing is not None and Path(existing).resolve(strict=True)
                        == (Path(target) / "bin" / name).resolve(strict=True),
                        "bootstrap baseline differs from selected executable: " + name)
        if old == target:
            return {"current": old, "changed": False}
        journal = {"old": old, "previous": prior, "target": target}
        atomic_json(state / "transaction.json", journal)
        try:
            if old is not None:
                atomic_link(state / "previous", old)
            atomic_link(state / "current", target)
        except BaseException:
            # A pending journal is deliberately retained on any partial change;
            # status exposes it and later activations fail closed for Root review.
            raise
        (state / "transaction.json").unlink()
        sync_directory(state)
        return {"current": target, "previous": old, "changed": True,
                "newProcessesOnly": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path,
                        default=Path.home() / ".local/state/weasel-provider-tools")
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("prepare")
    setup.add_argument("--receipt", type=Path, required=True)
    setup.add_argument("--receipt-sha256", required=True)
    setup.add_argument("--source-commit", required=True)
    setup.add_argument("--archive", type=Path, required=True)
    commands.add_parser("status")
    switch = commands.add_parser("activate")
    switch.add_argument("receipt_id")
    commands.add_parser("rollback")
    args = parser.parse_args()
    try:
        require(args.state_dir.is_absolute(), "state directory must be absolute")
        if args.command == "status":
            state = args.state_dir
            if not state.exists():
                result = {"current": None, "previous": None, "prepared": []}
            else:
                info = state.lstat()
                require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                        and info.st_mode & 0o077 == 0, "invalid state directory")
                result = {"current": link_target(state / "current"),
                          "previous": link_target(state / "previous"),
                          "prepared": sorted(p.stem for p in (state / "prepared").glob("*.json")),
                          "recoveryRequired": (state / "transaction.json").exists()}
                if result["current"] is not None:
                    root = Path(result["current"])
                    result["selectedExecutables"] = {
                        name: str((root / "bin" / name).resolve(strict=True)) for name in NAMES
                    }
                    result["declaredProviders"] = json.loads((root / "provider-tools.json").read_bytes())
        elif args.command == "prepare":
            result = prepare(args, args.state_dir)
        else:
            result = activate(args, args.state_dir)
        print(json.dumps(result, sort_keys=True))
    except (Rejected, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, "provider tools refused: " + str(error) + "\n")


if __name__ == "__main__":
    main()
