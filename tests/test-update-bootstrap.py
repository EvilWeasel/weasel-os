#!/usr/bin/env python3
"""Bootstrap policy and failure tests; root commands are recording fixtures only."""
import importlib.util
import io
import json
import os
from contextlib import ExitStack, redirect_stdout
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


class BootstrapResumeTests(unittest.TestCase):
    """Resume fixtures mock root identity; all files and commands stay private/user-owned."""

    setUp = BootstrapTests.setUp
    fixture = BootstrapTests.fixture
    receipt = BootstrapTests.receipt

    def resume_fixture(self, runner=None):
        runner, repo, source, receipt, expected, run = self.fixture(runner)
        receipt_path = Path("/nix/store/" + "c" * 32 + "-reviewed-bootstrap.json")
        record = {"schema": 1, "marker": b.BOOTSTRAP_TAG, "commit": receipt["commit"],
                  "old_system": receipt["old_system"], "new_system": receipt["new_system"],
                  "receipt": str(receipt_path), "phase": "recovery-required", "snapshot": 33,
                  "error": "ActivationError", "original_native_exit": 4,
                  "system_rollback": "complete", "home_rollback": False}
        data = a.encoded(record)
        (run / "journal.json").write_bytes(data)
        for name, target in [("old-system", receipt["old_system"]),
                             ("tested-system", receipt["new_system"])]:
            (run / name).symlink_to(target)
        return runner, repo, source, receipt, expected, run, receipt_path, record, data

    def fixture_root_reads(self, stack):
        # The real read_regular still checks regular-file safety and races.
        # Only the synthetic root UID is mapped to this fixture's actual UID.
        original = a.read_regular
        def read(path, *args, **kwargs):
            if kwargs.get("expected_uid") == 0:
                self.assertTrue(Path(path).is_relative_to(self.root))
                kwargs["expected_uid"] = os.getuid()
            return original(path, *args, **kwargs)
        stack.enter_context(patch.object(a.os, "geteuid", return_value=0))
        return stack.enter_context(patch.object(a, "read_regular", side_effect=read))

    def test_resume_binds_exact_original_bytes_without_changing_journal(self):
        runner, repo, source, receipt, expected, run, path, record, data = self.resume_fixture()
        with ExitStack() as stack:
            reads = self.fixture_root_reads(stack)
            returned, decoded = b.resume_journal(run, receipt, path, a.digest(data))
        self.assertEqual(returned, data)
        self.assertEqual(decoded, record)
        self.assertEqual((run / "journal.json").read_bytes(), data)
        self.assertEqual(reads.call_args.kwargs["expected_uid"], 0)
        self.assertEqual(runner.calls, [])

    def test_resume_rejects_every_changed_binding_even_with_fresh_digest(self):
        runner, repo, source, receipt, expected, run, path, record, data = self.resume_fixture()
        variants = [("marker", "another-owner"), ("commit", "f" * 40),
                    ("receipt", str(path) + ".other"), ("old_system", receipt["new_system"]),
                    ("new_system", receipt["old_system"]), ("phase", "activating"),
                    ("phase", "failed-before-integration"), ("phase", "complete"),
                    ("system_rollback", "failed"), ("system_rollback", None),
                    ("home_rollback", True), ("home_rollback", 0), ("home_rollback", None),
                    ("snapshot", True), ("snapshot", "33"), ("snapshot", 0), ("snapshot", -1)]
        with ExitStack() as stack:
            self.fixture_root_reads(stack)
            for key, value in variants:
                changed = dict(record, **{key: value})
                raw = a.encoded(changed)
                (run / "journal.json").write_bytes(raw)
                with self.subTest(key=key, value=value), self.assertRaises(a.RecoveryRequired):
                    b.resume_journal(run, receipt, path, a.digest(raw))
                self.assertEqual((run / "journal.json").read_bytes(), raw)

    def test_resume_rejects_stale_digest_and_other_namespace_receipt(self):
        runner, repo, source, receipt, expected, run, path, record, data = self.resume_fixture()
        with ExitStack() as stack:
            self.fixture_root_reads(stack)
            for digest in ["0" * 64, "not-a-digest", "A" * 64, None]:
                with self.subTest(digest=digest), self.assertRaises(a.RecoveryRequired):
                    b.resume_journal(run, receipt, path, digest)
            other = self.root / ("f" * 40)
            other.mkdir()
            (other / "journal.json").write_bytes(data)
            with self.assertRaises(a.RecoveryRequired):
                b.resume_journal(other, receipt, path, a.digest(data))
        self.assertEqual((run / "journal.json").read_bytes(), data)

    def test_resume_original_journal_must_actually_be_root_owned(self):
        if os.getuid() == 0:
            self.skipTest("Non-root ownership rejection requires the normal-user test harness")
        runner, repo, source, receipt, expected, run, path, record, data = self.resume_fixture()
        with self.assertRaises(a.ActivationError):
            b.resume_journal(run, receipt, path, a.digest(data))

    def test_resume_evidence_requires_both_exact_gc_roots(self):
        runner, repo, source, receipt, expected, run, path, record, data = self.resume_fixture()
        b.check_resume_evidence(runner, run, receipt, record)
        for name, target in [("old-system", receipt["old_system"]),
                             ("tested-system", receipt["new_system"])]:
            link = run / name
            link.unlink()
            with self.subTest(name=name, kind="missing"), self.assertRaises(a.RecoveryRequired):
                b.check_resume_evidence(runner, run, receipt, record)
            link.write_bytes(b"regular file is not a GC root")
            with self.subTest(name=name, kind="regular"), self.assertRaises(a.RecoveryRequired):
                b.check_resume_evidence(runner, run, receipt, record)
            link.unlink()
            link.symlink_to(receipt["new_system"] if name == "old-system" else receipt["old_system"])
            with self.subTest(name=name, kind="wrong-target"), self.assertRaises(a.RecoveryRequired):
                b.check_resume_evidence(runner, run, receipt, record)
            link.unlink()
            link.symlink_to(target)

    def test_resume_requires_original_snapshot_read_only(self):
        runner, repo, source, receipt, expected, run, path, record, data = self.resume_fixture(FixtureRunner(ro="ro=false"))
        with self.assertRaises(a.RecoveryRequired):
            b.check_resume_evidence(runner, run, receipt, record)
        self.assertEqual(runner.calls[-1], ("btrfs", ["property", "get", "-ts",
                         "/home/.snapshots/33/snapshot", "ro"]))
        self.assertFalse(any(name == "snapper" for name, args in runner.calls))

    def test_resume_preflight_still_checks_system_remote_signer_and_source(self):
        runner, repo, source, receipt, expected, run, path, record, data = self.resume_fixture()
        with ExitStack() as stack:
            self.fixture_root_reads(stack)
            stack.enter_context(patch.object(a, "STATE", self.root))
            other_activation = stack.enter_context(patch.object(a, "check_other_activation"))
            system = stack.enter_context(patch.object(a, "check_system"))
            remote = stack.enter_context(patch.object(a, "check_remote"))
            signer = stack.enter_context(patch.object(b, "signed_head"))
            # Each failed retained baseline guard must stop before any switch.
            for check in [system, other_activation, remote, signer]:
                check.side_effect = a.ActivationError("changed baseline fixture")
                with self.subTest(check=check), self.assertRaises(a.ActivationError):
                    b.preflight(runner, receipt, repository=repo, resume=(path, a.digest(data)))
                check.side_effect = None
            source.write_bytes(b"concurrent uncommitted source save\n")
            with self.assertRaises(a.ActivationError):
                b.preflight(runner, receipt, repository=repo, resume=(path, a.digest(data)))
            self.assertEqual(source.read_bytes(), b"concurrent uncommitted source save\n")
            self.assertEqual((run / "journal.json").read_bytes(), data)
            self.assertTrue(system.called and other_activation.called and remote.called and signer.called)

    def test_normal_user_preflight_cannot_request_resume(self):
        runner, repo, source, receipt, expected, run, path, record, data = self.resume_fixture()
        with patch.object(a, "check_system"), patch.object(a, "check_other_activation"), self.assertRaises(a.ActivationError):
            b.preflight(runner, receipt, repository=repo, privileged=False, resume=(path, a.digest(data)))
        self.assertEqual((run / "journal.json").read_bytes(), data)

    def test_resume_cli_rejects_unprivileged_and_mixed_or_incomplete_flags(self):
        receipt = self.receipt()
        path = "/nix/store/" + "c" * 32 + "-reviewed-bootstrap.json"
        variants = [["--resume"], ["--journal-sha256", "a" * 64],
                    ["--resume", "--journal-sha256", "a" * 64, "--verify-receipt"],
                    ["--resume", "--journal-sha256", "a" * 64],
                    ["--resume", "--journal-sha256", "a" * 64, "--check"]]
        for flags in variants:
            with self.subTest(flags=flags), patch.object(sys, "argv", ["bootstrap", "--receipt", path, *flags]), \
                    patch.object(b, "load_receipt", return_value=receipt), \
                    patch.object(a.os, "uname", return_value=types.SimpleNamespace(nodename=a.HOST)), \
                    patch.object(a.os, "geteuid", return_value=1000), \
                    patch.object(b, "preflight") as preflight, self.assertRaises(a.ActivationError):
                b.main()
            preflight.assert_not_called()

    def cli_fixture(self, stack, fixture, switch):
        runner, repo, source, receipt, expected, run, path, record, data = fixture
        self.fixture_root_reads(stack)
        self.root.chmod(0o711)
        (self.root / "bootstrap").chmod(0o700)
        run.chmod(0o700)
        self.status.parent.chmod(0o755)
        ensure = a.ensure_directory
        stack.enter_context(patch.object(a, "ensure_directory", side_effect=lambda path, **kwargs:
                                     ensure(path, **dict(kwargs, owner=os.getuid()))))
        stack.enter_context(patch.object(a, "STATE", self.root))
        stack.enter_context(patch.object(a.os, "uname", return_value=types.SimpleNamespace(nodename=a.HOST)))
        stack.enter_context(patch.object(sys, "argv", ["bootstrap", "--receipt", str(path), "--resume",
                                   "--journal-sha256", a.digest(data)]))
        stack.enter_context(patch.object(b, "load_receipt", return_value=receipt))
        stack.enter_context(patch.object(a, "Runner", return_value=runner))
        stack.enter_context(patch.object(b, "preflight", return_value=expected))
        stack.enter_context(patch.object(b, "reproduce"))
        stack.enter_context(patch.object(b, "source_checkpoint", side_effect=lambda _r, _repo, _receipt:
                                     BootstrapResumeTests.actual_source_checkpoint(_r, repo, _receipt)))
        stack.enter_context(patch.object(a, "check_system"))
        stack.enter_context(patch.object(a, "check_other_activation"))
        stack.enter_context(patch.object(a, "check_remote"))
        stack.enter_context(patch.object(a, "check_power"))
        stack.enter_context(patch.object(a, "check_space"))
        stack.enter_context(patch.object(a, "activate_exact", side_effect=switch))
        stack.enter_context(redirect_stdout(io.StringIO()))

    actual_source_checkpoint = staticmethod(b.source_checkpoint)

    def test_resume_archives_original_and_requires_fresh_snapshot_and_install_success(self):
        fixture = self.resume_fixture()
        runner, repo, source, receipt, expected, run, path, record, data = fixture
        closures = []
        with ExitStack() as stack:
            self.cli_fixture(stack, fixture, lambda _runner, system: closures.append(str(system)))
            self.assertEqual(b.main(), 0)
        archive = run / ("resumed-attempt-" + a.digest(data) + ".json")
        self.assertEqual(archive.read_bytes(), data)
        completed = json.loads((run / "journal.json").read_bytes())
        self.assertEqual(completed["phase"], "complete")
        self.assertEqual(completed["snapshot"], 11)
        self.assertEqual(completed["original_snapshot"], 33)
        self.assertEqual(completed["resumed_from"], a.digest(data))
        self.assertEqual(completed["original_journal"], str(archive))
        self.assertEqual(closures, [receipt["new_system"]])
        self.assertEqual(json.loads(archive.read_bytes())["original_native_exit"], 4)
        self.assertEqual(json.loads(archive.read_bytes())["phase"], "recovery-required")
        self.assertTrue(any(name == "snapper" and "create" in args for name, args in runner.calls))

    def test_resume_native_failure_keeps_original_and_never_produces_complete(self):
        fixture = self.resume_fixture()
        runner, repo, source, receipt, expected, run, path, record, data = fixture
        closures = []
        def native(_runner, system):
            closures.append(str(system))
            if str(system) == receipt["new_system"]:
                raise a.ActivationError("native switch fixture exit4")
        with ExitStack() as stack:
            self.cli_fixture(stack, fixture, native)
            with self.assertRaises(a.ActivationError):
                b.main()
        self.assertEqual(closures, [receipt["new_system"], receipt["old_system"]])
        archive = run / ("resumed-attempt-" + a.digest(data) + ".json")
        self.assertEqual(archive.read_bytes(), data)
        failed = json.loads((run / "journal.json").read_bytes())
        self.assertEqual(failed["phase"], "recovery-required")
        self.assertEqual(failed["snapshot"], 11)
        self.assertEqual(failed["system_rollback"], "complete")
        self.assertEqual(failed["resumed_from"], a.digest(data))
        self.assertEqual(failed["original_snapshot"], 33)
        self.assertEqual(failed["original_journal"], str(archive))
        self.assertEqual(json.loads(self.status.read_bytes())["outcome"], "blocked")

    def test_resume_changed_original_archive_refuses_before_install(self):
        fixture = self.resume_fixture()
        runner, repo, source, receipt, expected, run, path, record, data = fixture
        archive = run / ("resumed-attempt-" + a.digest(data) + ".json")
        changed = data + b"\nchanged archive\n"
        archive.write_bytes(changed)
        with ExitStack() as stack:
            self.cli_fixture(stack, fixture, lambda *_args: self.fail("must not activate"))
            with self.assertRaises(a.RecoveryRequired):
                b.main()
        self.assertEqual(archive.read_bytes(), changed)
        self.assertEqual((run / "journal.json").read_bytes(), data)
        self.assertFalse(any(name == "snapper" for name, args in runner.calls))

    def test_resume_exact_archive_after_interrupted_archival_can_continue(self):
        fixture = self.resume_fixture()
        runner, repo, source, receipt, expected, run, path, record, data = fixture
        archive = run / ("resumed-attempt-" + a.digest(data) + ".json")
        archive.write_bytes(data)
        original_inode = archive.stat().st_ino
        closures = []
        with ExitStack() as stack:
            self.cli_fixture(stack, fixture, lambda _runner, system: closures.append(str(system)))
            self.assertEqual(b.main(), 0)
        self.assertEqual(archive.read_bytes(), data)
        self.assertEqual(archive.stat().st_ino, original_inode)
        completed = json.loads((run / "journal.json").read_bytes())
        self.assertEqual(completed["phase"], "complete")
        self.assertEqual(completed["original_snapshot"], 33)
        self.assertEqual(closures, [receipt["new_system"]])

    def test_resume_rejects_dangling_archive_symlink_without_replacing_it(self):
        fixture = self.resume_fixture()
        runner, repo, source, receipt, expected, run, path, record, data = fixture
        archive = run / ("resumed-attempt-" + a.digest(data) + ".json")
        target = self.root / "absent-archive-target"
        archive.symlink_to(target)
        inode = archive.lstat().st_ino
        with ExitStack() as stack:
            self.cli_fixture(stack, fixture, lambda *_args: self.fail("must not activate"))
            with self.assertRaises((OSError, a.ActivationError)):
                b.main()
        self.assertTrue(archive.is_symlink())
        self.assertEqual(archive.lstat().st_ino, inode)
        self.assertEqual(archive.readlink(), target)
        self.assertEqual((run / "journal.json").read_bytes(), data)
        self.assertFalse(any(name == "snapper" for name, args in runner.calls))

    def test_resume_preactivation_failures_keep_original_recovery_fence_and_snapshot(self):
        fixture = self.resume_fixture()
        runner, repo, source, receipt, expected, run, path, record, data = fixture
        archive = run / ("resumed-attempt-" + a.digest(data) + ".json")
        for target, name in [(b, "reproduce"), (a, "check_power"), (a, "check_space")]:
            (run / "journal.json").write_bytes(data)
            runner.calls.clear()
            with self.subTest(fault=name), ExitStack() as stack:
                self.cli_fixture(stack, fixture, lambda *_args: self.fail("must not activate before fresh snapshot"))
                stack.enter_context(patch.object(target, name,
                                               side_effect=a.ActivationError("preactivation fixture " + name)))
                with self.assertRaises(a.ActivationError):
                    b.main()
                failed = json.loads((run / "journal.json").read_bytes())
                self.assertEqual(failed["phase"], "recovery-required")
                self.assertEqual(failed["snapshot"], 33)
                self.assertEqual(failed["original_snapshot"], 33)
                self.assertEqual(failed["system_rollback"], "complete")
                self.assertIs(failed["home_rollback"], False)
                self.assertEqual(failed["resumed_from"], a.digest(data))
                self.assertEqual(failed["original_journal"], str(archive))
                self.assertEqual(archive.read_bytes(), data)
                self.assertEqual(json.loads(archive.read_bytes())["original_native_exit"], 4)
                self.assertFalse(any(tool == "snapper" for tool, args in runner.calls))
                with self.assertRaises(a.RecoveryRequired):
                    a.check_recovery(self.root, read_only=True)
                with self.assertRaises(a.RecoveryRequired):
                    b.retryable_journal(run)
                self.assertEqual(json.loads(self.status.read_bytes())["outcome"], "blocked")


if __name__ == "__main__":
    unittest.main()
