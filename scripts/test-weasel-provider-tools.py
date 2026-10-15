"""Namespace-only protocol fixtures; fake providers never call a model or GUI."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('weasel-provider-tools.py')
spec = importlib.util.spec_from_file_location('provider_tools', SCRIPT)
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


def command(*args):
    return subprocess.check_output(args, text=True).strip()


class ProviderToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('nix-store') or not shutil.which('zstd'):
            raise RuntimeError('Run these real Store/import fixtures on Namespace with Nix and zstd')
        cls.fixtures = tempfile.TemporaryDirectory(prefix='provider-fixture-')
        cls.addClassCleanup(cls.fixtures.cleanup)
        cls.root = Path(cls.fixtures.name)
        cls.source = 'a' * 40
        cls.receipts = {}
        cls.archives = {}
        for role, cv, av in [('baseline', '0.162.0', '2.1.223'), ('candidate', '0.162.1', '2.1.300')]:
            packages = {}
            for package, names, version in [('codex', ['codex', 'codex-code-mode-host'], cv), ('acp', ['codex-acp'], '2.2.2'), ('claude', ['claude'], av)]:
                directory = cls.root / (role + '-' + package)
                (directory / 'bin').mkdir(parents=True)
                for name in names:
                    binary = directory / 'bin' / name
                    binary.write_text(f'#!{sys.executable}\nimport sys,time\nif "--hold" in sys.argv: time.sleep(30)\nprint({(name + " " + version)!r})\n')
                    binary.chmod(0o755)
                packages[package] = command('nix-store', '--add', str(directory))
            metadata = dict(schema=1, system='x86_64-linux', role=role,
                codex=dict(version=cv, storePath=packages['codex'], sourceRevision=cls.source,
                    patches={'codex-v0162-scoped-cancel.patch':'1'*64, 'scoped-cancel-memory-tests.patch':'2'*64}),
                claude=dict(version=av, storePath=packages['claude'], recipe='locked-stable-nixpkgs/claude-code'),
                acp=dict(version='2.2.2', storePath=packages['acp'], codexPath=packages['codex']+'/bin/codex'))
            bundle = cls.root / (role + '-bundle')
            (bundle / 'bin').mkdir(parents=True)
            for name in manager.NAMES:
                package = 'acp' if name == 'codex-acp' else 'claude' if name == 'claude' else 'codex'
                (bundle / 'bin' / name).symlink_to(packages[package] + '/bin/' + name)
            manifest = json.dumps(metadata, sort_keys=True).encode()
            (bundle / 'provider-tools.json').write_bytes(manifest)
            store = command('nix-store', '--add', str(bundle))
            archive = cls.root / (role + '.nar.zst')
            paths = command('nix-store', '--query', '--requisites', store).splitlines()
            with archive.open('wb') as output, subprocess.Popen(['nix-store', '--export', *paths], stdout=subprocess.PIPE) as exporter:
                subprocess.run(['zstd', '-q', '-c'], stdin=exporter.stdout, stdout=output, check=True)
                exporter.stdout.close()
                if exporter.wait() != 0: raise RuntimeError('fixture export failed')
            receipt = dict(schema=1, repository='morrowbyte/weasel-os', system='x86_64-linux',
                role=role, sourceCommit=cls.source, ciRunId=123,
                storePath=store, narHash=command('nix','hash','path','--type','sha256','--sri',store),
                archiveSha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                bundleManifestSha256=hashlib.sha256(manifest).hexdigest(), providers=metadata)
            cls.receipts[role] = receipt
            cls.archives[role] = archive

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='provider-test-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.state = self.work / 'state'
        baseline = self.receipts['baseline']['providers']
        paths = [baseline[k]['storePath']+'/bin' for k in ['codex','claude','acp']]
        self.env = {**os.environ, 'PATH':os.pathsep.join(paths+[os.environ['PATH']])}

    def invoke(self, *args, ok=True):
        result = subprocess.run([sys.executable,str(SCRIPT),'--state-dir',str(self.state),*args],
            env=self.env,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode == 0, ok, result.stdout+result.stderr)
        return result

    def prepare(self, role, mutate=None, ok=True, source=None):
        receipt = json.loads(json.dumps(self.receipts[role]))
        if mutate: mutate(receipt)
        raw = json.dumps(receipt,sort_keys=True).encode()
        path = self.work / (role+'.json'); path.write_bytes(raw)
        identifier = hashlib.sha256(raw).hexdigest()
        result = self.invoke('prepare','--receipt',str(path),'--receipt-sha256',identifier,
            '--source-commit',source or self.source,'--archive',str(self.archives[role]),ok=ok)
        return identifier, result

    def bootstrap(self):
        identifier,_ = self.prepare('baseline')
        self.invoke('activate',identifier)
        return identifier

    def test_status_does_not_create_state(self):
        self.invoke('status')
        self.assertFalse(self.state.exists())

    def test_candidate_cannot_bootstrap_a_new_version(self):
        identifier,_ = self.prepare('candidate')
        self.invoke('activate',identifier,ok=False)
        self.assertFalse((self.state/'current').exists())

    def test_prepare_switch_and_rollback_preserve_old_process(self):
        self.bootstrap()
        old = os.readlink(self.state/'current')
        child = subprocess.Popen([str(self.state/'current/bin/codex'),'--hold'], env=self.env,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            identifier,_ = self.prepare('candidate')
            self.assertEqual(os.readlink(self.state/'current'),old)
            self.invoke('activate',identifier)
            self.assertIsNone(child.poll())
            self.assertIn('2.1.300', command(str(self.state/'current/bin/claude'),'--version'))
            self.assertIn('0.162.1', command(str(self.state/'current/bin/codex'),'--version'))
            status=json.loads(self.invoke('status').stdout)
            self.assertEqual(status['declaredProviders']['acp']['codexPath'],
                self.receipts['candidate']['providers']['codex']['storePath']+'/bin/codex')
            self.invoke('rollback')
            self.assertEqual(os.readlink(self.state/'current'),old)
            self.assertIn('2.1.223', command(str(self.state/'current/bin/claude'),'--version'))
        finally:
            child.terminate(); child.wait(timeout=5)

    def test_wrong_source_is_rejected_before_state_or_import(self):
        self.prepare('candidate',source='b'*40,ok=False)
        self.assertFalse(self.state.exists())

    def test_wrong_repository_is_rejected(self):
        self.prepare('candidate',lambda d:d.update(repository='openai/codex'),ok=False)
        self.assertFalse(self.state.exists())

    def test_corrupt_archive_keeps_current(self):
        self.bootstrap(); old=os.readlink(self.state/'current')
        self.prepare('candidate',lambda d:d.update(archiveSha256='0'*64),ok=False)
        self.assertEqual(os.readlink(self.state/'current'),old)

    def test_mixed_acp_provenance_is_rejected(self):
        self.bootstrap(); old=os.readlink(self.state/'current')
        self.prepare('candidate',lambda d:d['providers']['acp'].update(codexPath='/nix/store/wrong/bin/codex'),ok=False)
        self.assertEqual(os.readlink(self.state/'current'),old)

    def test_changed_prepared_receipt_is_rejected(self):
        self.bootstrap(); old=os.readlink(self.state/'current')
        identifier,_=self.prepare('candidate')
        path=self.state/'prepared'/(identifier+'.json')
        value=json.loads(path.read_bytes()); value['ciRunId']=999
        path.write_text(json.dumps(value))
        self.invoke('activate',identifier,ok=False)
        self.assertEqual(os.readlink(self.state/'current'),old)

    def test_lock_contention_preserves_selection(self):
        self.bootstrap(); old=os.readlink(self.state/'current')
        identifier,_=self.prepare('candidate')
        with manager.locked(self.state): self.invoke('activate',identifier,ok=False)
        self.assertEqual(os.readlink(self.state/'current'),old)

    def test_pending_transaction_blocks_more_writes(self):
        self.bootstrap(); old=os.readlink(self.state/'current')
        identifier,_=self.prepare('candidate')
        (self.state/'transaction.json').write_text('{}')
        self.invoke('activate',identifier,ok=False)
        self.assertEqual(os.readlink(self.state/'current'),old)
        self.assertTrue(json.loads(self.invoke('status').stdout)['recoveryRequired'])


if __name__ == '__main__': unittest.main()
