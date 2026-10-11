#!/usr/bin/env python3
"""Safety boundaries for allocation maintenance and snapshot exclusions."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


health = load('weasel-btrfs-health')
excludes = load('weasel-snapshot-excludes')


def row(unallocated=7, errors=0, free=150):
    return {'unallocated_bytes': unallocated * health.GIB, 'free_bytes': free * health.GIB,
            'device_errors': errors, 'metadata': {
                'total_bytes': 12 * health.GIB, 'bytes_used': 11 * health.GIB,
                'bytes_reserved': 2 * health.GIB, 'bytes_pinned': 0,
                'bytes_may_use': 0, 'bytes_readonly': 0}}


class SafetyTests(unittest.TestCase):
    def test_latest_complete_status_cannot_hide_unresolved_journal(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = root / 'status.json'
            status.write_text(json.dumps({'phase': 'complete'}))
            for namespace in ('runs', 'bootstrap', 'manual-computer-use'):
                entry = root / namespace / 'transaction'
                entry.mkdir(parents=True)
                journal = entry / 'journal.json'
                self.assertIsNotNone(health.transaction_reason(root, status))
                journal.write_text(json.dumps({'phase': 'recovery-required'}))
                self.assertIsNotNone(health.transaction_reason(root, status))
                journal.write_text(json.dumps({'phase': 'complete'}))
                self.assertIsNone(health.transaction_reason(root, status))
            (root / 'runs/transaction/journal.json').write_text(json.dumps({'phase': 'failed-before-integration'}))
            self.assertIsNone(health.transaction_reason(root, status))

    def test_generous_reserve_thresholds_and_bounded_target(self):
        calls = []
        measured = iter([row(39), row(40), row(50)])
        with patch.object(health, 'transaction_reason', return_value=None), \
             patch.object(health, 'active_build', return_value=None):
            result = health.maintain('/home', lambda p: next(measured),
                                    lambda *args: calls.append(args) or 'No balance found')
        self.assertEqual(result['after_unallocated_bytes'], 50 * health.GIB)
        self.assertEqual(len([args for args in calls if 'start' in args]), 2)
        self.assertEqual(health.pressure(row(39))['level'], 'watch')
        self.assertEqual(health.pressure(row(50))['level'], 'healthy')

    def test_migration_refuses_low_reserve_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / 'target'
            target.mkdir()
            with patch.object(excludes.os, 'geteuid', return_value=0), \
                 patch.object(excludes, 'recognized', return_value=True), \
                 patch.object(excludes, 'tracked', return_value=False), \
                 patch.object(excludes.HEALTH, 'measure', return_value=row(unallocated=1)), \
                 patch.object(excludes.HEALTH, 'write_json') as write, \
                 patch.object(excludes.subprocess, 'run') as command:
                with self.assertRaisesRegex(RuntimeError, 'reserve'):
                    excludes.migrate(target, root)
                write.assert_not_called()
                command.assert_not_called()
            self.assertEqual(list(root.iterdir()), [target])

    def test_reservations_are_not_a_used_percentage(self):
        result = health.pressure(row())
        self.assertAlmostEqual(result['metadata_used_fraction'], 11 / 12)
        self.assertEqual(result['metadata_reservations_bytes'], 2 * health.GIB)
        self.assertEqual(result['metadata_commitment_headroom_bytes'], 0)
        self.assertEqual(result['level'], 'critical')

    def test_build_transaction_and_existing_balance_do_not_mutate(self):
        for transaction, build, status in [('unresolved', None, ''), (None, 'build', ''),
                                            (None, None, 'Balance on /home is running')]:
            calls = []
            with patch.object(health, 'transaction_reason', return_value=transaction), \
                 patch.object(health, 'active_build', return_value=build):
                result = health.maintain('/home', lambda p: row(),
                                        lambda *args: calls.append(args) or status)
            self.assertEqual(result['outcome'], 'deferred')
            self.assertFalse(any('start' in args for args in calls))

    def test_data_only_passes_stop_at_target_and_have_a_chunk_limit(self):
        calls = []
        measured = iter([row(), row(9), row(50)])
        with patch.object(health, 'transaction_reason', return_value=None), \
             patch.object(health, 'active_build', return_value=None):
            result = health.maintain('/home', lambda p: next(measured),
                                    lambda *args: calls.append(args) or 'No balance found')
        starts = [args for args in calls if 'start' in args]
        self.assertEqual([args[3] for args in starts], ['-dusage=0', '-dusage=5,limit=8'])
        self.assertEqual(result['after_unallocated_bytes'], 50 * health.GIB)

    def test_timeout_cancels_owned_kernel_balance(self):
        calls = []
        def run(*args):
            calls.append(args)
            if 'start' in args:
                raise subprocess.TimeoutExpired(args, 120)
            return 'No balance found'
        with patch.object(health, 'transaction_reason', return_value=None), \
             patch.object(health, 'active_build', return_value=None):
            result = health.maintain('/home', lambda p: row(), run)
        self.assertIn(('btrfs', 'balance', 'cancel', '/home'), calls)
        self.assertEqual(result['outcome'], 'cancelled')

    def test_errors_and_low_free_space_prevent_balance(self):
        for sample in (row(errors=1), row(free=20), row(unallocated=51)):
            calls = []
            health.maintain('/home', lambda p: sample, lambda *args: calls.append(args))
            self.assertEqual(calls, [])

    def test_unrecognized_and_tracked_directories_remain_in_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('build', 'dist', 'bin', 'obj', 'target', 'node_modules'):
                path = root / name
                path.mkdir()
                self.assertFalse(excludes.recognized(path))
            (root / 'Cargo.toml').touch()
            (root / 'target/.rustc_info.json').touch()
            self.assertTrue(excludes.recognized(root / 'target'))
            (root / 'package.json').touch()
            self.assertTrue(excludes.recognized(root / 'node_modules'))
            (root / 'linked').symlink_to(root / 'target')
            self.assertFalse(excludes.recognized(root / 'linked'))
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', '-C', str(root), 'add', 'target/.rustc_info.json'], check=True)
            self.assertTrue(excludes.tracked(root / 'target'))


if __name__ == '__main__':
    unittest.main()
