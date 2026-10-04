"""Experiments the project owner runs once in the game before photos and logos become a feature.

    NHLLegacyRosterUpdater-cli art-test install --rpcs3 <rpcs3.exe> [--source <roster>]
    NHLLegacyRosterUpdater-cli art-test remove  --rpcs3 <rpcs3.exe>

`install` writes coloured, numbered test pictures as loose files into the game's own folder on
RPCS3's hard disk (dev_hdd0/game/<TITLEID>/USRDIR/fe/ion/artassets/...), backing up any file it
replaces, and saves a new roster "LAB art test" that points two players at new portrait ids and
gives the NHL slots of Utah, Seattle and Vegas their names. `remove` puts every file back as it
was. Every picture is made from an art file of the player's own game disc (only the image is
swapped); nothing from EA is shipped with the program.

What to look for in the game, and what each test answers:
  1 red    Connor McDavid's portrait replaced           do loose portrait files override the disc?
  2 green  a player without a portrait, id the disc lacks   does a new file for an unused id show?
  3 yellow a second such player, id above the disc's range  which folder do ids above 12,000 use?
  4 blue   logo of Extraliga slot 107 (Kladno)          do loose logo files override the disc?
  names    NHL slots 22/30/31 named Utah/Seattle/Vegas   does the game show the save's names there?
"""
import json
import os
import shutil

from .. import datasource, savedata
from ..roster import Roster
from ..verify import verify
from . import bigf, dds
from .disc import EbArchive, IsoImage

ART = ('fe', 'ion', 'artassets')
COLOURS = {1: (214, 40, 40), 2: (40, 170, 70), 3: (230, 200, 30), 4: (40, 90, 220)}
DIGITS = {      # 5 x 7 block digits
    1: ('..#..', '.##..', '..#..', '..#..', '..#..', '..#..', '.###.'),
    2: ('.###.', '#...#', '....#', '...#.', '..#..', '.#...', '#####'),
    3: ('####.', '....#', '....#', '.###.', '....#', '....#', '####.'),
    4: ('...#.', '..##.', '.#.#.', '#..#.', '#####', '...#.', '...#.'),
}
EXISTING_PLAYER = 'Connor McDavid'
NEW_PLAYERS = ('Macklin Celebrini', 'Ivan Demidov')     # young stars the base roster has without a portrait
LOGO_SLOT = 107
LAB_NAME = "LAB art test"
NHL_NAMES = {22: ("Utah Mammoth", "Utah", "UTA"), 30: ("Seattle Kraken", "Seattle", "SEA"),
             31: ("Vegas Golden Knights", "Vegas", "VGK")}


def portrait_folder(artid):
    return 'p0_4000' if artid <= 4000 else 'p4001_8000' if artid <= 8000 else 'p8001_12000'


def paint(width, height, colour, digit, area=None):
    """A test picture: a coloured panel with a big white digit, transparent around it.
    `area` (x0, y0, x1, y1) is where the panel goes (default: the whole picture)."""
    x0, y0, x1, y1 = area or (0, 0, width, height)
    pixels = [[(0, 0, 0, 0)] * width for _ in range(height)]
    glyph = DIGITS[digit]
    cell = max(1, min((x1 - x0) // 8, (y1 - y0) // 10))
    gx = x0 + ((x1 - x0) - 5 * cell) // 2
    gy = y0 + ((y1 - y0) - 7 * cell) // 2
    for y in range(y0, y1):
        row = pixels[y]
        for x in range(x0, x1):
            gr, gc = (y - gy) // cell, (x - gx) // cell
            ink = 0 <= gr < 7 and 0 <= gc < 5 and glyph[gr][gc] == '#' and y >= gy and x >= gx
            row[x] = (255, 255, 255, 255) if ink else colour + (255,)
    return pixels


def test_art(template, digit):
    """An art file like `template` (bytes of one from the disc) showing test picture `digit`."""
    a = bigf.ArtFile(template)
    img = a.image()
    h = dds.Header(img)
    # portraits keep their photo in the top half (512 x 512 canvas or 512 x 256), centred
    if h.width == 2 * h.height or h.width == h.height and h.fourcc == 'DXT5':
        area = (h.width // 4, h.height // 32, 3 * h.width // 4, h.height // 2 if h.width == h.height else h.height)
    else:
        area = (h.width // 8, h.height // 8, 7 * h.width // 8, 7 * h.height // 8)
    return a.with_image(dds.build(img, paint(h.width, h.height, COLOURS[digit], digit, area)))


class Disc:
    """The art files of the player's own game disc (image or folder)."""

    def __init__(self, path):
        src = IsoImage(path) if os.path.isfile(path) else path
        self.archives = {name: EbArchive.open(src, name) for name in ('nocache.big', 'cache.big')}

    def find(self, inner):
        for arc in self.archives.values():
            if inner in arc.entries:
                return arc.read(inner)
        return None

    def portrait(self, kind, artid):
        """The disc's own art file for a portrait (kind 'playerheads' or 'playerheadssmall'), else a
        file of the same kind to use as the template."""
        own = self.find('/'.join(ART + (kind, portrait_folder(artid), f"p{artid}.big")))
        return own or self.find('/'.join(ART + (kind, 'p0_4000', 'p100.big')))

    def logo(self, folder, prefix, artid):
        return self.find('/'.join(ART + (folder, f"{prefix}{artid}.big")))


LOGO_KINDS = (('teamlogos', 't'), ('teamlogossmall', 's'), ('teamlogoswide', 'w'), ('teamlogoscalendar', 'c'),
              ('teamlogosdynasty', 'd'))


def backup_dir():
    return datasource.app_dir('art_backup')


def manifest_path():
    return os.path.join(backup_dir(), 'manifest.json')


def _write(game_dir, rel, data, manifest):
    path = os.path.join(game_dir, *rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entry = {'path': path, 'backup': None}
    if os.path.exists(path) and not any(m['path'] == path for m in manifest):
        entry['backup'] = os.path.join(backup_dir(), f"{len(manifest):04d}_{os.path.basename(path)}")
        shutil.copy2(path, entry['backup'])
    if not any(m['path'] == path for m in manifest):
        manifest.append(entry)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def install(rpcs3, source=None, say=print):
    """Write the test pictures and the LAB roster. Returns the new roster save (savedata.Slot)."""
    if savedata.running_rpcs3():
        raise RuntimeError("Close RPCS3 first: the game must not be running while its files change.")
    if os.path.exists(manifest_path()):
        raise RuntimeError("The art test is already installed. Run 'art-test remove' first.")
    slots = savedata.list_rosters(rpcs3.savedata)
    slot = next((s for s in slots if source in (s.folder, s.name)), None) if source else slots[0]
    if slot is None:
        raise FileNotFoundError(f"roster save {source} not found")
    disc_path = rpcs3.game_disc(slot.title_id)
    if not disc_path:
        raise FileNotFoundError(f"RPCS3 does not list where the game {slot.title_id} is (config/games.yml)")
    say(f"Reading art templates from your game: {disc_path}")
    disc = Disc(disc_path)
    with open(slot.sys_data, 'rb') as f:
        src = f.read()
    R = Roster(src)
    P, T = R.P, R.T
    used = {P.get(i, 'artid') for i in range(P.cur_rec)}
    on_disc = {int(n.rsplit('/p', 1)[1][:-4]) for n in disc.archives['nocache.big'].entries
               if '/playerheads/p' in n and '/silhouettes/' not in n}
    row = lambda name: next((i for i in range(P.cur_rec) if R.name(i) == name and R.teams_of(i)), None)

    game_dir = rpcs3.game_folder(slot.title_id)
    manifest = []
    plan = []          # (digit, relative path, template)
    star = row(EXISTING_PLAYER)
    if star is not None and P.get(star, 'artid'):
        aid = P.get(star, 'artid')
        for kind in ('playerheads', 'playerheadssmall'):
            plan.append((1, ART + (kind, portrait_folder(aid), f"p{aid}.big"), disc.portrait(kind, aid)))
    inside = next(k for k in range(3999, 0, -1) if k not in on_disc and k not in used)
    above = next(k for k in range(max(on_disc) + 1, 16000) if k not in used)     # just past the disc's ids
    new_ids = {}
    for digit, name, aid in ((2, NEW_PLAYERS[0], inside), (3, NEW_PLAYERS[1], above)):
        r = row(name)
        if r is None:
            say(f"{name} is not in this roster; test {digit} is skipped")
            continue
        new_ids[r] = aid
        for kind in ('playerheads', 'playerheadssmall'):
            folders = {portrait_folder(aid)} | ({'p12001_16000'} if aid > 12000 else set())
            for folder in sorted(folders):
                plan.append((digit, ART + (kind, folder, f"p{aid}.big"), disc.portrait(kind, 100)))
    team_art = T.get(LOGO_SLOT, 'artid')
    for folder, prefix in LOGO_KINDS:
        template = disc.logo(folder, prefix, team_art)
        if template:
            plan.append((4, ART + (folder, f"{prefix}{team_art}.big"), template))

    # the LAB roster: two players point at the new portrait ids, the NHL slots get their real names
    for r, aid in new_ids.items():
        P.set(r, 'artid', aid)
        P.set(r, 'hasportrait', 1)
    for t, (full, short, abbr) in NHL_NAMES.items():
        T.set(t, 'fullname', full)
        T.set(t, 'shortname', short)
        T.set(t, 'abbrname', abbr)
    built = R.f.build()
    problems, _ = verify(built, Roster(src))
    if problems:
        raise RuntimeError("the LAB roster did not pass the checks: " + "; ".join(problems[:3]))

    os.makedirs(backup_dir(), exist_ok=True)
    try:
        for digit, rel, template in plan:
            _write(game_dir, rel, test_art(template, digit), manifest)
            say(f"Test {digit}: {'/'.join(rel)}")
    finally:
        with open(manifest_path(), 'w', encoding='utf-8') as f:
            json.dump({'game_dir': game_dir, 'files': manifest}, f, indent=1)
    lab = savedata.install(rpcs3.savedata, slot, built, LAB_NAME)
    say(f"Saved the roster \"{lab.name}\" ({lab.folder}). Players with new portraits: "
        + ", ".join(f"{R.name(r)} (id {aid})" for r, aid in new_ids.items()))
    return lab


def remove(say=print):
    """Put every file the test replaced back, delete the ones it added. Returns how many."""
    if not os.path.exists(manifest_path()):
        say("The art test is not installed; nothing to remove.")
        return 0
    if savedata.running_rpcs3():
        raise RuntimeError("Close RPCS3 first: the game must not be running while its files change.")
    with open(manifest_path(), encoding='utf-8') as f:
        manifest = json.load(f)
    n = 0
    for entry in reversed(manifest['files']):
        if entry['backup']:
            shutil.copy2(entry['backup'], entry['path'])
            os.remove(entry['backup'])
        elif os.path.exists(entry['path']):
            os.remove(entry['path'])
        n += 1
    for entry in manifest['files']:          # folders the test created and left empty
        folder = os.path.dirname(entry['path'])
        while folder.startswith(manifest['game_dir']) and folder != manifest['game_dir']:
            try:
                os.rmdir(folder)
            except OSError:
                break
            folder = os.path.dirname(folder)
    os.remove(manifest_path())
    say(f"Removed the art test: {n} files put back as they were. The roster \"{LAB_NAME}\" stays in the "
        "game's list; delete it there if you like.")
    return n
