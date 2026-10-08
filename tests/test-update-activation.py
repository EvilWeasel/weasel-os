#!/usr/bin/env python3
"""Failure-path tests for the privileged source transaction; no system activation."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("activation", Path(__file__).resolve().parents[1] / "scripts/weasel-update-activate.py")
activation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = activation
SPEC.loader.exec_module(activation)


class LocalGit:
    """Unprivileged fixture Git; never invokes sudo, runuser, Nix or real services."""
    def __init__(self):
        self.account = types.SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())

    def git(self, repository, *args, extra_env=None):
        env = os.environ.copy()
        env["GIT_OPTIONAL_LOCKS"] = "0"
        env["GIT_NO_REPLACE_OBJECTS"] = "1"
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(repository), *map(str, args)],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode:
            raise activation.ActivationError("Fixture Git refused operation")
        return result.stdout


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="weasel-update-activation-test-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def request(self):
        return {"schema": 1, "id": "20261008T140000Z-1234abcd", "baseline_commit": "a" * 40,
                "baseline_system": "/nix/store/" + "a" * 32 + "-nixos-system-nixy-laptop-25.11.20260501.26ef669",
                "candidate_commit": "b" * 40, "candidate_ref": "refs/heads/weasel-update-20261008T140000Z-1234abcd"}

    def fixture(self):
        runner = LocalGit()
        repo = self.root / "repository"
        repo.mkdir()
        runner.git(repo, "init", "-b", "main")
        runner.git(repo, "config", "user.name", "Fixture")
        runner.git(repo, "config", "user.email", "fixture@example.invalid")
        runner.git(repo, "config", "commit.gpgsign", "false")
        source = repo / "packages/t3code/source.json"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"old source\n")
        (repo / "agent-learnings.md").write_bytes(b"previous learning\n")
        runner.git(repo, "add", ".")
        runner.git(repo, "commit", "-m", "baseline")
        baseline = runner.git(repo, "rev-parse", "HEAD").decode().strip()
        before, index = activation.repository_manifest(runner, repo, baseline)
        runner.git(repo, "switch", "-c", "candidate")
        source.write_bytes(b"new source\n")
        (repo / "agent-learnings.md").write_bytes(b"previous learning\nnew learning\n")
        runner.git(repo, "add", ".")
        runner.git(repo, "commit", "-m", "candidate")
        candidate = runner.git(repo, "rev-parse", "HEAD").decode().strip()
        runner.git(repo, "switch", "main")
        # Git recreates files/index during switch; capture the actual current identity.
        before, index = activation.repository_manifest(runner, repo, baseline)
        backup = self.root / "backup"
        backup.mkdir()
        workspace = self.root / "workspace"
        workspace.mkdir()
        request = self.request()
        request.update(baseline_commit=baseline, candidate_commit=candidate)
        changes = {"packages/t3code/source.json": (b"old source\n", b"new source\n"),
                   "agent-learnings.md": (b"previous learning\n", b"previous learning\nnew learning\n")}
        return runner, repo, request, before, index, changes, backup, workspace

    def test_strict_request_rejects_commands_paths_and_duplicate_keys(self):
        request = self.request()
        self.assertEqual(activation.parse_request(json.dumps(request).encode()), request)
        for key, value in [("command", "sh"), ("candidate_commit", "HEAD"), ("candidate_ref", "refs/heads/main"),
                           ("baseline_system", "/tmp/fake-system"), ("schema", True), ("id", "../../escape")]:
            bad = dict(request)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(activation.ActivationError):
                activation.parse_request(json.dumps(bad).encode())
        with self.assertRaises(activation.ActivationError):
            activation.parse_request(b'{"schema":1,"schema":1}')

    def test_request_rejects_oversize_and_nul(self):
        with self.assertRaises(activation.ActivationError):
            activation.parse_request(b" " * 65537)
        request = self.request()
        request["candidate_ref"] += "\0"
        with self.assertRaises(activation.ActivationError):
            activation.parse_request(json.dumps(request).encode())

    def test_request_file_rejects_symlink_and_hardlinks(self):
        real = self.root / "real"
        real.write_bytes(b"{}")
        linked = self.root / "symlink"
        linked.symlink_to(real)
        with self.assertRaises(OSError):
            activation.read_regular(linked)
        hard = self.root / "hard"
        os.link(real, hard)
        with self.assertRaises(activation.ActivationError):
            activation.read_regular(real)

    def test_request_claim_preserves_newer_file(self):
        inbox, archive = self.root / "request.json", self.root / "archived.json"
        inbox.write_bytes(b"original")
        actual_rename = activation.rename_no_replace
        def race(source, destination):
            if source == inbox:
                newer = self.root / "newer"
                newer.write_bytes(b"concurrent request")
                os.replace(newer, inbox)
            actual_rename(source, destination)
        with patch.object(activation, "rename_no_replace", race), self.assertRaises(activation.ActivationError):
            activation.consume_request(inbox, archive, os.getuid())
        self.assertEqual(inbox.read_bytes(), b"concurrent request")
        self.assertEqual(archive.with_suffix(".original.json").read_bytes(), b"original")

    def test_interrupted_journal_blocks_even_no_candidate(self):
        runs = self.root / "runs"
        runs.mkdir()
        for phase in ["preparing", "tested", "checkpoint-created", "integrating", "source-integrated", "activating", "publishing", "recovery-required"]:
            run = runs / phase
            run.mkdir()
            (run / "journal.json").write_bytes(activation.encoded({"phase": phase}))
            with self.subTest(phase=phase), self.assertRaises(activation.ActivationError):
                activation.check_recovery(self.root)
            shutil.rmtree(run)
        for phase in activation.TERMINAL_PHASES:
            run = runs / phase
            run.mkdir()
            (run / "journal.json").write_bytes(activation.encoded({"phase": phase}))
        activation.check_recovery(self.root)

    def test_missing_daily_journal_blocks_without_deleting_retained_artifacts(self):
        run = self.root / "runs" / "20261008T140000Z-1234abcd"
        run.mkdir(parents=True)
        for read_only in [True, False]:
            with self.subTest(stage="before-first-journal", read_only=read_only):
                with self.assertRaises(activation.RecoveryRequired):
                    activation.check_recovery(self.root, read_only=read_only)
                self.assertTrue(run.is_dir())
                self.assertEqual(list(run.iterdir()), [])
        journal = run / "journal.json"
        journal.write_bytes(activation.encoded({"marker": activation.OWNER_TAG, "id": run.name, "phase": "pruning"}))
        retained = run / "retained-proof.json"
        retained.write_bytes(b"proof from interrupted cleanup\n")
        # A cleanup interruption can remove the journal before the run directory.
        journal.unlink()
        for read_only in [True, False]:
            with self.subTest(stage="partially-pruned-run", read_only=read_only):
                with self.assertRaises(activation.RecoveryRequired):
                    activation.check_recovery(self.root, read_only=read_only)
                self.assertFalse(journal.exists())
                self.assertEqual(retained.read_bytes(), b"proof from interrupted cleanup\n")

    def test_existing_file_destination_is_never_overwritten(self):
        source, destination = self.root / "source", self.root / "dest"
        source.write_bytes(b"source")
        destination.write_bytes(b"unrelated")
        with self.assertRaises(FileExistsError):
            activation.rename_no_replace(source, destination)
        self.assertEqual(source.read_bytes(), b"source")
        self.assertEqual(destination.read_bytes(), b"unrelated")

    def test_replacement_retains_original_inode_and_permissions(self):
        path, retained = self.root / "source", self.root / "retained"
        path.write_bytes(b"old")
        path.chmod(0o644)
        before = path.stat()
        activation.replace_preserving_inode(path, b"old", b"new", retained, uid=os.getuid(), gid=os.getgid(), mode=0o644)
        self.assertEqual(retained.stat().st_ino, before.st_ino)
        self.assertEqual(retained.read_bytes(), b"old")
        self.assertEqual(path.read_bytes(), b"new")
        self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_editor_fd_save_retains_bytes_and_refuses_activation(self):
        path, retained = self.root / "source", self.root / "retained"
        path.write_bytes(b"old")
        fd = os.open(path, os.O_WRONLY)
        self.addCleanup(os.close, fd)
        actual_rename = activation.rename_no_replace
        def race(source, destination):
            actual_rename(source, destination)
            if destination == path:
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, b"editor save")
                os.ftruncate(fd, len(b"editor save"))
        with patch.object(activation, "rename_no_replace", race), self.assertRaises(activation.ActivationError):
            activation.replace_preserving_inode(path, b"old", b"new", retained, uid=os.getuid(), gid=os.getgid(), mode=0o644)
        self.assertEqual(retained.read_bytes(), b"editor save")
        self.assertEqual(path.read_bytes(), b"new")

    def test_atomic_editor_replacement_is_not_clobbered(self):
        path, retained = self.root / "source", self.root / "retained"
        path.write_bytes(b"old")
        actual_rename = activation.rename_no_replace
        def race(source, destination):
            actual_rename(source, destination)
            if source == path:
                path.write_bytes(b"concurrent replacement")
        with patch.object(activation, "rename_no_replace", race), self.assertRaises(activation.ActivationError):
            activation.replace_preserving_inode(path, b"old", b"new", retained, uid=os.getuid(), gid=os.getgid(), mode=0o644)
        self.assertEqual(path.read_bytes(), b"concurrent replacement")
        self.assertEqual(retained.read_bytes(), b"old")
        self.assertEqual(retained.with_name(retained.name + ".candidate").read_bytes(), b"new")

    def test_source_manifest_detects_ignored_git_index_flags(self):
        runner, repo, request, _before, _index, _changes, _backup, _workspace = self.fixture()
        runner.git(repo, "update-index", "--assume-unchanged", "packages/t3code/source.json")
        (repo / "packages/t3code/source.json").write_bytes(b"hidden dirty content")
        with self.assertRaises(activation.ActivationError):
            activation.repository_manifest(runner, repo, request["baseline_commit"])

    def test_source_integration_keeps_clean_main_and_old_versions(self):
        runner, repo, request, before, index, changes, backup, workspace = self.fixture()
        phases = []
        after = activation.integrate_source(runner, repo, request, before, index, changes, backup, workspace,
                                            lambda phase, **fields: phases.append(phase))
        self.assertEqual(after["commit"], request["candidate_commit"])
        self.assertFalse(runner.git(repo, "status", "--porcelain"))
        self.assertEqual(phases, ["integrating", "source-integrated"])
        self.assertEqual((backup / "packages__t3code__source.json").read_bytes(), b"old source\n")
        self.assertEqual((backup / "index-original").read_bytes(), index)
        self.assertFalse((repo / ".git/index.lock").exists())

    def test_concurrent_main_commit_is_not_reset(self):
        runner, repo, request, before, index, changes, backup, workspace = self.fixture()
        runner.git(repo, "commit", "--allow-empty", "-m", "parallel work")
        concurrent_head = runner.git(repo, "rev-parse", "HEAD")
        with self.assertRaises(activation.ActivationError):
            activation.integrate_source(runner, repo, request, before, index, changes, backup, workspace, lambda *a, **k: None)
        self.assertEqual(runner.git(repo, "rev-parse", "HEAD"), concurrent_head)
        self.assertEqual((repo / "packages/t3code/source.json").read_bytes(), b"old source\n")

    def test_other_git_lock_is_preserved(self):
        runner, repo, request, before, index, changes, backup, workspace = self.fixture()
        lock = repo / ".git/index.lock"
        lock.write_bytes(b"parallel git transaction")
        with self.assertRaises(FileExistsError):
            activation.integrate_source(runner, repo, request, before, index, changes, backup, workspace, lambda *a, **k: None)
        self.assertEqual(lock.read_bytes(), b"parallel git transaction")

    def test_power_gate_uses_ac_and_battery(self):
        sysroot = self.root / "power"
        sysroot.mkdir()
        mains = sysroot / "AC"
        battery = sysroot / "BAT0"
        mains.mkdir()
        battery.mkdir()
        (mains / "type").write_text("Mains")
        (mains / "online").write_text("1")
        (battery / "type").write_text("Battery")
        (battery / "capacity").write_text("30")
        activation.check_power(sysroot)
        for online, capacity in [("0", "100"), ("1", "29")]:
            (mains / "online").write_text(online)
            (battery / "capacity").write_text(capacity)
            with self.assertRaises(activation.ActivationError):
                activation.check_power(sysroot)

    def test_exact_active_and_boot_profile_both_required(self):
        baseline = self.root / "system"
        (baseline / "bin").mkdir(parents=True)
        (baseline / "bin/switch-to-configuration").write_text("fixture")
        current, profile = self.root / "current", self.root / "profile"
        current.symlink_to(baseline)
        profile.symlink_to(baseline)
        with patch.object(activation, "CURRENT", current), patch.object(activation, "PROFILE", profile):
            activation.check_system(baseline)
            profile.unlink()
            profile.symlink_to(self.root / "different")
            with self.assertRaises(activation.ActivationError):
                activation.check_system(baseline)

    def test_snapshot_requires_own_btrfs_mount_and_read_only_checkpoint(self):
        class Snapshots:
            def __init__(self, filesystem="btrfs", ro="ro=true"):
                self.filesystem = filesystem
                self.ro = ro
            def root(self, name, arguments):
                if name == "findmnt":
                    return json.dumps({"filesystems": [{"target": "/home", "fstype": self.filesystem}]}).encode()
                if name == "snapper":
                    return b"7\n"
                if name == "btrfs" and arguments[0] == "property":
                    return self.ro.encode()
                return b""
        with patch.object(activation, "check_space"):
            self.assertEqual(activation.create_snapshot(Snapshots(), "fixture"), 7)
            for runner in [Snapshots(filesystem="ext4"), Snapshots(ro="ro=false")]:
                with self.assertRaises(activation.ActivationError):
                    activation.create_snapshot(runner, "fixture")


    def checked_fixture(self):
        runner, repo, request, before, index, changes, backup, workspace = self.fixture()
        runner.git(repo, "update-ref", request["candidate_ref"], request["candidate_commit"])
        original_git = runner.git
        def signed_git(repository, *args, **kwargs):
            if args == ("config", "--get", "user.signingkey"):
                return activation.EXPECTED_PRIMARY_FINGERPRINT.encode()
            if args[:1] == ("verify-commit",):
                return b""
            if args[:3] == ("show", "-s", "--format=%G? %GF %GP"):
                return ("G " + activation.EXPECTED_PRIMARY_FINGERPRINT + " " + activation.EXPECTED_PRIMARY_FINGERPRINT).encode()
            return original_git(repository, *args, **kwargs)
        runner.git = signed_git
        discovery = types.SimpleNamespace(
            validate_transition=lambda *a, **k: {"old": {"version": "0.1.0"}, "new": {"version": "0.2.0"}},
            learning_suffix=lambda *a, **k: b"new learning\n",
        )
        return runner, repo, request, discovery, original_git

    def test_check_mode_verifies_exact_scope_without_writing(self):
        runner, repo, request, discovery, original_git = self.checked_fixture()
        before = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
        with patch.object(activation, "import_peer", return_value=discovery), patch.object(activation, "check_system"), patch.object(activation, "check_other_activation"), patch.object(activation, "check_remote"):
            result = activation.process_request(runner, request, self.root / "state", repo, check_only=True)
        after = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
        self.assertTrue(result["ok"])
        self.assertFalse(result["activation_verified"])
        self.assertEqual(before, after)
        self.assertFalse((self.root / "state").exists())

    def test_check_rejects_forged_learning_suffix(self):
        runner, repo, request, discovery, original_git = self.checked_fixture()
        discovery.learning_suffix = lambda *a: b"unrelated expected suffix\n"
        with patch.object(activation, "import_peer", return_value=discovery), patch.object(activation, "check_system"), patch.object(activation, "check_other_activation"), patch.object(activation, "check_remote"):
            with self.assertRaisesRegex(activation.ActivationError, "Learning entry"):
                activation.process_request(runner, request, self.root / "state", repo, check_only=True)

    def test_check_rejects_other_valid_signer(self):
        runner, repo, request, discovery, original_git = self.checked_fixture()
        signed_git = runner.git
        def wrong_signer(repository, *args, **kwargs):
            if args[:3] == ("show", "-s", "--format=%G? %GF %GP"):
                return b"G 1111111111111111111111111111111111111111 1111111111111111111111111111111111111111"
            return signed_git(repository, *args, **kwargs)
        runner.git = wrong_signer
        with patch.object(activation, "import_peer", return_value=discovery), patch.object(activation, "check_system"), patch.object(activation, "check_other_activation"), patch.object(activation, "check_remote"):
            with self.assertRaisesRegex(activation.ActivationError, "signer"):
                activation.process_request(runner, request, self.root / "state", repo, check_only=True)

    def test_original_open_fd_prevents_cleanup(self):
        backup = self.root / "backup"
        backup.mkdir()
        retained = backup / "original"
        retained.write_bytes(b"editor")
        with open(retained, "rb"):
            self.assertTrue(activation.retained_has_open_fds(backup))

    def test_other_activation_blocks_switch_but_parallel_build_is_allowed(self):
        proc = self.root / "processes"
        process = proc / "123456"
        process.mkdir(parents=True)
        (process / "cmdline").write_bytes(b"/nix/store/test/bin/nixos-rebuild\0build\0")
        activation.check_other_activation(proc)
        (process / "cmdline").write_bytes(b"/nix/store/test/bin/nixos-rebuild\0switch\0")
        with self.assertRaises(activation.ActivationError):
            activation.check_other_activation(proc)


    def test_root_reads_reject_symlinked_parent_directories(self):
        real = self.root / "real"
        real.mkdir()
        (real / "source").write_bytes(b"private")
        linked = self.root / "linked"
        linked.symlink_to(real, target_is_directory=True)
        with self.assertRaises(OSError):
            activation.read_regular(linked / "source")
        destination = self.root / "retained"
        with self.assertRaises(OSError):
            activation.rename_no_replace(linked / "source", destination)
        self.assertEqual((real / "source").read_bytes(), b"private")
        self.assertFalse(destination.exists())


    def test_remote_provenance_and_current_head_are_required(self):
        expected = "a" * 40
        class Remote:
            def __init__(self, url=activation.ORIGIN_URL, head=expected, push=None):
                self.url, self.head, self.push = url, head, push
            def git(self, repository, *args):
                if args[:2] == ("remote", "get-url"):
                    return ((self.push if "--push" in args and self.push is not None else self.url) + "\n").encode()
                return (self.head + "\trefs/heads/main\n").encode()
        activation.check_remote(Remote(), self.root, expected)
        for remote in [Remote(url="https://example.invalid/repo"), Remote(head="b" * 40), Remote(push="https://example.invalid/push")]:
            with self.assertRaises(activation.ActivationError):
                activation.check_remote(remote, self.root, expected)


    def test_late_editor_save_blocks_and_readonly_check_preserves_journal(self):
        state = self.root / "state"
        run = state / "runs/20261008T140000Z-1234abcd"
        run.mkdir(parents=True)
        backups = self.root / "backups"
        backup = backups / run.name
        backup.mkdir(parents=True)
        (backup / "original").write_bytes(b"late editor save")
        journal = run / "journal.json"
        journal.write_bytes(activation.encoded({"marker": activation.OWNER_TAG, "phase": "complete",
                                               "retained_originals": {"original": activation.digest(b"old")}}))
        original = journal.read_bytes()
        with patch.object(activation, "BACKUPS", backups):
            with self.assertRaises(activation.RecoveryRequired):
                activation.check_recovery(state, read_only=True)
            self.assertEqual(journal.read_bytes(), original)
            with self.assertRaises(activation.RecoveryRequired):
                activation.check_recovery(state)
        self.assertEqual(json.loads(journal.read_bytes())["phase"], "recovery-required")
        self.assertEqual((backup / "original").read_bytes(), b"late editor save")

    def test_retention_never_deletes_an_untagged_snapshot(self):
        state, backups = self.root / "state", self.root / "backups"
        (state / "runs").mkdir(parents=True)
        (state / "requests").mkdir()
        for serial in range(4):
            identifier = "20261008T140000Z-" + str(serial).zfill(8)
            run = state / "runs" / identifier
            run.mkdir()
            backup = backups / identifier
            backup.mkdir(parents=True)
            for name, contents in {"original": b"old", "index-original": b"index", "original-index-copy": b"index"}.items():
                (backup / name).write_bytes(contents)
            (run / "journal.json").write_bytes(activation.encoded({
                "marker": activation.OWNER_TAG, "id": identifier, "phase": "complete", "snapshot": serial + 1,
                "retained_originals": {"original": activation.digest(b"old")},
                "original_index_sha256": activation.digest(b"index")}))
        class SnapshotReader:
            account = types.SimpleNamespace(pw_uid=os.getuid())
            def root(self, name, args):
                if name == "snapper" and "list" in args:
                    return b'{"home":[{"number":1,"userdata":{"other-owner":"yes"}}]}'
                raise AssertionError("Deletion must not execute")
        with patch.object(activation, "BACKUPS", backups), patch.object(activation, "retained_has_open_fds", return_value=False):
            with self.assertRaisesRegex(activation.ActivationError, "untagged"):
                activation.prune_owned(SnapshotReader(), state, keep=3)
        self.assertEqual(len(list((state / "runs").iterdir())), 4)
        self.assertEqual(len(list(backups.iterdir())), 4)


    def test_corrupted_git_blob_cannot_replace_signed_content(self):
        runner, repo, request, _before, _index, _changes, _backup, _workspace = self.fixture()
        original = runner.git
        blob = activation.tracked_tree(runner, repo, request["baseline_commit"])["packages/t3code/source.json"][1]
        def substituted(repository, *args, **kwargs):
            if args == ("cat-file", "blob", blob):
                return b"corrupted loose object"
            return original(repository, *args, **kwargs)
        runner.git = substituted
        with self.assertRaisesRegex(activation.ActivationError, "signed content address"):
            activation.read_blob(runner, repo, blob)

    def test_corrupted_git_tree_cannot_redirect_source_paths(self):
        runner, repo, request, _before, _index, _changes, _backup, _workspace = self.fixture()
        original = runner.git
        def substituted(repository, *args, **kwargs):
            result = original(repository, *args, **kwargs)
            if args[:2] == ("cat-file", "tree"):
                return result.replace(b"packages", b"dangerous")
            return result
        runner.git = substituted
        with self.assertRaisesRegex(activation.ActivationError, "signed content address"):
            activation.tracked_tree(runner, repo, request["baseline_commit"])


if __name__ == "__main__":
    unittest.main()
