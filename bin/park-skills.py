#!/usr/bin/env python3
"""Park skills that are not in the keep set.

MiniMax Code always scans <dataDir>/skills, so those directories cannot be
turned off with config. They can only be moved out of the way. The pattern is
the one claude-command-center already uses: an installed directory lives in
skills/, a parked one lives in skills-off/, and toggling is a move between them.

The config gate handles the three external roots (<claude>/skills, <codex>/skills,
<agents>/skills). This script handles the root that config cannot reach.

Usage:
    python park-skills.py status          # what is installed, what is parked
    python park-skills.py park            # move every non-keep skill to skills-off/
    python park-skills.py restore <name>  # move one skill back
    python park-skills.py restore-all     # move everything back
"""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

# The keep set: the token-saving skills, the router, the forge family, and the
# skill-evolution channel the native runtime needs.
KEEP = {
    # token control
    'aswath-token-guard', 'aswath-token-evaluator', 'aswath-token-ledger',
    'aswath-compact', 'save-token', 'token-optimizer', 'context-engineering',
    'context-window-design', 'principle-guard-the-context-window',
    'context-tax-audit',
    # the router
    'aswath-capability',
    # forge family
    'aswath-forge', 'aswath-first-principles', 'aswath-resume',
    'aswath-csvjson', 'aswath-manual-demo',
    # the native skill-evolution channel
    'skill-evolution',
    # the terse-voice channel the user asks for by name
    'caveman',
}


def data_dir(home=None):
    base = Path(home) if home else Path.home()
    return base / '.minimax'


def skills_dir(home=None):
    return data_dir(home) / 'skills'


def parked_dir(home=None):
    return data_dir(home) / 'skills-off'


def manifest_path(home=None):
    return data_dir(home) / 'skills-off-manifest.json'


def load_manifest(home=None):
    p = manifest_path(home)
    if not p.is_file():
        return {'parked_at': None, 'skills': []}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'parked_at': None, 'skills': []}


def save_manifest(data, home=None):
    p = manifest_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1), encoding='utf-8')


def cmd_status(home):
    on = skills_dir(home)
    off = parked_dir(home)
    installed = sorted([d.name for d in on.iterdir() if d.is_dir()]) if on.is_dir() else []
    parked = sorted([d.name for d in off.iterdir() if d.is_dir()]) if off.is_dir() else []
    keep_here = [s for s in installed if s in KEEP]
    print('data dir   : %s' % data_dir(home))
    print('installed  : %d directories' % len(installed))
    print('  keep set : %d -> %s' % (len(keep_here), ', '.join(keep_here)))
    print('  to park  : %d' % len([s for s in installed if s not in KEEP]))
    print('parked     : %d directories in %s' % (len(parked), off))
    man = load_manifest(home)
    if man.get('parked_at'):
        print('last park  : %s' % man['parked_at'])
    return 0


def cmd_park(home, dry_run):
    on = skills_dir(home)
    off = parked_dir(home)
    if not on.is_dir():
        raise SystemExit('no skills directory at %s' % on)
    movable = [d for d in sorted(on.iterdir())
               if d.is_dir() and d.name not in KEEP]
    if dry_run:
        print('would park %d directories' % len(movable))
        for d in movable:
            print('  %s' % d.name)
        return 0
    off.mkdir(parents=True, exist_ok=True)
    moved = []
    for d in movable:
        target = off / d.name
        if target.exists():
            print('SKIP (already parked): %s' % d.name)
            continue
        shutil.move(str(d), str(target))
        moved.append(d.name)
    man = load_manifest(home)
    man['parked_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    man.setdefault('skills', [])
    for name in moved:
        if name not in man['skills']:
            man['skills'].append(name)
    save_manifest(man, home)
    print('parked %d directories into %s' % (len(moved), off))
    print('kept %d in %s' % (len([d for d in on.iterdir() if d.is_dir()]), on))
    return 0


def cmd_restore(home, name, dry_run):
    on = skills_dir(home)
    off = parked_dir(home)
    src = off / name
    if not src.is_dir():
        raise SystemExit('%s is not parked' % name)
    if dry_run:
        print('would restore %s' % name)
        return 0
    on.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(on / name))
    man = load_manifest(home)
    man['skills'] = [s for s in man.get('skills', []) if s != name]
    save_manifest(man, home)
    print('restored %s' % name)
    return 0


def cmd_restore_all(home, dry_run):
    on = skills_dir(home)
    off = parked_dir(home)
    if not off.is_dir():
        print('nothing parked')
        return 0
    names = [d.name for d in sorted(off.iterdir()) if d.is_dir()]
    if dry_run:
        print('would restore %d directories' % len(names))
        return 0
    on.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.move(str(off / name), str(on / name))
    man = load_manifest(home)
    man['parked_at'] = None
    man['skills'] = []
    save_manifest(man, home)
    print('restored %d directories' % len(names))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--home', default=None)
    ap.add_argument('--dry-run', action='store_true')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status')
    sub.add_parser('park')
    p = sub.add_parser('restore'); p.add_argument('name')
    sub.add_parser('restore-all')
    args = ap.parse_args()
    fn = {'status': cmd_status, 'park': cmd_park,
          'restore': cmd_restore, 'restore-all': cmd_restore_all}[args.cmd]
    if args.cmd in ('status', 'park', 'restore-all'):
        return fn(args.home, args.dry_run) if args.cmd != 'status' else fn(args.home)
    return fn(args.home, args.name, args.dry_run)


if __name__ == '__main__':
    sys.exit(main() or 0)
