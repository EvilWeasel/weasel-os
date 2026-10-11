#!/usr/bin/env python3
"""Private config-copy and command-boundary tests; no compositor or session IPC."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("niri_gate", Path(__file__).resolve().parents[1] / "scripts/weasel-update-niri.py")
niri = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = niri
SPEC.loader.exec_module(niri)


class ParentTraversalTests(unittest.TestCase):
    @unittest.skipIf(os.geteuid() == 0, "Requires an ordinary UID for search-only permission enforcement")
    def test_owned_search_only_ancestor_allows_read_and_own_fixture_but_not_symlink(self):
        with tempfile.TemporaryDirectory(prefix="weasel-niri-owned-search-test-") as temporary:
            root = Path(temporary)
            ancestor = root / "search-only"
            ancestor.mkdir()
            source = ancestor / "source"
            source.mkdir()
            readable = source / "config.kdl"
            readable.write_bytes(b"immutable search-only configuration\n")
            readable.chmod(0o444)
            source.chmod(0o555)
            own = ancestor / "ordinary-user"
            own.mkdir(mode=0o700)
            alias = ancestor / "source-link"
            alias.symlink_to(source, target_is_directory=True)
            ancestor.chmod(0o111)
            try:
                self.assertEqual(stat.S_IMODE(ancestor.stat().st_mode), 0o111)
                self.assertEqual(ancestor.stat().st_uid, os.getuid())
                with self.assertRaises(PermissionError):
                    os.open(ancestor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                self.assertEqual(niri.read_file(readable, immutable=True), b"immutable search-only configuration\n")
                target = own / "nested/fixture/result.kdl"
                parent = niri.open_parent(target, create_missing=True)
                try:
                    self.assertFalse(os.get_inheritable(parent))
                finally:
                    os.close(parent)
                niri.write_private(target, b"private ordinary-user fixture\n")
                self.assertEqual(target.read_bytes(), b"private ordinary-user fixture\n")
                self.assertEqual(target.stat().st_uid, os.getuid())
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                with self.assertRaises(OSError):
                    niri.read_file(alias / "config.kdl", immutable=True)
                self.assertEqual(stat.S_IMODE(ancestor.stat().st_mode), 0o111)
            finally:
                ancestor.chmod(0o700)
                source.chmod(0o700)

    def test_missing_o_path_fails_closed_before_opening(self):
        if not hasattr(os, "O_PATH"):
            self.skipTest("Linux O_PATH is unavailable")
        original = os.O_PATH
        try:
            del os.O_PATH
            with patch.object(niri.os, "open") as opened:
                with self.assertRaisesRegex(niri.NiriGateError, "Search-only"):
                    niri.open_parent(Path("/unopened/config.kdl"))
                opened.assert_not_called()
        finally:
            os.O_PATH = original


@unittest.skipUnless(os.geteuid() == 0, "Requires UID0 fixture and actual unprivileged child")
class RootSearchOnlyParentTests(unittest.TestCase):
    def test_search_only_source_and_private_fixture_with_unprivileged_uid(self):
        with tempfile.TemporaryDirectory(prefix="weasel-niri-parent-traversal-test-") as temporary:
            root = Path(temporary)
            root.chmod(0o711)
            namespace = root / "root-namespace"
            namespace.mkdir(mode=0o711)
            namespace.chmod(0o711)
            source = namespace / "source"
            source.mkdir()
            readable = source / "config.kdl"
            readable.write_bytes(b"immutable candidate configuration\n")
            readable.chmod(0o444)
            oversized = source / "oversized.kdl"
            oversized.write_bytes(b"x" * (niri.MAXIMUM_FILE + 1))
            oversized.chmod(0o444)
            source.chmod(0o555)
            private = root / "root-private"
            private.mkdir(mode=0o700)
            (private / "config.kdl").write_bytes(b"private fixture\n")
            (private / "config.kdl").chmod(0o444)
            alias = root / "source-link"
            alias.symlink_to(source, target_is_directory=True)
            own = root / "ordinary-user"
            own.mkdir(mode=0o700)
            os.chown(own, 65534, 65534)
            before = [(path.stat().st_mode, path.stat().st_uid, path.stat().st_gid)
                      for path in (namespace, source, readable)]
            read_fd, write_fd = os.pipe()
            pid = os.fork()
            if pid == 0:
                os.close(read_fd)
                try:
                    os.setgroups([])
                    os.setgid(65534)
                    os.setuid(65534)
                    assert os.getuid() == os.geteuid() == 65534
                    assert niri.read_file(readable, immutable=True) == b"immutable candidate configuration\n"
                    try:
                        niri.read_file(private / "config.kdl", immutable=True)
                    except PermissionError:
                        pass
                    else:
                        raise AssertionError("Private root directory was readable")
                    try:
                        niri.read_file(alias / "config.kdl", immutable=True)
                    except OSError:
                        pass
                    else:
                        raise AssertionError("Parent symlink was followed")
                    try:
                        niri.read_file(oversized, immutable=True)
                    except niri.NiriGateError as error:
                        assert "bounded" in str(error)
                    else:
                        raise AssertionError("Oversized source was accepted")
                    target = own / "nested/fixture/result.kdl"
                    parent = niri.open_parent(target, create_missing=True)
                    os.close(parent)
                    niri.write_private(target, b"private ordinary-user fixture\n")
                    assert target.read_bytes() == b"private ordinary-user fixture\n"
                    assert target.stat().st_uid == 65534
                    assert stat.S_IMODE(target.stat().st_mode) == 0o600
                    os.write(write_fd, b"PASS:0711-read;0700-refused;symlink-refused;bound;own-fixture\n")
                    os._exit(0)
                except BaseException as error:
                    os.write(write_fd, (type(error).__name__ + ": " + str(error)[:300]).encode())
                    os._exit(1)
            os.close(write_fd)
            try:
                deadline = time.monotonic() + 10
                while True:
                    waited, status = os.waitpid(pid, os.WNOHANG)
                    if waited:
                        break
                    if time.monotonic() >= deadline:
                        os.kill(pid, signal.SIGKILL)
                        os.waitpid(pid, 0)
                        self.fail("Unprivileged parent traversal fixture timed out")
                    time.sleep(0.01)
                observed = os.read(read_fd, 1024)
                self.assertEqual(os.waitstatus_to_exitcode(status), 0, observed.decode(errors="replace"))
                self.assertEqual(observed, b"PASS:0711-read;0700-refused;symlink-refused;bound;own-fixture\n")
                self.assertEqual(before, [(path.stat().st_mode, path.stat().st_uid, path.stat().st_gid)
                                          for path in (namespace, source, readable)])
                self.assertEqual(readable.read_bytes(), b"immutable candidate configuration\n")
            finally:
                os.close(read_fd)


class NiriTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="weasel-niri-gate-test-")
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.store = self.root / "store"
        self.store.mkdir()
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "flake.lock").write_text('{"version":7}')
        self.main = self.root / "mutable-main/programs/niri"
        (self.main / "dms").mkdir(parents=True)
        (self.main / "dms/colors.kdl").write_bytes(b"mutable main bytes\n")
        frozen = self.source / "programs/niri/dms/colors.kdl"
        frozen.parent.mkdir(parents=True)
        frozen.write_bytes(b"frozen candidate bytes\n")
        self.app = self.store / ("a" * 32 + "-niri")
        (self.app / "bin").mkdir(parents=True)
        executable = self.app / "bin/niri"
        executable.write_text('#!' + sys.executable + '\n'
            'import json, os, pathlib, sys\n'
            'args=sys.argv[1:]\n'
            'assert len(args)==3 and args[0]=="validate" and args[1]=="--config"\n'
            'config=pathlib.Path(args[2])\n'
            'assert config.read_text().startswith("include ")\n'
            'assert (config.parent/"dms/colors.kdl").read_bytes()==b"frozen candidate bytes\\n"\n'
            'pathlib.Path("observed.json").write_text(json.dumps({"uid":os.getuid(),"argv":args,"environment":dict(os.environ)}))\n'
            'print("private configuration validated")\n')
        executable.chmod(0o555)
        self.app.chmod(0o555)
        config = self.store / ("b" * 32 + "-generated-config")
        config.write_bytes(b'include "dms/colors.kdl"\n'); config.chmod(0o444)
        dms = self.store / ("c" * 32 + "-dms-link")
        dms.symlink_to(self.main / "dms/colors.kdl")
        self.metadata = {"app": str(self.app), "sources": {"niri/config.kdl": str(config), "niri/dms/colors.kdl": str(dms)}}
        self.nix = str(self.store / ("d" * 32 + "-nix/bin/nix"))
        self.calls = []
        original_command = niri.run_command
        def command(argv, environment, directory, *, timeout):
            self.calls.append((argv, environment, timeout))
            if argv[0] == self.nix:
                return subprocess.CompletedProcess(argv, 0, json.dumps(self.metadata).encode(), b"")
            return original_command(argv, environment, directory, timeout=timeout)
        self.stack = []
        for mock in (patch.object(niri, "STORE_ROOT", self.store), patch.object(niri, "MAIN_NIRI", self.main),
                     patch.object(niri, "trusted_nix", return_value=self.nix), patch.object(niri, "run_command", side_effect=command)):
            mock.start(); self.addCleanup(mock.stop)

    def test_actual_fixture_uses_frozen_dms_and_exact_generated_config(self):
        run_dir = self.root / "new-parent/probes/niri"
        with patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-live", "NIRI_SOCKET": "/private/live-niri", "DBUS_SESSION_BUS_ADDRESS": "private-session", "OPENAI_API_KEY": "fixture-token", "SSH_AUTH_SOCK": "/private/live-agent"}):
            receipt = niri.probe(self.source, run_dir)
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["files"]["dms/colors.kdl"], hashlib.sha256(b"frozen candidate bytes\n").hexdigest())
        self.assertEqual(receipt["file_origins"], {"config.kdl": "immutable-store", "dms/colors.kdl": "frozen-source"})
        self.assertEqual((self.main / "dms/colors.kdl").read_bytes(), b"mutable main bytes\n")
        observed = json.loads((run_dir / "observed.json").read_text())
        self.assertEqual(observed["uid"], os.getuid())
        self.assertEqual(observed["argv"], ["validate", "--config", str(run_dir / "fixture/config.kdl")])
        for name in ("DISPLAY", "WAYLAND_DISPLAY", "NIRI_SOCKET", "DBUS_SESSION_BUS_ADDRESS", "OPENAI_API_KEY", "SSH_AUTH_SOCK"):
            self.assertNotIn(name, observed["environment"])
        self.assertEqual(stat.S_IMODE(run_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((run_dir / "receipt.json").stat().st_mode), 0o600)
        self.assertEqual(json.loads((run_dir / "receipt.json").read_text()), receipt)
        self.assertEqual(self.calls[0][0][1:6], ["eval", "--raw", "--impure", "--no-write-lock-file", "--expr"])
        self.assertIn("config-parse-only", receipt["coverage"])
        self.assertIn("unobserved", receipt["coverage"])

    def test_main_link_target_can_be_absent_without_reading_mutable_main(self):
        (self.main / "dms/colors.kdl").unlink()
        self.assertTrue(niri.probe(self.source, self.root / "fixture")["ok"])

    def test_production_arguments_are_accepted_by_real_niri_when_installed(self):
        executable = shutil.which("niri")
        if executable is None:
            self.skipTest("Built Niri is unavailable; real candidate probe remains required")
        run_dir = self.root / "real-parser"
        run_dir.mkdir(mode=0o700)
        config = run_dir / "config.kdl"
        config.write_text("// Isolated parser fixture with no session connection.\n")
        environment = niri.private_environment(run_dir, self.nix)
        result = niri.run_command(niri.validation_arguments(executable, config), environment, run_dir, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_root_is_refused_before_creating_fixture(self):
        target = self.root / "fixture"
        with patch.object(niri.os, "geteuid", return_value=0), self.assertRaisesRegex(niri.NiriGateError, "ordinary user"):
            niri.probe(self.source, target)
        self.assertFalse(target.exists())
        self.assertEqual(self.calls, [])

    def test_reused_fixture_is_refused_and_cli_never_prints_its_receipt(self):
        target = self.root / "fixture"
        target.mkdir()
        (target / "receipt.json").write_text('"existing private fixture token"')
        with self.assertRaisesRegex(niri.NiriGateError, "fresh"):
            niri.probe(self.source, target)
        with patch.object(sys, "argv", ["gate", "--source", str(self.source), "--run-dir", str(target)]), patch("builtins.print") as emitted:
            self.assertEqual(niri.main(), 1)
        self.assertNotIn("existing private fixture token", str(emitted.call_args_list))

    def test_personal_relative_and_traversal_sources_are_refused(self):
        for value in (str(self.main / "dms/colors.kdl"), "relative/config.kdl", str(self.store / "../personal.kdl")):
            self.metadata["sources"]["niri/config.kdl"] = value
            target = self.root / ("fixture-" + str(len(self.calls)))
            with self.subTest(source=value), self.assertRaises(niri.NiriGateError):
                niri.probe(self.source, target)
            receipt = json.loads((target / "receipt.json").read_text())
            self.assertFalse(receipt["ok"])
            self.assertTrue(all(call[0][0] == self.nix for call in self.calls))

    def test_arbitrary_personal_store_link_is_not_followed(self):
        link = self.store / ("e" * 32 + "-personal-link")
        private = self.root / "personal-secret.kdl"
        private.write_text("private test-only token")
        link.symlink_to(private)
        self.metadata["sources"]["niri/config.kdl"] = str(link)
        with self.assertRaisesRegex(niri.NiriGateError, "outside the immutable Store"):
            niri.probe(self.source, self.root / "fixture")
        self.assertEqual(private.read_text(), "private test-only token")

    def test_frozen_source_symlink_escape_is_refused(self):
        file = self.source / "programs/niri/dms/colors.kdl"
        file.unlink(); file.symlink_to(self.main / "dms/colors.kdl")
        with self.assertRaises(niri.NiriGateError):
            niri.probe(self.source, self.root / "fixture")
        self.assertTrue(all(call[0][0] == self.nix for call in self.calls))

    def test_source_and_run_parent_symlinks_are_refused(self):
        alias = self.root / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(OSError):
            niri.probe(alias, self.root / "fixture")
        parent = self.root / "parent-link"
        parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            niri.probe(self.source, parent / "fixture")
        self.assertFalse((self.root / "fixture").exists())

    def test_target_escape_and_missing_main_config_are_refused(self):
        original = dict(self.metadata["sources"])
        for target in ("niri/../../private", "niri/./config.kdl", "niri//config.kdl", "other/config.kdl"):
            self.metadata["sources"] = dict(original, **{target: original["niri/config.kdl"]})
            with self.subTest(target=target), self.assertRaises(niri.NiriGateError):
                niri.probe(self.source, self.root / ("fixture-" + str(len(self.calls))))
        self.metadata["sources"] = {"niri/dms/colors.kdl": original["niri/dms/colors.kdl"]}
        with self.assertRaisesRegex(niri.NiriGateError, "incomplete"):
            niri.probe(self.source, self.root / "missing")

    def test_writable_store_file_or_package_is_refused(self):
        config = Path(self.metadata["sources"]["niri/config.kdl"])
        config.chmod(0o644)
        with self.assertRaisesRegex(niri.NiriGateError, "writable"):
            niri.probe(self.source, self.root / "fixture")
        config.chmod(0o444); self.app.chmod(0o755)
        with self.assertRaisesRegex(niri.NiriGateError, "writable"):
            niri.probe(self.source, self.root / "package")

    def test_lock_mutation_by_evaluator_refuses_before_execution(self):
        def changed(argv, environment, directory, **kwargs):
            (self.source / "flake.lock").write_text("modified")
            return subprocess.CompletedProcess(argv, 0, json.dumps(self.metadata).encode(), b"")
        with patch.object(niri, "run_command", side_effect=changed), self.assertRaisesRegex(niri.NiriGateError, "changed candidate flake.lock"):
            niri.probe(self.source, self.root / "fixture")

    def test_validation_failure_has_private_logs_and_honest_receipt(self):
        def failed(argv, environment, directory, **kwargs):
            if argv[0] == self.nix:
                return subprocess.CompletedProcess(argv, 0, json.dumps(self.metadata).encode(), b"")
            return subprocess.CompletedProcess(argv, 1, b"", b"private parser context")
        target = self.root / "fixture"
        with patch.object(niri, "run_command", side_effect=failed), self.assertRaisesRegex(niri.NiriGateError, "validation failed") as error:
            niri.probe(self.source, target)
        receipt = json.loads((target / "receipt.json").read_text())
        self.assertFalse(receipt["ok"])
        self.assertNotIn("private parser context", str(error.exception) + json.dumps(receipt))
        self.assertEqual((target / "validate.stderr").read_bytes(), b"private parser context")
        self.assertEqual(stat.S_IMODE((target / "validate.stderr").stat().st_mode), 0o600)

    def test_timeouts_are_bounded_and_do_not_expose_command_output(self):
        with patch.object(niri.subprocess, "run", side_effect=subprocess.TimeoutExpired("fixture", 1, output=b"private timeout output")):
            with self.assertRaisesRegex(niri.NiriGateError, "time bound") as error:
                niri.run_command(["fixture"], {}, self.root, timeout=1)
        self.assertNotIn("private timeout output", str(error.exception))


if __name__ == "__main__":
    unittest.main()
