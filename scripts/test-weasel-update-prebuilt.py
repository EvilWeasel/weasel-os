#!/usr/bin/env python3
"""Pure receipt and source-policy tests; never invoke Nix or activate a system."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("prebuilt", Path(__file__).with_name("weasel-update-prebuilt.py"))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def fixture():
    return dict(schema=1, host="nixy-laptop", sourceCommit="a" * 40, sourceTree="b" * 40,
                baselineCommit=p.BASELINE, baselineSystem=p.BASELINE_SYSTEM,
                systemPath="/nix/store/" + "c" * 32 + "-nixos-system-nixy-laptop-26.05",
                systemDrv="/nix/store/" + "d" * 32 + "-system.drv", flakeLockSha256=p.LOCK_HASH,
                archive="nixy-laptop.nar.zst", archiveSha256="e" * 64,
                githubRepository="morrowbyte/weasel-os", githubRunId="123", githubRunAttempt="1")


class FakeRunner:
    def __init__(self, **overrides):
        self.values = {("rev-parse", "HEAD"): "a" * 40, ("rev-parse", "HEAD^{tree}"): "b" * 40,
                       ("show", "-s", "--format=%P", "HEAD"): p.BASELINE,
                       ("status", "--porcelain", "--untracked-files=all"): "",
                       ("verify-commit", "--raw", "HEAD"): "",
                       ("show", "-s", "--format=%G? %GF %GP", "HEAD"): "G signing-subkey " + p.a.EXPECTED_PRIMARY_FINGERPRINT,
                       ("diff", "--name-only", p.BASELINE, "HEAD"): "programs/t3code-client.nix"}
        self.overrides = overrides

    def git(self, source, *args):
        if args == ("diff", "--name-only", p.BASELINE, "HEAD") and self.overrides.get("path"):
            return self.overrides["path"].encode()
        if args[0:2] == ("show", p.BASELINE + ":flake.lock") or args == ("show", "HEAD:flake.lock"):
            return b"locked"
        fixture = b"fixture {\n" + p.FIXTURE_BEFORE + b"\n}\n"
        if args == ("show", p.BASELINE + ":" + p.FIXTURE_PATH):
            return fixture
        if args == ("show", "HEAD:" + p.FIXTURE_PATH):
            candidate = fixture.replace(p.FIXTURE_BEFORE, p.FIXTURE_AFTER)
            return candidate + (b"runtime change" if self.overrides.get("runtime_change") else b"")
        return self.values[args].encode()


class Policy(unittest.TestCase):
    def test_valid_receipt(self):
        self.assertEqual(p.validate_receipt(fixture())["host"], "nixy-laptop")

    def test_rejects_changed_or_unrelated_identity(self):
        for field, value in [("baselineCommit", "f" * 40), ("baselineSystem", fixture()["systemPath"]),
                             ("flakeLockSha256", "0" * 64), ("host", "hephaestus"),
                             ("sourceCommit", "HEAD"), ("schema", True), ("archive", "../payload"),
                             ("githubRepository", "someone/weasel-os"), ("systemPath", "/tmp/system")]:
            with self.subTest(field=field):
                record = copy.deepcopy(fixture())
                record[field] = value
                with self.assertRaises(p.a.ActivationError):
                    p.validate_receipt(record)

    def test_no_unknown_receipt_fields(self):
        record = fixture()
        record["command"] = "nix build"
        with self.assertRaises(p.a.ActivationError):
            p.validate_receipt(record)

    def test_unrelated_source_path_rejected_before_lock_check(self):
        with self.assertRaises(p.a.ActivationError):
            p.source_guard(FakeRunner(path="programs/computer-use.nix"),
                           Path("/home/evilweasel/.t3-morrowbyte/worktrees/weasel-os/candidate"), fixture())

    def test_canonical_checkout_rejected(self):
        with self.assertRaises(p.a.ActivationError):
            p.source_guard(FakeRunner(), Path("/home/evilweasel/weasel-os"), fixture())

    def test_exact_clean_signed_source_passes(self):
        with patch.object(p.a, "digest", return_value=p.LOCK_HASH):
            p.source_guard(FakeRunner(),
                           Path("/home/evilweasel/.t3-morrowbyte/worktrees/weasel-os/candidate"), fixture())

    def test_source_guards_fail_closed(self):
        variations = [(('rev-parse', 'HEAD'), 'f' * 40),
                      (('show', '-s', '--format=%P', 'HEAD'), 'f' * 40),
                      (('status', '--porcelain', '--untracked-files=all'), ' M programs/t3code-client.nix'),
                      (('show', '-s', '--format=%G? %GF %GP', 'HEAD'), 'G subkey wrong-primary')]
        for key, value in variations:
            runner = FakeRunner()
            runner.values[key] = value
            with self.subTest(key=key), self.assertRaises(p.a.ActivationError):
                p.source_guard(runner, Path('/home/evilweasel/.t3-morrowbyte/worktrees/weasel-os/candidate'), fixture())

    def test_only_exact_test_fixture_patch_is_allowed(self):
        source = Path('/home/evilweasel/.t3-morrowbyte/worktrees/weasel-os/candidate')
        with patch.object(p.a, "digest", return_value=p.LOCK_HASH):
            p.source_guard(FakeRunner(path=p.FIXTURE_PATH), source, fixture())
            with self.assertRaises(p.a.ActivationError):
                p.source_guard(FakeRunner(path=p.FIXTURE_PATH, runtime_change=True), source, fixture())


if __name__ == "__main__":
    unittest.main()
