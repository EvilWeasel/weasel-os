#!/usr/bin/env python3
"""Versioned cloud backup and recovery, using restic and official Proton Drive."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
import stat

spec = importlib.util.spec_from_file_location('transport', Path(__file__).with_name('proton-restic-server.py'))
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


def fingerprint(source):
    paths = [source, *source.rglob('*')] if source.is_dir() else [source]
    rows = []
    for path in paths:
        s = path.lstat()
        rows.append((str(path.relative_to(source.parent)), s.st_dev, s.st_ino,
                     s.st_mode, s.st_size, s.st_mtime_ns,
                     os.readlink(path) if path.is_symlink() else ''))
    return sorted(rows)


def active_references(source):
    prefix = str(source) + '/'
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            links = [proc / 'cwd', proc / 'exe', *(proc / 'fd').iterdir()]
            for link in links:
                try:
                    target = os.readlink(link)
                    if target == str(source) or target.startswith(prefix):
                        return True
                except OSError:
                    pass
            for line in (proc / 'maps').read_text().splitlines():
                parts = line.split(maxsplit=5)
                if len(parts) == 6 and (parts[5] == str(source) or parts[5].startswith(prefix)):
                    return True
        except OSError:
            continue
    return False


def archive(args, drive, spool, state):
    if args.source.is_symlink():
        raise RuntimeError('Archive source must not be a symlink')
    source = args.source.resolve(strict=True)
    if source.is_symlink() or not source.exists() or source == Path.home() or Path.home().is_relative_to(source):
        raise RuntimeError('Select one existing regular file or directory below the home directory')
    if not source.is_relative_to(Path.home()) or source.is_relative_to(state):
        raise RuntimeError('Archive source must be a personal path outside the job state')
    if active_references(source):
        raise RuntimeError('Selected archive has active process references')
    before = fingerprint(source)
    if any(not (stat.S_ISREG(row[3]) or stat.S_ISDIR(row[3]) or stat.S_ISLNK(row[3])) for row in before):
        raise RuntimeError('Special files in archive source; local source retained')
    estimated = sum(row[4] for row in before if stat.S_ISREG(row[3]))
    disk = shutil.disk_usage(state)
    if disk.free - 2 * estimated < disk.total * .20:
        raise RuntimeError('Not enough staging space to remain below 80%; choose a smaller archive')
    parent = '/my-files/Weasel-Archive'
    roots = drive.rows(drive.command('list', '/my-files'))
    if 'Weasel-Archive' not in roots:
        drive.command('create-folder', '/my-files', 'Weasel-Archive')
    name = time.strftime('%Y%m%dT%H%M%S-') + secrets.token_hex(4) + '-' + source.name + '.tar.zst'
    pack = Path(spool) / name
    subprocess.run(['tar', '--zstd', '--xattrs', '--acls', '-cpf', str(pack),
                    '-C', str(source.parent), '--', source.name], check=True)
    if before != fingerprint(source):
        raise RuntimeError('Source changed while archiving; local source retained')
    def digest(path):
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    expected = digest(pack)
    drive.command('upload', '-f', 'skip', '-t', str(pack), parent)
    with tempfile.TemporaryDirectory(dir=spool) as downloaded:
        drive.command('download', '-f', 'skip', parent + '/' + name, downloaded)
        if digest(Path(downloaded) / name) != expected:
            raise RuntimeError('Archive cloud readback hash mismatch; local source retained')
    receipt = {'time': time.time(), 'source': str(source), 'remote': parent + '/' + name,
               'sha256': expected, 'bytes': pack.stat().st_size, 'verified': True, 'evicted': False}
    if args.evict:
        if before != fingerprint(source) or active_references(source):
            raise RuntimeError('Source changed or became active after verification; local source retained')
        quarantine_root = state / ('archive-quarantine-' + secrets.token_hex(8))
        quarantine_root.mkdir(mode=0o700)
        retained = quarantine_root / source.name
        source.rename(retained)
        if before != fingerprint(retained) or active_references(retained) or active_references(source):
            if not source.exists():
                retained.rename(source)
                quarantine_root.rmdir()
            raise RuntimeError('Archive changed during eviction; retained locally, see archive quarantine if source path was recreated')
        if retained.is_dir():
            shutil.rmtree(retained)
        else:
            retained.unlink()
        quarantine_root.rmdir()
        receipt['evicted'] = True
    (state / 'last-archive.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['probe', 'backup', 'snapshots', 'check', 'restore', 'maintain', 'archive'])
    p.add_argument('--cli', default='proton-drive')
    p.add_argument('--restic', default='restic')
    p.add_argument('--excludes', type=Path, required=True)
    p.add_argument('--root', default='/my-files/Weasel-Recovery/nixy-laptop-restic-v1')
    p.add_argument('--source', type=Path, default=Path.home())
    p.add_argument('--target', type=Path)
    p.add_argument('--snapshot', default='latest')
    p.add_argument('--tag', choices=['personal-state', 'system-state'], default='personal-state')
    p.add_argument('--probe-system', action='store_true')
    p.add_argument('--evict', action='store_true', help='For selected archives only: remove local source after full verified readback')
    args = p.parse_args()
    os.umask(0o077)
    state = Path.home() / '.local/state/weasel-backup'
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / 'job.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix='spool-', dir=state) as spool:
            drive = transport.Drive(args.cli, args.root, spool)
            if args.mode == 'archive':
                archive(args, drive, spool, state)
                return
            drive.folders()
            parent = args.root.rsplit('/', 1)[0]
            key_name = 'nixy-laptop-restic-password.txt'
            password = Path.home() / '.local/share/weasel-backup' / key_name
            password.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            remote_keys = drive.rows(drive.command('list', parent))
            if not password.exists():
                if key_name in remote_keys:
                    drive.command('download', '-f', 'skip', parent + '/' + key_name, str(password.parent))
                    password.chmod(0o600)
                elif 'config' in drive.listing(''):
                    raise RuntimeError('Repository exists but recovery password is missing; initialization refused')
                else:
                    with password.open('x') as stream:
                        stream.write(secrets.token_urlsafe(48) + '\n')
            if password.is_symlink() or password.stat().st_uid != os.getuid() or password.stat().st_mode & 0o077:
                raise RuntimeError('Unsafe backup password file permissions')
            if key_name not in remote_keys:
                drive.command('upload', '-f', 'skip', '-t', str(password), parent)
            # Keep recovery possible after total laptop loss. Verify the private
            # recovery material without exposing it in output or process args.
            with tempfile.TemporaryDirectory(dir=spool) as tmp:
                drive.command('download', '-f', 'skip', parent + '/' + key_name, tmp)
                if (Path(tmp) / key_name).read_bytes() != password.read_bytes():
                    raise RuntimeError('Cloud recovery password does not match local private store')
            token = secrets.token_urlsafe(32)
            server = transport.serve(drive, token, allow_delete=args.mode == 'maintain')
            env = dict(os.environ, RESTIC_REPOSITORY=f'rest:http://weasel:{token}@127.0.0.1:{server.server_port}/',
                       RESTIC_PASSWORD_FILE=str(password), RESTIC_CACHE_DIR=str(state / 'restic-cache'))

            def restic(*command):
                result = subprocess.run([args.restic, '-o', 'rest.connections=1', *command],
                                        env=env, capture_output=True, text=True)
                # Logs are private; command line/environment never logged here.
                (state / 'last-restic.log').write_text(result.stdout + result.stderr)
                if result.returncode:
                    raise RuntimeError('restic failed (exit ' + str(result.returncode) + '); see private last-restic.log')
                return result.stdout

            # Restic matches absolute source paths. Expand the declared
            # home-relative rules against the actual backup source.
            excludes = Path(spool) / 'excludes.txt'
            excludes.write_text('\n'.join(str(args.source) + line if line.startswith('/') else line
                                          for line in args.excludes.read_text().splitlines()) + '\n')

            try:
                if 'config' not in drive.listing(''):
                    restic('init', '--repository-version', '2')
                if args.mode == 'probe':
                    with tempfile.TemporaryDirectory(prefix='restore-proof-', dir=state) as tmp:
                        source = Path(tmp) / 'source'
                        source.mkdir()
                        payload = secrets.token_bytes(1024 * 1024)
                        (source / 'proof.bin').write_bytes(payload)
                        (source / 'link').symlink_to('proof.bin')
                        restic('backup', '--tag', 'restore-proof', '--host', 'nixy-laptop', str(source))
                        restic('check', '--read-data')
                        destination = Path(tmp) / 'restored'
                        restic('restore', 'latest', '--tag', 'restore-proof', '--target', str(destination))
                        restored = destination / str(source).lstrip('/')
                        if (restored / 'proof.bin').read_bytes() != payload or os.readlink(restored / 'link') != 'proof.bin':
                            raise RuntimeError('Cloud restore proof failed')
                    (state / 'restore-proof.json').write_text(json.dumps({'time': time.time(), 'ok': True}))
                    print('Cloud backup restore proof passed: full remote read, byte equality and symlink preservation')
                    if args.probe_system:
                        result = subprocess.run(['sudo', '-n', '/run/current-system/sw/bin/weasel-system-state-export', 'probe'],
                                                input=json.dumps({'repository': env['RESTIC_REPOSITORY']}), capture_output=True, text=True)
                        (state / 'last-system-restic.log').write_text(result.stdout + result.stderr)
                        if result.returncode:
                            raise RuntimeError('Private root-state restore proof failed; see private last-system-restic.log')
                        print('Private root-state restore proof passed, including owner root and mode 0600')
                elif args.mode == 'backup':
                    restic('backup', '--host', 'nixy-laptop', '--tag', 'personal-state',
                           '--exclude-file', str(excludes), '--pack-size', '32', str(args.source))
                    if args.source == Path.home():
                        # The token travels through stdin, not process arguments,
                        # a public environment file or the root journal.
                        result = subprocess.run(['sudo', '-n', '/run/current-system/sw/bin/weasel-system-state-export', 'backup'],
                                                input=json.dumps({'repository': env['RESTIC_REPOSITORY']}),
                                                capture_output=True, text=True)
                        (state / 'last-system-restic.log').write_text(result.stdout + result.stderr)
                        if result.returncode:
                            raise RuntimeError('Mutable system-state backup failed; see private last-system-restic.log')
                    restic('check')
                    (state / 'last-success.json').write_text(json.dumps({'time': time.time(), 'ok': True,
                                                                       'source': str(args.source)}))
                    print('Cloud backup completed; repository structural check passed')
                elif args.mode == 'check':
                    restic('check', '--read-data-subset', '5%')
                    print('Repository check with remote data sample passed')
                elif args.mode == 'maintain':
                    if not (state / 'last-success.json').exists() or not (state / 'restore-proof.json').exists():
                        raise RuntimeError('Retention needs a successful backup and restore proof first')
                    restic('check', '--read-data-subset', '5%')
                    restic('forget', '--tag', 'personal-state', '--tag', 'system-state', '--group-by', 'host,paths',
                           '--keep-daily', '7', '--keep-weekly', '4', '--keep-monthly', '3', '--prune')
                    print('Cloud retention completed')
                elif args.mode == 'snapshots':
                    print(restic('snapshots', '--tag', args.tag))
                elif args.mode == 'restore':
                    if not args.target or args.target.exists():
                        raise RuntimeError('Restore requires a new, absent --target directory')
                    print(restic('restore', args.snapshot, '--tag', args.tag, '--target', str(args.target)))
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Do not print arbitrary subprocess exceptions containing auth URLs.
        print('Cloud backup stopped: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__))
        raise SystemExit(1)
