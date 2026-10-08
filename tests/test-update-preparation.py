#!/usr/bin/env python3
"""Preparation refusal and concurrency invariants on disposable real files."""
import importlib.util
import datetime as dt
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preparation', ROOT / 'scripts/weasel-update-prepare.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PreparationTests(unittest.TestCase):
    def test_exclusive_publication_keeps_concurrent_request(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            old, new = directory / 'request.json', directory / 'new.json'
            old.write_bytes(b'concurrent')
            new.write_bytes(b'tested')
            with self.assertRaises(FileExistsError):
                p.publish_exclusive(new, old)
            self.assertEqual(old.read_bytes(), b'concurrent')
            self.assertEqual(new.read_bytes(), b'tested')

    def test_published_inode_is_complete_and_single_link(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            staged, destination = directory / 'staged', directory / 'request.json'
            staged.write_bytes(b'{"complete":true}')
            inode = staged.stat().st_ino
            p.publish_exclusive(staged, destination)
            self.assertEqual(destination.stat().st_ino, inode)
            self.assertEqual(destination.stat().st_nlink, 1)
            self.assertFalse(staged.exists())

    def test_candidate_id_cannot_escape_namespace(self):
        for value in ['../documents', '20261008T120000Z-aaaaaaaa/../../x', 'x', '20261008T120000Z-AAAA0000']:
            with self.assertRaises(p.Blocked):
                p.candidate_directory(Path('/tmp/unused'), value)

    def test_state_file_symlink_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            real = directory / 'real.json'
            real.write_text('{"value":1}')
            link = directory / 'request.json'
            link.symlink_to(real)
            with self.assertRaises(OSError):
                p.read_json(link)

    def test_battery_and_power_failure_are_real_refusals(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for name, values in [('AC', {'type': 'Mains', 'online': '1'}), ('BAT0', {'type': 'Battery', 'capacity': '90'})]:
                target = directory / name
                target.mkdir()
                for key, value in values.items():
                    (target / key).write_text(value)
            p.require_power(directory)
            (directory / 'AC/online').write_text('0')
            with self.assertRaises(p.Blocked):
                p.require_power(directory)
            (directory / 'AC/online').write_text('1')
            (directory / 'BAT0/capacity').write_text('29')
            with self.assertRaises(p.Blocked):
                p.require_power(directory)

    def test_all_unresolved_transaction_phases_block_new_candidates(self):
        with tempfile.TemporaryDirectory() as folder:
            status = Path(folder) / 'status.json'
            with patch.object(p, 'STATUS', status):
                for phase in ['recovery-required', 'checkpoint-created', 'activating', 'publishing', 'rolling-back-system']:
                    status.write_text(json.dumps({'phase': phase}))
                    with self.assertRaises(p.Blocked):
                        p.require_resolved()
                status.write_text(json.dumps({'phase': 'complete'}))
                p.require_resolved()

    def test_hidden_working_file_save_changes_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            subprocess.run(['git', 'init', '-q', '-b', 'main', repo], check=True)
            subprocess.run(['git', '-C', repo, 'config', 'user.name', 'Fixture'], check=True)
            subprocess.run(['git', '-C', repo, 'config', 'user.email', 'fixture@invalid'], check=True)
            file = repo / 'source.nix'
            file.write_text('old source')
            subprocess.run(['git', '-C', repo, 'add', 'source.nix'], check=True)
            subprocess.run(['git', '-C', repo, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture'], check=True)
            before = p.source_manifest(repo)
            subprocess.run(['git', '-C', repo, 'update-index', '--assume-unchanged', 'source.nix'], check=True)
            # Ignore the flag's index change: capture it before the editor save.
            before = p.source_manifest(repo)
            file.write_text('new unsaved-to-git source')
            self.assertNotEqual(p.source_manifest(repo), before)

    def test_review_coverage_cannot_silently_drop_unknown_pin(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            registry = directory / 'registry.json'
            registry.write_text(json.dumps({'entries': [{'id': 't3'}, {'id': 'unknown-pin'}]}))
            review = directory / 'review.json'
            review.write_text(json.dumps({'entries': [{'id': 't3', 'decision': 'unchanged'}]}))
            with patch.object(p, 'registry_path', return_value=registry):
                with self.assertRaisesRegex(p.Blocked, 'every registered'):
                    p.record_review(directory, review)

    def test_review_accepts_new_pin_and_dated_explicit_adapter_need(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            registry = directory / 'registry.json'
            registry.write_text(json.dumps({'entries': [{'id': 'known-pin'}]}))
            tomorrow = (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=1)).isoformat()
            entries = [{'id': name, 'decision': 'adapter-needed', 'current': '1.0.0',
                        'reason': 'Device hotplug needs a concrete probe',
                        'next_review': tomorrow, 'evidence_urls': ['https://example.invalid/release']}
                       for name in ['known-pin', 'new-pin']]
            review = directory / 'review.json'
            review.write_text(json.dumps({'schema_version': 1, 'entries': entries,
                                          'baseline_commit': 'a' * 40, 'lock_nodes': {}}))
            with patch.object(p, 'registry_path', return_value=registry), patch.object(
                    p, 'review_baseline', return_value={'commit': 'a' * 40, 'lock_sha256': 'b' * 64, 'nodes': {}}):
                result = p.record_review(directory, review)
            self.assertEqual(result['entries'], 2)

    def test_transitive_lock_node_coverage_and_revision_are_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            registry = directory / 'registry.json'
            registry.write_text(json.dumps({'entries': []}))
            review = directory / 'review.json'
            locked = {'type': 'github', 'owner': 'fixture', 'repo': 'upstream', 'rev': 'c' * 40}
            baseline = {'commit': 'a' * 40, 'lock_sha256': 'b' * 64,
                        'nodes': {'transitive': locked}}
            finding = {'current_locked': locked, 'decision': 'investigate',
                       'reason': 'Follow parent update; upstream freshness remains unverified',
                       'next_review': (dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=1)).isoformat(),
                       'evidence': ['repo:flake.lock#nodes.transitive']}
            value = {'entries': [], 'baseline_commit': baseline['commit'], 'lock_nodes': {}}
            with patch.object(p, 'registry_path', return_value=registry), patch.object(
                    p, 'review_baseline', return_value=baseline):
                review.write_text(json.dumps(value))
                with self.assertRaisesRegex(p.Blocked, 'every resolved'):
                    p.record_review(directory, review)
                value['lock_nodes']['transitive'] = finding
                value['lock_nodes']['transitive']['current_locked'] = dict(locked, rev='d' * 40)
                review.write_text(json.dumps(value))
                with self.assertRaisesRegex(p.Blocked, 'exact source'):
                    p.record_review(directory, review)
                finding['current_locked'] = locked
                value['baseline_commit'] = 'e' * 40
                review.write_text(json.dumps(value))
                with self.assertRaisesRegex(p.Blocked, 'actual current'):
                    p.record_review(directory, review)
                value['baseline_commit'] = baseline['commit']
                review.write_text(json.dumps(value))
                result = p.record_review(directory, review)
                self.assertEqual(result['resolved_lock_nodes'], 1)
                receipt = json.loads(Path(result['path']).read_text())
                self.assertEqual(receipt['coverage']['lock_sha256'], baseline['lock_sha256'])

    def test_review_source_race_cannot_publish_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            registry = directory / 'registry.json'
            registry.write_text(json.dumps({'entries': []}))
            review = directory / 'review.json'
            baseline = {'commit': 'a' * 40, 'lock_sha256': 'b' * 64, 'nodes': {}}
            review.write_text(json.dumps({'entries': [], 'baseline_commit': baseline['commit'], 'lock_nodes': {}}))
            with patch.object(p, 'registry_path', return_value=registry), patch.object(
                    p, 'review_baseline', side_effect=[baseline, dict(baseline, lock_sha256='c' * 64)]):
                with self.assertRaisesRegex(p.Blocked, 'Source changed'):
                    p.record_review(directory, review)
            self.assertFalse((directory / 'reviews').exists())

    def test_allowlisted_helper_cannot_overwrite_personal_output(self):
        with self.assertRaises(p.Blocked):
            p.check_cli_paths(p.REPOSITORY, p.STATE, Path('/home/evilweasel/.codex/auth.json'))

    def test_explicit_output_preserves_file_created_after_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder) / 'receipt.json'
            p.check_cli_paths(p.REPOSITORY, p.STATE, receipt)
            receipt.write_bytes(b'concurrent save')
            with self.assertRaises(FileExistsError):
                p.write_receipt_exclusive(receipt, b'new receipt')
            self.assertEqual(receipt.read_bytes(), b'concurrent save')

    def test_explicit_output_parent_swap_cannot_follow_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / 'receipts'
            other = Path(folder) / 'personal'
            parent.mkdir()
            other.mkdir()
            receipt = parent / 'auth.json'
            p.check_cli_paths(p.REPOSITORY, p.STATE, receipt)
            parent.rmdir()
            parent.symlink_to(other, target_is_directory=True)
            with self.assertRaises(OSError):
                p.write_receipt_exclusive(receipt, b'new receipt')
            self.assertFalse((other / 'auth.json').exists())

    def test_interrupted_unsubmitted_candidate_is_retained_and_resolved(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            identifier = '20261008T120000Z-1234abcd'
            directory = state / 'candidates' / identifier
            directory.mkdir(parents=True)
            marker = directory / 'candidate.json'
            marker.write_text(json.dumps({'id': identifier, 'source': str(directory / 'source'),
                                          'phase': 'building'}))
            with patch.object(p, 'STATUS', state / 'absent-status'):
                p.prune_candidates(Path('/unused/repository'), state)
            self.assertTrue(directory.exists())
            self.assertEqual(json.loads(marker.read_text())['phase'], 'failed')

    def test_prune_preserves_editor_changes_untracked_ignored_and_open_files(self):
        for change in ['tracked', 'hidden', 'untracked', 'ignored', 'open', 'extra-artifact', 'clean']:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                repo, state = root / 'main', root / 'state'
                subprocess.run(['git', 'init', '-q', '-b', 'main', repo], check=True)
                subprocess.run(['git', '-C', repo, 'config', 'user.name', 'Fixture'], check=True)
                subprocess.run(['git', '-C', repo, 'config', 'user.email', 'fixture@invalid'], check=True)
                (repo / 'source.nix').write_text('tested source')
                (repo / '.gitignore').write_text('ignored.txt\n')
                subprocess.run(['git', '-C', repo, 'add', '.'], check=True)
                subprocess.run(['git', '-C', repo, '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture'], check=True)
                identifier = '20261008T120000Z-1234abcd'
                directory = state / 'candidates' / identifier
                directory.mkdir(parents=True)
                source = directory / 'source'
                subprocess.run(['git', '-C', repo, 'worktree', 'add', '-q', '-b',
                                'weasel-update-' + identifier, source], check=True)
                manifest = p.source_manifest(source)
                (directory / 'candidate.json').write_text(json.dumps({
                    'id': identifier, 'source': str(source), 'phase': 'tested',
                    'candidate_commit': manifest['head'], 'candidate_manifest': manifest}))
                stream = None
                if change in {'tracked', 'hidden'}:
                    if change == 'hidden':
                        subprocess.run(['git', '-C', source, 'update-index', '--assume-unchanged', 'source.nix'], check=True)
                    (source / 'source.nix').write_text('later editor save')
                elif change in {'untracked', 'ignored'}:
                    (source / ('ignored.txt' if change == 'ignored' else 'notes.txt')).write_text('personal notes')
                elif change == 'open':
                    stream = (source / 'source.nix').open('rb')
                elif change == 'extra-artifact':
                    (directory / 'personal-notes.txt').write_text('preserve')
                try:
                    with patch.object(p, 'STATUS', root / 'absent-status'):
                        p.prune_candidates(repo, state, keep=0)
                    self.assertEqual(directory.exists(), change != 'clean')
                    if change in {'tracked', 'hidden'}:
                        self.assertEqual((source / 'source.nix').read_text(), 'later editor save')
                finally:
                    if stream:
                        stream.close()


if __name__ == '__main__':
    unittest.main()
