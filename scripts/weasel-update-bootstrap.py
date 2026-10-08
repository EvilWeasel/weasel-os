#!/usr/bin/env python3
"""One-time installation of the exact reviewed daily-update system closure.

Run the immutable Nix-store wrapper from a normal host terminal with sudo.
The receipt never supplies commands, repositories or verifier locations.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

SPEC = importlib.util.spec_from_file_location("weasel_update_activation", Path(__file__).resolve().with_name("weasel-update-activate.py"))
a = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = a
SPEC.loader.exec_module(a)

RECEIPT_KEYS = {"schema", "commit", "old_system", "new_system", "manifest"}
BOOTSTRAP_TAG = "weasel-daily-bootstrap-v1"


def validate_receipt(data):
    if len(data) > 8 * 1024 * 1024:
        raise a.ActivationError("Bootstrap receipt exceeds its size bound")
    value = a.json_object(data)
    if not isinstance(value, dict) or set(value) != RECEIPT_KEYS or type(value["schema"]) is not int or value["schema"] != 1:
        raise a.ActivationError("Unexpected bootstrap receipt schema")
    if not isinstance(value["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value["commit"]):
        raise a.ActivationError("Bootstrap requires a complete signed commit ID")
    a.valid_system(value["old_system"])
    a.valid_system(value["new_system"])
    if value["old_system"] == value["new_system"]:
        raise a.ActivationError("Bootstrap system equals its baseline")
    manifest = value["manifest"]
    if not isinstance(manifest, dict) or set(manifest) != {"head", "index", "files"} or manifest["head"] != value["commit"]:
        raise a.ActivationError("Unexpected bootstrap source manifest")
    if not isinstance(manifest["index"], str) or not re.fullmatch(r"[0-9a-f]{64}", manifest["index"]):
        raise a.ActivationError("Invalid bootstrap index manifest")
    if not isinstance(manifest["files"], dict) or not manifest["files"]:
        raise a.ActivationError("Bootstrap source manifest is empty")
    for name, entry in manifest["files"].items():
        if (not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts
                or not name or name == ".git" or name.startswith(".git/")):
            raise a.ActivationError("Unsafe bootstrap source path")
        if (not isinstance(entry, dict) or set(entry) != {"sha256", "mode"}
                or not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                or type(entry["mode"]) is not int or not 0 <= entry["mode"] <= 0o777):
            raise a.ActivationError("Bootstrap manifest only permits normal committed files")
    return value


def load_receipt(path):
    path = Path(path)
    if path.parent != Path("/nix/store") or not re.fullmatch(r"[0-9a-z]{32}-[A-Za-z0-9.+_-]+\.json", path.name):
        raise a.ActivationError("Bootstrap receipt must be an immutable Nix-store JSON file")
    data, info = a.read_regular(path, maximum=8 * 1024 * 1024, expected_uid=0, allow_hardlinks=True)
    if info.st_mode & 0o222:
        raise a.ActivationError("Bootstrap receipt is writable")
    return validate_receipt(data)


def signed_head(runner, repository, commit):
    if runner.git(repository, "config", "--get", "user.signingkey").decode().strip().rstrip("!") != a.EXPECTED_PRIMARY_FINGERPRINT:
        raise a.ActivationError("Configured bootstrap signing key changed")
    a.read_object(runner, repository, "commit", commit)
    runner.git(repository, "verify-commit", "--raw", commit)
    signature = runner.git(repository, "show", "-s", "--format=%G? %GF %GP", commit).decode().split()
    if len(signature) != 3 or signature[0] not in {"G", "U"} or signature[2] != a.EXPECTED_PRIMARY_FINGERPRINT:
        raise a.ActivationError("Bootstrap commit has another signer")


def source_checkpoint(runner, repository, receipt):
    full, index = a.repository_manifest(runner, repository, receipt["commit"])
    stage = runner.git(repository, "ls-files", "--stage", "-z")
    manifest = {"head": full["commit"], "index": a.digest(stage),
                "files": {name: {"sha256": entry["sha256"], "mode": entry["mode"]}
                          for name, entry in full["files"].items()}}
    if manifest != receipt["manifest"]:
        raise a.ActivationError("Main source changed after the reviewed bootstrap build")
    return full, index


def preflight(runner, receipt, *, repository=a.REPOSITORY, privileged=True):
    a.check_system(Path(receipt["old_system"]))
    a.check_other_activation()
    if privileged:
        a.check_recovery(a.STATE, read_only=True)
    a.check_remote(runner, repository, receipt["commit"])
    signed_head(runner, repository, receipt["commit"])
    before = source_checkpoint(runner, repository, receipt)
    if not (Path(receipt["new_system"]) / "bin/switch-to-configuration").is_file():
        raise a.ActivationError("Reviewed bootstrap closure has not been built")
    return before


def assert_unchanged(runner, receipt, expected, repository=a.REPOSITORY):
    actual = source_checkpoint(runner, repository, receipt)
    if actual != expected:
        raise a.ActivationError("Concurrent source/index save retained; bootstrap stopped")
    a.check_system(Path(receipt["old_system"]))
    a.check_other_activation()
    a.check_remote(runner, repository, receipt["commit"])


def reproduce(runner, receipt, expected, repository=a.REPOSITORY):
    # Evaluate only as the ordinary user, using the committed Git-flake filter.
    result = runner.user("nix", ["eval", "--no-write-lock-file", "--raw",
                                str(repository) + "#nixosConfigurations.nixy-laptop.config.system.build.toplevel.outPath"]).decode().strip()
    if result != receipt["new_system"]:
        raise a.ActivationError("Reviewed main does not reproduce the exact bootstrap closure")
    assert_unchanged(runner, receipt, expected, repository)


def checkpoint(runner, receipt):
    a.check_space(50 * a.GIB)
    mount = a.json_object(runner.root("findmnt", ["--json", "--target", "/home", "--output", "TARGET,FSTYPE"]))
    rows = mount.get("filesystems", [])
    if len(rows) != 1 or rows[0].get("target") != "/home" or rows[0].get("fstype") != "btrfs":
        raise a.ActivationError("Bootstrap Home must be a Btrfs mount")
    runner.root("btrfs", ["subvolume", "show", "/home/.snapshots"])
    number = runner.root("snapper", ["-c", "home", "create", "--type", "single", "--print-number",
                                   "--description", "Before verified daily-update bootstrap " + receipt["commit"][:12],
                                   "--userdata", "weasel-bootstrap=yes,weasel-bootstrap-commit=" + receipt["commit"]]).decode().strip()
    if not re.fullmatch(r"[1-9][0-9]*", number):
        raise a.ActivationError("Bootstrap Snapper checkpoint ID is invalid")
    path = Path("/home/.snapshots") / number / "snapshot"
    runner.root("btrfs", ["subvolume", "show", path])
    if runner.root("btrfs", ["property", "get", "-ts", path, "ro"]).decode().strip() != "ro=true":
        raise a.ActivationError("Bootstrap Home checkpoint is not read-only")
    return int(number)


def health(runner, receipt):
    runner.root("systemctl", ["is-active", "--quiet", "NetworkManager", "systemd-resolved", "netbird-personal"])
    runner.root("getent", ["hosts", "github.com"])
    runner.root("systemctl", ["is-active", "--quiet", "weasel-update-activate.path"])
    exact_helper = Path(receipt["new_system"]) / "sw/bin/weasel-update"
    status = a.json_object(runner.user(str(exact_helper), ["--status"], timeout=120))
    if status.get("schema") != 1 or status.get("phase") in {"not-installed", "blocked", "recovery-required"}:
        raise a.ActivationError("Installed normal-user helper status did not pass")


def install(runner, receipt, expected, run, receipt_path, *, repository=a.REPOSITORY):
    record = {"schema": 1, "marker": BOOTSTRAP_TAG, "commit": receipt["commit"],
              "old_system": receipt["old_system"], "new_system": receipt["new_system"], "receipt": str(receipt_path)}
    identifier = "bootstrap-" + receipt["commit"][:12]
    def journal(phase, **fields):
        record.update(phase=phase, **fields)
        a.atomic_write(run / "journal.json", a.encoded(record))
        a.write_status("running", identifier, phase)
    journal("bootstrap-preparing")
    attempted = False
    try:
        reproduce(runner, receipt, expected, repository)
        a.check_power()
        a.check_space(65 * a.GIB)
        assert_unchanged(runner, receipt, expected, repository)
        journal("bootstrap-checkpoint-creating")
        number = checkpoint(runner, receipt)
        journal("checkpoint-created", snapshot=number)
        assert_unchanged(runner, receipt, expected, repository)
        a.check_power()
        a.check_space(50 * a.GIB)
        for label, system in [("old-system", receipt["old_system"]), ("tested-system", receipt["new_system"])]:
            runner.root("nix-store", ["--add-root", run / label, "--indirect", "--realise", system])
        assert_unchanged(runner, receipt, expected, repository)
        journal("activating")
        attempted = True
        a.activate_exact(runner, Path(receipt["new_system"]))
        health(runner, receipt)
        if source_checkpoint(runner, repository, receipt) != expected:
            raise a.ActivationError("Concurrent source save retained during bootstrap")
        journal("complete")
        a.write_status("installed", identifier, "complete", system=receipt["new_system"], snapshot=number,
                       note="Root activation path verified; daily T3 schedule remains separately controlled")
        return {"schema": 1, "ok": True, "system": receipt["new_system"], "snapshot": number,
                "root_activation_observed": True, "scheduler_enabled": False}
    except Exception as exc:
        if attempted:
            journal("rolling-back-system", error=type(exc).__name__)
            try:
                a.activate_exact(runner, Path(receipt["old_system"]))
                journal("recovery-required", system_rollback="complete", home_rollback=False)
            except Exception as rollback_error:
                journal("recovery-required", system_rollback="failed", rollback_error=type(rollback_error).__name__, home_rollback=False)
        else:
            journal("failed-before-integration" if record["phase"] == "bootstrap-preparing" else "recovery-required", error=type(exc).__name__)
        a.write_status("blocked", identifier, record["phase"], reason=str(exc)[:400])
        raise


def retryable_journal(run):
    data, _ = a.read_regular(run / "journal.json", maximum=8 * 1024 * 1024)
    record = a.json_object(data)
    if (record.get("marker") != BOOTSTRAP_TAG or record.get("commit") != run.name
            or record.get("phase") != "failed-before-integration"):
        raise a.RecoveryRequired("Bootstrap receipt was already attempted; inspect its retained journal")
    return data


class UserRunner(a.Runner):
    """Unprivileged receipt inspection is explicitly unable to run root commands."""
    def user(self, name, arguments, *, cwd=None, extra_env=None, timeout=10800):
        if os.getuid() != self.account.pw_uid:
            raise a.ActivationError("Verify the receipt as the designated normal user")
        env = {"HOME": self.account.pw_dir, "USER": self.account.pw_name, "LOGNAME": self.account.pw_name,
               "PATH": self.user_path, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1"}
        if extra_env:
            env.update(extra_env)
        argv = [self.executable("env"), "-i", *[key + "=" + value for key, value in env.items()],
                self.executable(name), *map(str, arguments)]
        return self.run(argv, cwd=cwd, timeout=timeout)

    def root(self, *args, **kwargs):
        raise a.ActivationError("Receipt inspection has no privileged execution capability")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="Root read-only source and exact-closure validation")
    modes.add_argument("--verify-receipt", action="store_true", help="Normal-user receipt/source inspection; proves no privileged activation")
    args = parser.parse_args()
    if os.uname().nodename != a.HOST:
        raise a.ActivationError("Bootstrap belongs to nixy-laptop")
    receipt = load_receipt(args.receipt)
    if args.verify_receipt:
        if os.geteuid() == 0:
            raise a.ActivationError("Use --verify-receipt as the normal user")
        runner = UserRunner()
        preflight(runner, receipt, privileged=False)
        print(json.dumps({"schema": 1, "ok": True, "commit": receipt["commit"], "receipt_verified": True,
                          "new_system": receipt["new_system"], "root_activation_observed": False,
                          "exact_source_evaluation": False, "root_recovery_checked": False}))
        return 0
    if os.geteuid() != 0:
        raise a.ActivationError("Run the immutable bootstrap wrapper with sudo from the normal host terminal")
    runner = a.Runner()
    expected = preflight(runner, receipt)
    if args.check:
        reproduce(runner, receipt, expected)
        print(json.dumps({"schema": 1, "ok": True, "new_system": receipt["new_system"],
                          "exact_source_evaluation": True, "root_activation_observed": False}))
        return 0
    a.ensure_directory(a.STATE, mode=0o711)
    a.ensure_directory(a.STATUS.parent, mode=0o755)
    parent = a.ensure_directory(a.STATE / "bootstrap")
    lock = os.open(a.STATE / "activation.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # State and source may have changed while waiting for the privileged lock.
        expected = preflight(runner, receipt)
        run = parent / receipt["commit"]
        try:
            run.mkdir(mode=0o700)
        except FileExistsError:
            a.ensure_directory(run)
            previous = retryable_journal(run)
            a.atomic_write(run / ("failed-attempt-" + uuid.uuid4().hex + ".json"), previous)
        a.sync_directory(parent)
        result = install(runner, receipt, expected, run, args.receipt)
    finally:
        os.close(lock)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schema": 1, "ok": False, "error": str(exc)[:400]}), file=sys.stderr)
        sys.exit(1)
