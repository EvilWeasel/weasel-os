#!/usr/bin/env python3
"""Bootstrap policy and failure tests; root commands are recording fixtures only."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("bootstrap", Path(__file__).resolve().parents[1] / "scripts/weasel-update-bootstrap.py")
b = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = b
SPEC.loader.exec_module(b)
a = b.a


class FixtureRunner:
    def __init__(self, ro="ro=true", fail_health=False):
        self.account = types.SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
        self.calls = []
        self.ro = ro
        self.fail_health = fail_health

    def git(self, repository, *args, extra_env=None):
        env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1")
        result = subprocess.run(["git", "--no-replace-objects", "-c", "core.hooksPath=/dev/null", "-C", str(repository), *map(str, args)],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode:
            raise a.ActivationError("Fixture Git refused operation")
        return result.stdout

    def root(self, name, args, **kwargs):
        self.calls.append((name, [str(value) for value in args]))
        if name == "findmnt":
            return b'{"filesystems":[{"target":"/home","fstype":"btrfs"}]}'
        if name == "snapper":
            return b"11\n"
        if name == "btrfs" and args[0] == "property":
            return self.ro.encode()
        if self.fail_health and name == "getent":
            raise a.ActivationError("Fixture DNS failure")
        return b""

    def user(self, name, args, **kwargs):
        self.calls.append((name, [str(value) for value in args]))
        return a.encoded({"schema": 1, "phase": "activating"})


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="weasel-update-bootstrap-test-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.status = self.root / "status/status.json"
        self.status.parent.mkdir()
        status_patch = patch.object(a, "STATUS", self.status)
        status_patch.start()
        self.addCleanup(status_patch.stop)

    def receipt(self):
        return {"schema": 1, "commit": "a" * 40,
                "old_system": "/nix/store/" + "a" * 32 + "-nixos-system-nixy-laptop-25.11.old",
                "new_system": "/nix/store/" + "b" * 32 + "-nixos-system-nixy-laptop-25.11.new",
                "manifest": {"head": "a" * 40, "index": "b" * 64,
                             "files": {"configuration.nix": {"sha256": "c" * 64, "mode": 0o644}}}}

    def fixture(self, runner=None):
        runner = runner or FixtureRunner()
        repo = self.root / "repository"
        repo.mkdir()
        runner.git(repo, "init", "-b", "main")
        runner.git(repo, "config", "user.name", "Fixture")
        runner.git(repo, "config", "user.email", "fixture@example.invalid")
        runner.git(repo, "config", "commit.gpgsign", "false")
        source = repo / "configuration.nix"
        source.write_bytes(b"{ bootstrap = true; }\n")
        runner.git(repo, "add", ".")
        runner.git(repo, "commit", "-m", "reviewed bootstrap fixture")
        commit = runner.git(repo, "rev-parse", "HEAD").decode().strip()
        full, index = a.repository_manifest(runner, repo, commit)
        receipt = self.receipt()
        receipt["commit"] = commit
        receipt["manifest"] = {"head": commit,
                               "index": a.digest(runner.git(repo, "ls-files", "--stage", "-z")),
                               "files": {name: {"sha256": entry["sha256"], "mode": entry["mode"]}
                                         for name, entry in full["files"].items()}}
        run = self.root / "bootstrap" / commit
        run.mkdir(parents=True)
        return runner, repo, source, receipt, (full, index), run

    def install(self, runner, repo, receipt, expected, run, snapshot=None):
        with patch.object(b, "reproduce"), patch.object(a, "check_power"), patch.object(a, "check_space"), patch.object(a, "check_system"), patch.object(a, "check_other_activation"), patch.object(a, "check_remote"):
            if snapshot is None:
                return b.install(runner, receipt, expected, run, Path("/nix/store/" + "c" * 32 + "-receipt.json"), repository=repo)
            with patch.object(b, "checkpoint", snapshot):
                return b.install(runner, receipt, expected, run, Path("/nix/store/" + "c" * 32 + "-receipt.json"), repository=repo)

    def test_schema_is_fixed_and_no_commands_or_repo_paths_are_accepted(self):
        receipt = self.receipt()
        self.assertEqual(b.validate_receipt(a.encoded(receipt)), receipt)
        for key, value in [("command", "sh"), ("repository", "/tmp/fake"), ("commit", "main"), ("schema", True),
                           ("new_system", "/tmp/fake-system"), ("new_system", receipt["old_system"])]:
            bad = dict(receipt)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(a.ActivationError):
                b.validate_receipt(a.encoded(bad))

    def test_manifest_rejects_traversal_links_and_special_mode_bits(self):
        for files in [{"../secret": {"sha256": "a" * 64, "mode": 0o644}},
                      {"file": {"link": "/etc/shadow"}},
                      {"file": {"sha256": "a" * 64, "mode": 0o4644}}]:
            receipt = self.receipt()
            receipt["manifest"]["files"] = files
            with self.assertRaises(a.ActivationError):
                b.validate_receipt(a.encoded(receipt))
        receipt = self.receipt()
        receipt["manifest"]["files"]["configuration.nix"]["mode"] = 0o444
        b.validate_receipt(a.encoded(receipt))

    def test_receipt_only_uses_an_immutable_root_owned_store_file(self):
        for path in [self.root / "receipt.json", Path("/nix/store/fake.json"),
                     Path("/nix/store/" + "a" * 32 + "-dir/receipt.json")]:
            with self.assertRaises(a.ActivationError):
                b.load_receipt(path)
        valid = Path("/nix/store/" + "a" * 32 + "-receipt.json")
        with patch.object(a, "read_regular", return_value=(a.encoded(self.receipt()), types.SimpleNamespace(st_mode=0o444))) as reader:
            b.load_receipt(valid)
            self.assertEqual(reader.call_args.kwargs["expected_uid"], 0)
            self.assertTrue(reader.call_args.kwargs["allow_hardlinks"])
        with patch.object(a, "read_regular", return_value=(a.encoded(self.receipt()), types.SimpleNamespace(st_mode=0o644))):
            with self.assertRaises(a.ActivationError):
                b.load_receipt(valid)

    def test_duplicate_keys_are_rejected(self):
        with self.assertRaises(a.ActivationError):
            b.validate_receipt(b'{"schema":1,"schema":1}')

    def test_checkpoint_is_distinct_from_daily_cleanup_and_read_only(self):
        runner = FixtureRunner()
        with patch.object(a, "check_space"):
            self.assertEqual(b.checkpoint(runner, self.receipt()), 11)
        call = next(args for name, args in runner.calls if name == "snapper")
        userdata = call[call.index("--userdata") + 1]
        self.assertIn("weasel-bootstrap=yes", userdata)
        self.assertNotIn("weasel-daily-update=yes", userdata)
        with patch.object(a, "check_space"), self.assertRaises(a.ActivationError):
            b.checkpoint(FixtureRunner(ro="ro=false"), self.receipt())

    def test_snapshot_failure_happens_before_any_activation(self):
        runner, repo, source, receipt, expected, run = self.fixture(FixtureRunner(ro="ro=false"))
        original = source.read_bytes()
        with patch.object(a, "activate_exact") as switch, self.assertRaises(a.ActivationError):
            self.install(runner, repo, receipt, expected, run)
        switch.assert_not_called()
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(json.loads((run / "journal.json").read_bytes())["phase"], "recovery-required")

    def test_concurrent_save_after_snapshot_is_retained_and_prevents_switch(self):
        runner, repo, source, receipt, expected, run = self.fixture()
        def concurrent_save(*_args):
            source.write_bytes(b"user editor save\n")
            return 11
        with patch.object(a, "activate_exact") as switch, self.assertRaises(a.ActivationError):
            self.install(runner, repo, receipt, expected, run, concurrent_save)
        switch.assert_not_called()
        self.assertEqual(source.read_bytes(), b"user editor save\n")
        record = json.loads((run / "journal.json").read_bytes())
        self.assertEqual(record["snapshot"], 11)
        self.assertEqual(record["phase"], "recovery-required")

    def test_health_failure_rolls_back_only_system_and_retains_snapshot(self):
        runner, repo, source, receipt, expected, run = self.fixture(FixtureRunner(fail_health=True))
        original = source.read_bytes()
        closures = []
        with patch.object(a, "activate_exact", side_effect=lambda _runner, path: closures.append(str(path))), self.assertRaises(a.ActivationError):
            self.install(runner, repo, receipt, expected, run)
        self.assertEqual(closures, [receipt["new_system"], receipt["old_system"]])
        record = json.loads((run / "journal.json").read_bytes())
        self.assertEqual(record["phase"], "recovery-required")
        self.assertEqual(record["snapshot"], 11)
        self.assertEqual(record["system_rollback"], "complete")
        self.assertFalse(record["home_rollback"])
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(any("delete" in args or "rollback" in args for name, args in runner.calls if name == "snapper"))

    def test_success_selects_exact_system_and_observes_path_and_user_helper(self):
        runner, repo, source, receipt, expected, run = self.fixture()
        closures = []
        with patch.object(a, "activate_exact", side_effect=lambda _runner, path: closures.append(str(path))):
            result = self.install(runner, repo, receipt, expected, run)
        self.assertEqual(closures, [receipt["new_system"]])
        self.assertTrue(result["root_activation_observed"])
        self.assertNotIn("scheduler_enabled", result)
        self.assertEqual(result["scheduler_state"], "managed-separately-by-T3")
        self.assertEqual(result["snapshot"], 11)
        self.assertTrue(any(name == "systemctl" and "weasel-update-activate.path" in args for name, args in runner.calls))
        self.assertTrue(any(name == receipt["new_system"] + "/sw/bin/weasel-update" and args == ["--status"] for name, args in runner.calls))
        self.assertEqual(json.loads(self.status.read_bytes())["outcome"], "installed")

    def test_source_checkpoint_detects_hidden_editor_changes(self):
        runner, repo, source, receipt, expected, run = self.fixture()
        runner.git(repo, "update-index", "--assume-unchanged", "configuration.nix")
        source.write_bytes(b"hidden user save\n")
        with self.assertRaises(a.ActivationError):
            b.source_checkpoint(runner, repo, receipt)
        self.assertEqual(source.read_bytes(), b"hidden user save\n")

    def test_exact_evaluation_mismatch_never_counts_as_tested_closure(self):
        runner, repo, source, receipt, expected, run = self.fixture()
        runner.user = lambda *_args, **_kwargs: b"/nix/store/wrong-system"
        with self.assertRaises(a.ActivationError):
            b.reproduce(runner, receipt, expected, repo)

    def test_normal_user_inspector_cannot_run_privileged_commands(self):
        runner = b.UserRunner.__new__(b.UserRunner)
        with self.assertRaises(a.ActivationError):
            runner.root("snapper", ["create"])

    def test_daily_root_recovers_gate_blocks_interrupted_bootstrap(self):
        state = self.root / "state"
        run = state / "bootstrap" / ("a" * 40)
        run.mkdir(parents=True)
        with self.assertRaises(a.RecoveryRequired):
            a.check_recovery(state)
        journal = run / "journal.json"
        for phase in ["bootstrap-preparing", "bootstrap-checkpoint-creating", "checkpoint-created", "activating", "rolling-back-system", "recovery-required"]:
            journal.write_bytes(a.encoded({"marker": b.BOOTSTRAP_TAG, "commit": run.name, "phase": phase}))
            with self.subTest(phase=phase), self.assertRaises(a.RecoveryRequired):
                a.check_recovery(state, read_only=True)
        for phase in ["complete", "failed-before-integration"]:
            journal.write_bytes(a.encoded({"marker": b.BOOTSTRAP_TAG, "commit": run.name, "phase": phase}))
            a.check_recovery(state)


    def test_only_preintegration_failure_is_safe_to_retry(self):
        run = self.root / ("a" * 40)
        run.mkdir()
        record = {"marker": b.BOOTSTRAP_TAG, "commit": run.name, "phase": "failed-before-integration"}
        (run / "journal.json").write_bytes(a.encoded(record))
        self.assertEqual(a.json_object(b.retryable_journal(run))["phase"], "failed-before-integration")
        for phase in ["checkpoint-created", "activating", "recovery-required", "complete"]:
            record["phase"] = phase
            (run / "journal.json").write_bytes(a.encoded(record))
            with self.subTest(phase=phase), self.assertRaises(a.RecoveryRequired):
                b.retryable_journal(run)


if __name__ == "__main__":
    unittest.main()
