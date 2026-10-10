#!/usr/bin/env python3
"""Bound recovery points; never touch project caches or arbitrary GC roots."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess


def run(*args):
    return subprocess.check_output(args, text=True)


def generation_plan(profile, keep=4, protected=()):
    rows = sorted((int(m[1]), p) for p in profile.parent.glob(profile.name + '-*-link')
                  if (m := re.fullmatch(re.escape(profile.name) + r'-(\d+)-link', p.name)))
    retained = {n for n, _ in rows[-keep:]}
    targets = {str(Path(p).resolve()) for p in protected if Path(p).exists()}
    targets.add(str(profile.resolve()))
    retained.update(n for n, p in rows if str(p.resolve()) in targets)
    return {'profile': str(profile), 'keep': sorted(retained),
            'delete': [n for n, _ in rows if n not in retained]}


def snapshot_plan(rows, keep=3):
    rows = [r for r in rows if int(r['number']) > 0]
    retained = {int(r['number']) for r in sorted(rows, key=lambda r: int(r['number']))[-keep:]}
    # Updater-owned snapshots have their own transactional retention protocol.
    retained.update(int(r['number']) for r in rows
                    if (r.get('userdata') or {}).get('weasel-daily-update') == 'yes'
                    or (r.get('userdata') or {}).get('weasel-retain') == 'yes')
    return {'keep': sorted(retained), 'delete': [int(r['number']) for r in rows
                                               if int(r['number']) not in retained]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--gc', action='store_true', help='Collect at most 40 GiB of unreferenced Nix store data')
    args = p.parse_args()
    if os.geteuid() != 0:
        p.error('run through sudo')
    with open('/var/lib/weasel-updates/activation.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Never remove recovery checkpoints during an unresolved update.
        status = Path('/var/lib/weasel-updates-status/status.json')
        if status.exists():
            state = json.loads(status.read_text())
            if state.get('phase') != 'complete':
                raise RuntimeError('Unresolved daily-update status; retention deferred')
        for journal in Path('/var/lib/weasel-updates/manual-computer-use').glob('*/journal.json'):
            if json.loads(journal.read_text()).get('phase') != 'complete':
                raise RuntimeError('Unresolved manual activation; retention deferred')
        snapshots = json.loads(run('snapper', '--jsonout', '-c', 'home', 'list',
                                  '--columns', 'number,userdata'))['home']
        plan = {'snapshots': snapshot_plan(snapshots),
                'system': generation_plan(Path('/nix/var/nix/profiles/system'), protected=(
                    '/run/current-system', '/run/booted-system'))}
        print(json.dumps(plan), flush=True)
        if args.apply:
            for n in plan['snapshots']['delete']:
                subprocess.run(['snapper', '-c', 'home', 'delete', '--sync', str(n)], check=True)
            if plan['system']['delete']:
                subprocess.run(['nix-env', '-p', plan['system']['profile'], '--delete-generations',
                                *map(str, plan['system']['delete'])], check=True)
                subprocess.run(['/run/current-system/bin/switch-to-configuration', 'boot'], check=True)
            if args.gc:
                subprocess.run(['nix-store', '--gc', '--max-freed', str(40 * 1024**3)], check=True)


if __name__ == '__main__':
    main()
