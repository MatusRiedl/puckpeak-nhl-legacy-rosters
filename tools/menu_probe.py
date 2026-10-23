"""LAB probe: hide the dead online entries (menus.DEAD: View Player Hub, Leaderboards, Lobby) in the main menu.

These entries died with the game's servers. The probe writes one loose file into a LAB game folder and takes
it out again.

    python tools\\menu_probe.py install --game-dir <lab USRDIR> [--disc <iso>] [--mode hide|remove]
    python tools\\menu_probe.py remove  --game-dir <lab USRDIR>
    python tools\\menu_probe.py status  --game-dir <lab USRDIR>
    python tools\\menu_probe.py write   -o <folder outside RPCS3> [--disc <iso>] [--mode hide|remove]

<lab USRDIR> is the LAB RPCS3's dev_hdd0\\game\\BLES02153\\USRDIR (or BLUS31540). The file is
fe\\ion\\game\\menus\\mainmenuitems.big there (legacy_roster/art/menus.py makes it from the disc,
default --disc: LEGACY_ROSTER_DISC). --mode hide (default) marks the entries `isHidden: true`;
--mode remove leaves them out of the menu lists.

Safety: only a folder ...\\dev_hdd0\\game\\<TITLEID>\\USRDIR below a lab (a folder above it holds
launch_lab.ps1) is accepted, and nothing is written while an RPCS3 runs. A file already at that
place is kept first (never overwritten) in <lab>\\menu_probe\\<TITLEID>\\kept\\, and `remove` puts it
back. `remove` takes out only the file this probe wrote (same SHA-1); a file changed since stays.

What to look for in the game: RPCS3's log line sys_fs_open(path="/dev_hdd0/game/<TITLEID>/USRDIR/
fe/ion/game/menus/mainmenuitems.big" (the game read the loose file), then the main menu's
"Featured" tiles, PLAY and COMMUNITY (docs/notes/menus.md).
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from legacy_roster import savedata  # noqa: E402
from legacy_roster.art import menus  # noqa: E402

MARKER = 'launch_lab.ps1'
STORE = 'menu_probe'
MANIFEST = 'manifest.json'


def _sha1(data):
    return hashlib.sha1(data).hexdigest()


def lab_game_dir(path):
    """(USRDIR, title id, lab folder) of a LAB game folder, else SystemExit with the reason."""
    usrdir = os.path.abspath(path)
    parts = usrdir.replace('\\', '/').rstrip('/').split('/')
    if (len(parts) < 5 or parts[-1].upper() != 'USRDIR' or parts[-2].upper() not in savedata.GAMES
            or parts[-3].lower() != 'game' or parts[-4].lower() != 'dev_hdd0'):
        sys.exit(f"refused: {usrdir} is not ...\\dev_hdd0\\game\\<{'|'.join(savedata.GAMES)}>\\USRDIR")
    if not os.path.isdir(usrdir):
        sys.exit(f"refused: {usrdir} does not exist (start the game once in the lab RPCS3)")
    folder = os.path.dirname(usrdir)
    while True:
        if os.path.isfile(os.path.join(folder, MARKER)):
            return usrdir, parts[-2].upper(), folder
        up = os.path.dirname(folder)
        if up == folder:
            sys.exit(f"refused: no {MARKER} in any folder above {usrdir}; this probe writes only into a lab RPCS3")
        folder = up


def _store(lab, title_id):
    return os.path.join(lab, STORE, title_id)


def _load(store):
    try:
        with open(os.path.join(store, MANIFEST), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(store, manifest):
    os.makedirs(store, exist_ok=True)
    tmp = os.path.join(store, MANIFEST + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    os.replace(tmp, os.path.join(store, MANIFEST))


def _not_running():
    running = savedata.running_rpcs3()
    if running:
        sys.exit(f"refused: RPCS3 is running ({running}); close it first")


def _disc(args):
    disc = args.disc or os.environ.get('LEGACY_ROSTER_DISC')
    if not disc or not os.path.exists(disc):
        sys.exit("give the game disc: --disc <iso or folder> (or set LEGACY_ROSTER_DISC)")
    return disc


def install(args):
    usrdir, title_id, lab = lab_game_dir(args.game_dir)
    _not_running()
    files = menus.hidden_files(_disc(args), args.mode)
    store = _store(lab, title_id)
    manifest = _load(store)
    for rel, data in files.items():
        key = '/'.join(rel)
        target = os.path.join(usrdir, *rel)
        entry = manifest.get(key, {})
        if os.path.isfile(target):
            with open(target, 'rb') as f:
                there = f.read()
            if _sha1(there) != entry.get('written') and not entry.get('kept'):
                kept = os.path.join(store, 'kept', *rel)
                if os.path.exists(kept):
                    sys.exit(f"refused: a kept copy is already at {kept}; look at it before going on")
                os.makedirs(os.path.dirname(kept), exist_ok=True)
                shutil.copyfile(target, kept)
                entry['kept'] = os.path.relpath(kept, store).replace('\\', '/')
                print(f"kept the file that was there: {kept}")
            elif _sha1(there) != entry.get('written'):
                sys.exit(f"refused: {target} changed since this probe wrote it, and a kept copy exists; "
                         "run remove first or look at it")
        made = []
        folder = os.path.dirname(target)
        while not os.path.isdir(folder):
            made.append(os.path.relpath(folder, usrdir).replace('\\', '/'))
            folder = os.path.dirname(folder)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp = target + '.menuprobe.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, target)
        entry.update(written=_sha1(data), mode=args.mode, version=menus.MENUS_VERSION,
                     made_folders=sorted(set(entry.get('made_folders', []) + made), key=len, reverse=True))
        manifest[key] = entry
        print(f"written: {target} ({len(data):,} bytes, mode {args.mode}, sha1 {_sha1(data)[:12]})")
    _save(store, manifest)
    print(f"undo: python tools\\menu_probe.py remove --game-dir \"{usrdir}\"")
    return 0


def remove(args):
    usrdir, title_id, lab = lab_game_dir(args.game_dir)
    _not_running()
    store = _store(lab, title_id)
    manifest = _load(store)
    if not manifest:
        print("nothing to take out: this probe wrote nothing here")
        return 0
    left = {}
    for key, entry in manifest.items():
        target = os.path.join(usrdir, *key.split('/'))
        if os.path.isfile(target):
            with open(target, 'rb') as f:
                if _sha1(f.read()) != entry.get('written'):
                    print(f"left alone: {target} changed since this probe wrote it")
                    left[key] = entry
                    continue
            os.remove(target)
            print(f"taken out: {target}")
        kept = entry.get('kept')
        if kept:
            source = os.path.join(store, *kept.split('/'))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
            os.remove(source)
            print(f"put back the file that was there before: {target}")
        else:
            for folder in entry.get('made_folders', []):
                path = os.path.join(usrdir, *folder.split('/'))
                try:
                    os.rmdir(path)              # only empty folders this probe made
                except OSError:
                    pass
    _save(store, left)
    return 0


def status(args):
    usrdir, title_id, lab = lab_game_dir(args.game_dir)
    manifest = _load(_store(lab, title_id))
    target = os.path.join(usrdir, *menus.REL)
    entry = manifest.get('/'.join(menus.REL))
    if not os.path.isfile(target):
        print(f"no loose menu file: {target}")
    else:
        with open(target, 'rb') as f:
            data = f.read()
        mine = entry and _sha1(data) == entry.get('written')
        print(f"{target}: {len(data):,} bytes, " + (f"written by this probe (mode {entry.get('mode')})"
                                                    if mine else "NOT written by this probe"))
        try:
            hidden = [(a, k) for a, k, h in menus.menu_entries(data) if h]
            print("hidden entries: " + (', '.join(f"{k} ({a})" for a, k in hidden) or 'none'))
        except ValueError as exc:
            print(f"cannot read it: {exc}")
    if entry and entry.get('kept'):
        print(f"kept copy of the file that was there before: {entry['kept']}")
    return 0


def write(args):
    out = os.path.abspath(args.out)
    if 'dev_hdd0' in out.replace('\\', '/').lower().split('/'):
        sys.exit(f"refused: {out} is inside an RPCS3 folder; use install for a lab game folder")
    for rel, data in menus.hidden_files(_disc(args), args.mode).items():
        target = os.path.join(out, *rel)
        if os.path.exists(target):
            sys.exit(f"refused: {target} exists")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'wb') as f:
            f.write(data)
        print(f"written: {target} ({len(data):,} bytes, sha1 {_sha1(data)[:12]})")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='command', required=True)
    for name in ('install', 'remove', 'status'):
        p = sub.add_parser(name)
        p.add_argument('--game-dir', required=True, help="the LAB RPCS3's dev_hdd0\\game\\<TITLEID>\\USRDIR")
    p = sub.add_parser('write')
    p.add_argument('-o', '--out', required=True, help="a folder outside RPCS3")
    for name in ('install', 'write'):
        sub.choices[name].add_argument('--disc', help="the game disc (iso or folder; default LEGACY_ROSTER_DISC)")
        sub.choices[name].add_argument('--mode', choices=(menus.HIDE, menus.REMOVE), default=menus.HIDE)
    args = ap.parse_args(argv)
    return {'install': install, 'remove': remove, 'status': status, 'write': write}[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
