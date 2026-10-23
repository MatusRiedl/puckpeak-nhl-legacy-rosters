"""Coachella Valley's and Henderson's crests on their jerseys and centre ice (art/crests.py). The files made from the disc
need it (LEGACY_ROSTER_DISC, read only); the rest runs without."""
import os
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from legacy_roster import layout as L
from legacy_roster.art import crests, install, rpsgl

DISC = os.environ.get('LEGACY_ROSTER_DISC')
needs_disc = pytest.mark.skipif(not DISC, reason="needs the game disc (LEGACY_ROSTER_DISC)")
NAVY, RED, ORANGE = L.OWN_KIT[234][11, 1][:3]


def _logo():
    """A round crest in the three colours, on a transparent square."""
    img = Image.new('RGBA', (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((10, 10, 290, 290), fill=NAVY + (255,))
    d.ellipse((60, 60, 240, 240), fill=RED + (255,))
    d.rectangle((120, 120, 180, 180), fill=ORANGE + (255,))
    return img


def test_logo_numbers():
    assert crests.logo_number(20073) == 72 and crests.logo_number(20081) == 80
    assert crests.logo_number(20001) == 0 and crests.logo_number(162) is None
    assert crests.crest_paths(20073)[0] == 'rendering/czlogo/logoct_72_0_tm.rpsgl'
    assert len(crests.crest_paths(20081)) == 13


def test_the_crest_colours_become_the_three_weights():
    colours = (NAVY, RED, ORANGE)
    assert [round(x, 6) for x in crests.mix(NAVY, colours)] == [1, 0, 0]
    assert [round(x, 6) for x in crests.mix(ORANGE, colours)] == [0, 0, 1]
    tinted = crests.weights(crests.fitted(_logo()), colours)
    assert tinted.size == (crests.SIZE, crests.SIZE)
    raw = tinted.tobytes()
    assert all(sum(raw[i:i + 3]) == 255 for i in range(0, len(raw), 4) if raw[i + 3])
    assert tinted.getpixel((256, 256)) == (0, 0, 255, 255)       # the middle: orange = zone 3
    assert tinted.getpixel((256, 60)) == (255, 0, 0, 255)        # the ring: navy = zone 1
    assert tinted.getpixel((0, 0))[3] == 0                       # outside the crest: nothing
    back = crests.shown(tinted, colours)
    assert back.getpixel((256, 256))[:3] == ORANGE
    assert crests.mix((22, 22, 22), ((0, 0, 0), (20, 20, 20), (40, 40, 40))) == [0.0, 1.0, 0.0]    # colours on a line


def test_a_crest_pictures_main_colours_are_three_different_ones():
    img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 496, 496), fill=(224, 0, 0, 255), outline=(255, 210, 0, 255), width=36)    # soft red edges
    d.rectangle((180, 150, 330, 360), fill=(255, 255, 255, 255))
    assert crests.main_colours(img) == [(224, 0, 0), (255, 210, 0), (255, 255, 255)]
    assert crests.main_colours(Image.new('RGBA', (8, 8), (10, 20, 30, 255))) == [(10, 20, 30)] * 3
    assert crests.main_colours(Image.new('RGBA', (8, 8))) == [(255, 255, 255)] * 3              # nothing visible


def test_the_digest_follows_logo_and_colours():
    a = crests.crest_digest(20073, _logo(), (NAVY, RED, ORANGE))
    assert a == crests.crest_digest(20073, _logo(), (NAVY, RED, ORANGE))
    assert a != crests.crest_digest(20073, _logo(), (RED, NAVY, ORANGE))
    assert a != crests.crest_digest(20081, _logo(), (NAVY, RED, ORANGE))


@needs_disc
def test_crest_files_from_the_disc():
    from legacy_roster.art.lab import Disc
    disc = Disc(DISC)
    files = crests.crest_files(disc, 20073, _logo(), (NAVY, RED, ORANGE))
    assert sorted(files) == sorted(crests.crest_paths(20073))
    for path, data in files.items():
        mine, own = rpsgl.Rpsgl(data), rpsgl.Rpsgl(disc.render(path))
        assert [(n, r['width'], r['height'], r['mips'], r['format'], r['size']) for n, r in mine.rasters.items()] == \
            [(n, r['width'], r['height'], r['mips'], r['format'], r['size']) for n, r in own.rasters.items()]
    tm = rpsgl.Rpsgl(files['rendering/czlogo/logoct_72_0_tm.rpsgl']).image('logoct_72_0_tm')
    assert tm.getpixel((256, 256))[2] > 200 and tm.getpixel((256, 256))[3] == 255
    assert tm.getpixel((2, 2))[3] == 0
    one = rpsgl.Rpsgl(files['rendering/czlogo/logoct_72_1_tm.rpsgl']).image('logoct_72_1_tm')
    assert one.getpixel((256, 256))[:3] == (0, 0, 0)                 # zones 4-6: none
    assert files == crests.crest_files(disc, 20073, _logo(), (NAVY, RED, ORANGE))     # the same bytes twice


# --- installed with the photos ------------------------------------------------------------------------------------------

@pytest.fixture
def game(tmp_path, monkeypatch):
    from legacy_roster import datasource, savedata
    monkeypatch.setattr(datasource, 'data_home', lambda: str(tmp_path / 'appdata'))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    monkeypatch.setattr(install, 'check', lambda rpcs3, title_id: None)
    folder = tmp_path / 'dev_hdd0' / 'game' / 'BLES02153' / 'USRDIR'
    folder.mkdir(parents=True)
    made = []

    def files(disc, art, logo, colours):
        made.append(art)
        return {p: f'{p} {colours[0]}'.encode() for p in crests.crest_paths(art)}
    monkeypatch.setattr(crests, 'crest_files', files)
    monkeypatch.setattr('legacy_roster.art.lab.Disc', lambda path: None)
    rpcs3 = SimpleNamespace(game_folder=lambda t: str(folder), game_disc=lambda t: 'disc')
    return rpcs3, folder, made


def test_install_once_then_undo(game):
    rpcs3, folder, made = game
    wanted = [(20073, _logo(), (NAVY, RED, ORANGE))]
    says = []
    assert crests.install_crests(rpcs3, 'BLES02153', wanted, says.append) == 13
    tm = folder.joinpath(*crests.crest_paths(20073)[0].split('/'))
    assert tm.read_bytes().endswith(str(NAVY).encode()) and says
    assert crests.install_crests(rpcs3, 'BLES02153', wanted, says.append) == 0 and made == [20073]
    other = [(20073, _logo(), (RED, NAVY, ORANGE))]                 # new colours: made again
    assert crests.install_crests(rpcs3, 'BLES02153', other, says.append) == 13
    assert tm.read_bytes().endswith(str(RED).encode())
    install.remove(say=lambda m: None)                               # "Restore the game's own pictures"
    assert not tm.exists()


def test_a_crest_no_longer_wanted_goes(game):
    rpcs3, folder, _made = game
    crests.install_crests(rpcs3, 'BLES02153', [(20081, _logo(), (NAVY, RED, ORANGE))], print)
    tm = folder.joinpath(*crests.crest_paths(20081)[0].split('/'))
    assert tm.exists()
    assert crests.install_crests(rpcs3, 'BLES02153', [], print) == 0
    assert not tm.exists()


def test_teams_with_their_own_art_id_only(base_bytes):
    from legacy_roster import roster
    R = roster.Roster(base_bytes)
    assert [(s, a) for s, a, _c in crests.crest_teams(R)] == [(234, 20073), (235, 20081)]   # the community roster's
    R.T.set(235, 'artid', 20054)
    assert [s for s, _a, _c in crests.crest_teams(R)] == [234]
    skipped = []
    assert crests.crests_from(R, {}, skipped=skipped) == [] and skipped == [(234, "no logo is known for it")]
