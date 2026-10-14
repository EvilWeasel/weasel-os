#!/usr/bin/env python3
"""Activate a reviewed Namespace-built laptop closure without evaluating Nix."""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

SPEC = importlib.util.spec_from_file_location("weasel_prebuilt_activation", Path(__file__).resolve().with_name("weasel-update-activate.py"))
a = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = a
SPEC.loader.exec_module(a)

BASELINE = "54c1c00364bfffc23307d8e0521f65facaf4f106"
BASELINE_SYSTEM = "/nix/store/qynkf7gqhwdkixbjiin83gjb9r7wmc57-nixos-system-nixy-laptop-26.05.20261012.7993f34"
LOCK_HASH = "761446d247f2a0c9d3e838c816af187463002094660ef0e8e3a9667aaba83ea4"
ALLOWED = {"hosts/nixy-laptop/config.nix", "hosts/nixy-laptop/home.nix", "profiles/system/laptop.nix",
           "programs/t3code-client.nix", "programs/t3code-fork.nix", "modules/daily-updates.nix",
           "scripts/weasel-update-prebuilt.py", "scripts/test-weasel-update-prebuilt.py", ".github/workflows/namespace.yml"}
FIXTURE_PATH = "packages/computer-use/core/src/main.rs"
ALLOWED.add(FIXTURE_PATH)
FIXTURE_BEFORE = b'        fs::write(&script, b"#!/bin/sh\\nsleep 0.4 &\\nexit 0\\n").unwrap();'
FIXTURE_AFTER = b'        fs::write(&script, b"#!/bin/sh\\ncat >/dev/null\\nsleep 0.4 &\\nexit 0\\n").unwrap();'
KEYS = {"schema", "host", "sourceCommit", "sourceTree", "baselineCommit", "baselineSystem", "systemPath",
        "systemDrv", "flakeLockSha256", "archive", "archiveSha256", "githubRepository", "githubRunId", "githubRunAttempt"}


def validate_receipt(value):
    if not isinstance(value, dict) or set(value) != KEYS or type(value["schema"]) is not int or value["schema"] != 1:
        raise a.ActivationError("Unexpected prebuilt receipt schema")
    if (value["host"] != "nixy-laptop" or value["baselineCommit"] != BASELINE
            or value["baselineSystem"] != BASELINE_SYSTEM or value["flakeLockSha256"] != LOCK_HASH
            or value["githubRepository"] not in {"morrowbyte/weasel-os", "EvilWeasel/weasel-os"}
            or value["archive"] != "nixy-laptop.nar.zst"):
        raise a.ActivationError("Prebuilt receipt is outside the reviewed migration")
    for key in ["sourceCommit", "sourceTree"]:
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{40}", value[key]):
            raise a.ActivationError("Invalid source identity")
    for key in ["archiveSha256"]:
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise a.ActivationError("Invalid archive hash")
    for key in ["githubRunId", "githubRunAttempt"]:
        if not isinstance(value[key], str) or not re.fullmatch(r"[1-9][0-9]*", value[key]):
            raise a.ActivationError("Invalid build run identity")
    a.valid_system(value["systemPath"])
    if not isinstance(value["systemDrv"], str) or not re.fullmatch(r"/nix/store/[a-z0-9]{32}-[^/]+\.drv", value["systemDrv"]):
        raise a.ActivationError("Invalid system derivation")
    if value["systemPath"] == BASELINE_SYSTEM:
        raise a.ActivationError("Prebuilt system does not change the baseline")
    return value


def source_guard(runner, source, receipt):
    root = Path("/home/evilweasel/.t3-morrowbyte/worktrees/weasel-os")
    if source != source.resolve() or not source.is_relative_to(root) or source == root:
        raise a.ActivationError("Source is not an isolated migration worktree")
    def git(*args):
        return runner.git(source, *args).decode().strip()
    if git("rev-parse", "HEAD") != receipt["sourceCommit"] or git("rev-parse", "HEAD^{tree}") != receipt["sourceTree"]:
        raise a.ActivationError("Source identity differs from Namespace receipt")
    if git("show", "-s", "--format=%P", "HEAD") != BASELINE or git("status", "--porcelain", "--untracked-files=all"):
        raise a.ActivationError("Migration candidate must be clean and directly based on active source")
    runner.git(source, "verify-commit", "--raw", "HEAD")
    signature = git("show", "-s", "--format=%G? %GF %GP", "HEAD").split()
    if len(signature) != 3 or signature[0] not in {"G", "U"} or signature[2] != a.EXPECTED_PRIMARY_FINGERPRINT:
        raise a.ActivationError("Migration source signer is not authorized")
    changed = set(git("diff", "--name-only", BASELINE, "HEAD").splitlines())
    if not changed or not changed <= ALLOWED:
        raise a.ActivationError("Migration includes unrelated source changes")
    if FIXTURE_PATH in changed:
        baseline_fixture = runner.git(source, "show", BASELINE + ":" + FIXTURE_PATH)
        candidate_fixture = runner.git(source, "show", "HEAD:" + FIXTURE_PATH)
        if (baseline_fixture.count(FIXTURE_BEFORE) != 1
                or candidate_fixture != baseline_fixture.replace(FIXTURE_BEFORE, FIXTURE_AFTER)):
            raise a.ActivationError("Only the exact stdin-consuming test fixture change is allowed")
    for commit in [BASELINE, "HEAD"]:
        if a.digest(runner.git(source, "show", commit + ":flake.lock")) != LOCK_HASH:
            raise a.ActivationError("Migration changed the active flake lock")


def repository_fingerprint(runner):
    """Observe dirty canonical files; never reset, stage or write them."""
    repo = a.REPOSITORY
    paths = runner.git(repo, "ls-files", "-z").split(b"\0")
    files = []
    for raw in paths:
        if not raw:
            continue
        path = repo / os.fsdecode(raw)
        try:
            info = path.lstat()
            content = os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes()
            files.append((raw.hex(), info.st_ino, info.st_mode, a.digest(content)))
        except FileNotFoundError:
            files.append((raw.hex(), "absent"))
    return a.digest(a.encoded({"head": runner.git(repo, "rev-parse", "HEAD").decode(),
                              "index": a.digest((repo / ".git/index").read_bytes()),
                              "status": runner.git(repo, "status", "--porcelain=v1", "-z").hex(), "files": files}))


def retain_system(path, name):
    root = Path("/nix/var/nix/gcroots") / name
    try:
        root.symlink_to(path)
    except FileExistsError:
        if not root.is_symlink() or os.readlink(root) != str(path):
            raise a.ActivationError("Existing migration GC root differs")


def preflight(runner, source, receipt):
    a.require_switch_checks()
    a.check_system(a.valid_system(BASELINE_SYSTEM))
    a.check_other_activation()
    a.check_recovery(a.STATE, read_only=True)
    a.check_power()
    a.check_space(50 * a.GIB)
    source_guard(runner, source, receipt)
    system = a.valid_system(receipt["systemPath"])
    if not (system / "bin/switch-to-configuration").is_file():
        raise a.ActivationError("Prebuilt system closure is not imported")
    paths = runner.root("nix-store", ["--query", "--requisites", system]).decode().splitlines()
    if str(system) not in paths:
        raise a.ActivationError("Incomplete prebuilt closure")
    # Verification only: never realise, substitute, evaluate or build on the host.
    for offset in range(0, len(paths), 128):
        runner.root("nix-store", ["--verify-path", *paths[offset:offset + 128]])
    return repository_fingerprint(runner)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if os.geteuid() != 0 or not str(Path(__file__).resolve()).startswith("/nix/store/"):
        raise a.ActivationError("Use the immutable prebuilt wrapper as root")
    if not re.fullmatch(r"[0-9a-f]{64}", args.receipt_sha256) or not str(args.receipt).startswith("/nix/store/"):
        raise a.ActivationError("An explicitly pinned immutable receipt is required")
    data, _ = a.read_regular(args.receipt, maximum=65536, expected_uid=0, allow_hardlinks=True)
    if a.digest(data) != args.receipt_sha256:
        raise a.ActivationError("Receipt differs from the reviewed artifact")
    receipt = validate_receipt(a.json_object(data))
    runner = a.Runner()
    a.ensure_directory(a.STATE, mode=0o711)
    lock = os.open(a.STATE / "activation.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original = preflight(runner, args.source, receipt)
        if args.check:
            print(json.dumps({"ok": True, "source": receipt["sourceCommit"], "built_locally": False, "activated": False}))
            return 0
        parent = a.ensure_directory(a.STATE / "runs")
        run = parent / ("prebuilt-" + receipt["sourceCommit"])
        run.mkdir(mode=0o700)  # Existing transactions require explicit recovery review.
        journal = {"marker": "weasel-prebuilt-v1", "phase": "prepared", "receipt": receipt,
                   "receipt_sha256": args.receipt_sha256, "canonical_fingerprint": original, "home_rollback": False}
        def save():
            a.atomic_write(run / "journal.json", a.encoded(journal))
        save()
        switched = False
        try:
            retain_system(BASELINE_SYSTEM, "weasel-prebuilt-baseline-" + receipt["sourceCommit"])
            retain_system(receipt["systemPath"], "weasel-prebuilt-candidate-" + receipt["sourceCommit"])
            bootstrap = a.import_peer("weasel-update-bootstrap.py")
            journal["snapshot"] = bootstrap.checkpoint(runner, {"commit": receipt["sourceCommit"]})
            save()
            source_guard(runner, args.source, receipt)
            if repository_fingerprint(runner) != original:
                raise a.ActivationError("Canonical source changed during preparation")
            a.check_system(a.valid_system(BASELINE_SYSTEM))
            journal["phase"] = "activating"
            save()
            switched = True
            a.activate_exact(runner, a.valid_system(receipt["systemPath"]))
            runner.root("systemctl", ["is-active", "--quiet", "NetworkManager", "systemd-resolved", "netbird-personal"])
            runner.root("getent", ["hosts", "github.com"])
            if repository_fingerprint(runner) != original:
                raise a.ActivationError("Canonical source changed during activation")
            journal["phase"] = "complete"
            save()
        except Exception:
            journal["phase"] = "recovery-required" if switched else "failed-before-integration"
            if switched:
                try:
                    a.activate_exact(runner, a.valid_system(BASELINE_SYSTEM))
                    journal["system_rollback"] = "complete"
                except Exception:
                    journal["system_rollback"] = "failed"
            save()
            raise
        print(json.dumps({"ok": True, "system": receipt["systemPath"], "snapshot": journal["snapshot"], "activated": True}))
    finally:
        os.close(lock)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (a.ActivationError, OSError) as exc:
        print("Prebuilt migration blocked: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
