"""Loose files go into the game's folder (dev_hdd0/game/<TITLEID>/USRDIR/...) and the game reads them before its .big archives.
On Linux the file system tells upper from lower case, so every loose path must be spelled exactly like the game's own path,
folder by folder. The disc (and the update's patch.big) spell every folder and file of every archive in lower case; only the
files that sit loose in USRDIR (EBOOT.BIN, ICON0.PNG) and RPCS3's own files (PARAM.SFO, SYS-DATA) are upper case. Notes:
docs/notes/linux-paths.md.

Part (a) needs nothing: the naming functions against a table of spellings taken from the disc. Part (b) needs
LEGACY_ROSTER_DISC (the game's disc image, read only) and checks the real listing case-sensitively."""
import os
import re

import pytest

from legacy_roster import gamepatch
from legacy_roster.art import clubart, crests, install, lab, loc, looks, masks, menus, onlinestart, pressstart

DISC = os.environ.get('LEGACY_ROSTER_DISC')

# the loose files an update writes, for sample art ids / slots: (what, path as the program names it, exact spelling on the disc)
EXPECTED = [
    ('jersey', looks.JERSEY.format(s=1, a=22, v=3), 'rendering/jersey/texlib_1_22_3.rpsgl'),
    ('pants', looks.PANT.format(s=1, a=22, v=3), 'rendering/pant/texlib_1_22_3.rpsgl'),
    ('socks', looks.SOCK.format(s=1, a=22, v=3), 'rendering/sock/sock_1_22_3_cm.rpsgl'),
    ('centre ice', looks.CENTRE.format(a=22), 'rendering/icesurface/centerlogo_22_cm.rpsgl'),
    ('rink picture', looks.ICE_PICTURE.format(a=22), 'rendering/icesurface/icesurface_22_bm.rpsgl'),
    ('helmet logo', looks.DECAL.format(a=22, s=1, v=3), 'rendering/logo/texlib_22_1_3.rpsgl'),
    ('menu jersey', looks.PREVIEW.format(s=1, a=22, v=3), 'fe/ion/artassets/jerseys/jersey_1_22_3.big'),
    ('goalie mask', masks.MASK.format(n=5), 'rendering/goaliehelmet/goaliehelmet_0_5_cm.rpsgl'),
    ('club name sheet', clubart.NAME.format(a=900, v=0), 'rendering/jersey/name_1_900_0_cm.rpsgl'),
    ('club banner', clubart.EXTRA[0].format(a=900), 'rendering/banner/banner_900_cm.rpsgl'),
    ('club goalie helmet', clubart.EXTRA[1].format(a=900), 'rendering/goaliehelmet/goaliehelmet_0_900_cm.rpsgl'),
    ('club puck', clubart.EXTRA[2].format(a=900), 'rendering/puck/puck_900_cm.rpsgl'),
    ('crest', crests.crest_paths(20073)[0], 'rendering/czlogo/logoct_72_0_tm.rpsgl'),
    ('main menu', '/'.join(menus.REL), 'fe/ion/game/menus/mainmenuitems.big'),
    ('press start', '/'.join(pressstart.REL), 'fe/ion/game/screens/bootflow/03_pressstart.big'),
    ('welcome back', '/'.join(onlinestart.WELCOME_REL), 'fe/ion/online/screens/login/welcomebackscreen.big'),
    ('matchmaking', '/'.join(onlinestart.MATCH_REL), 'fe/ion/online/screens/matchmaking/matchmakingscreen.big'),
    ('database description', '/'.join(gamepatch.META_FILE), 'db/nhlng-meta.xml'),
    ('database', '/'.join(gamepatch.DB_FILE), 'db/nhlng.db'),
    ('texts', '/'.join(('fe', 'loc', f"nhl_{loc.LANGUAGES[0]}.db")), 'fe/loc/nhl_eng_us.db'),
]
ARCHIVES = {'menu': menus.ARCHIVE, 'press start': pressstart.ARCHIVE, 'online screens': onlinestart.CACHE}


def _portrait(kind, aid):
    return '/'.join(lab.ART + (kind, lab.portrait_folder(aid), f"p{aid}.big"))


def _logo(kind, prefix, aid):
    return '/'.join(lab.ART + (kind, f"{prefix}{aid}.big"))


EXPECTED += [
    ('portrait low', _portrait('playerheads', 100), 'fe/ion/artassets/playerheads/p0_4000/p100.big'),
    ('portrait mid', _portrait('playerheadssmall', 4001), 'fe/ion/artassets/playerheadssmall/p4001_8000/p4001.big'),
    ('portrait high', _portrait('playerheads', 12000), 'fe/ion/artassets/playerheads/p8001_12000/p12000.big'),
    ('portrait over', _portrait('playerheads', 40000), 'fe/ion/artassets/playerheads/p8001_12000/p40000.big'),
]
EXPECTED += [(f'logo {folder}', _logo(folder, prefix, 22), f'fe/ion/artassets/{folder}/{prefix}22.big')
             for folder, prefix in install.logo_kinds(22)]


@pytest.mark.parametrize('what, path, spelled', EXPECTED, ids=[e[0] for e in EXPECTED])
def test_loose_paths_are_spelled_as_the_games_own(what, path, spelled):
    assert path == spelled


def test_every_loose_path_is_lower_case_except_the_known_files():
    """The disc spells every folder and file of its archives in lower case, so a name with a capital is a mistake."""
    for what, path, _spelled in EXPECTED:
        assert path == path.lower(), (what, path)
    assert install.UPDATE_ARCHIVE == 'patch.big'                # the update's archive, read from the game folder
    for lang in loc.LANGUAGES:
        assert f"nhl_{lang}.db" == f"nhl_{lang}.db".lower()
    assert install.ART == ('fe', 'ion', 'artassets')            # the pictures' folders


def test_the_archives_the_program_reads_are_spelled_as_on_the_disc():
    assert ARCHIVES == {'menu': 'boot.big', 'press start': 'cacheboot.big', 'online screens': 'cache.big'}


# --- part (b): the disc's real listing ------------------------------------------------------------
@pytest.fixture(scope='module')
def disc_entries():
    if not DISC:
        pytest.skip("needs LEGACY_ROSTER_DISC")
    from legacy_roster.art.disc import EbArchive, IsoImage
    iso = IsoImage(DISC)
    found = {}
    for path in iso.files:
        if path.startswith('/PS3_GAME/USRDIR/') and path.endswith('.big') and path.count('/') == 3:
            name = path.rsplit('/', 1)[1]
            try:
                found[name] = set(EbArchive.open(iso, name).entries)
            except (ValueError, NotImplementedError):
                continue
    return found


def _pattern(template):
    return re.compile('^' + re.sub(r'\\\{\w*\\\}', r'[0-9a-z_]+', re.escape(template)) + '$')


def test_every_entry_of_every_disc_archive_is_lower_case(disc_entries):
    assert disc_entries, "no archive was read"
    bad = sorted(e for entries in disc_entries.values() for e in entries if e != e.lower())
    assert bad == [], bad[:10]


def test_no_two_disc_entries_differ_only_by_case(disc_entries):
    seen = {}
    for entries in disc_entries.values():
        for e in entries:
            seen.setdefault(e.lower(), set()).add(e)
    assert [v for v in seen.values() if len(v) > 1] == []


def test_every_loose_path_of_the_samples_matches_the_disc_case_sensitively(disc_entries):
    """Files the game has itself must be found by their exact spelling; files for new numbers (art 900, portraits over the
    disc's range, crests the disc lacks) must be spelled like their neighbours, so their folder exists on the disc."""
    every = set().union(*disc_entries.values())
    folders = {e.rsplit('/', 1)[0] for e in every if '/' in e}
    # sample paths made from numbers the disc has files for
    own = [path for what, path, _s in EXPECTED if what in ('jersey', 'pants', 'socks', 'centre ice', 'rink picture',
                                                           'helmet logo', 'menu jersey', 'goalie mask', 'main menu',
                                                           'press start', 'welcome back', 'matchmaking',
                                                           'database description', 'database', 'texts')
           or what.startswith('logo ') or what in ('portrait low', 'portrait mid', 'portrait high')]
    missing = [p for p in own if p not in every]
    assert missing == [], missing
    # paths for numbers the disc lacks: the folder must exist exactly like this
    for what, path, _spelled in EXPECTED:
        assert path.rsplit('/', 1)[0] in folders, (what, path)


def test_every_template_matches_disc_files_exactly(disc_entries):
    every = set().union(*disc_entries.values())
    templates = [looks.JERSEY, looks.PANT, looks.SOCK, looks.CENTRE, looks.ICE_PICTURE, looks.DECAL, looks.PREVIEW,
                 masks.MASK, crests.TPL, clubart.NAME, *clubart.EXTRA]
    for t in templates:
        rx = _pattern(t)
        assert any(rx.match(e) for e in every), t
        assert not any(rx.match(e) is None and re.match(rx.pattern, e, re.I) for e in every), t


def test_the_languages_are_the_discs_text_files(disc_entries):
    for lang in loc.LANGUAGES:
        assert f"fe/loc/nhl_{lang}.db" in disc_entries['cacheboot.big'], lang
