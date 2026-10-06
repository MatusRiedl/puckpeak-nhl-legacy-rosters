"""The game's 3D textures (art/rpsgl.py) and the in-game test of loose ones (art/rendering.py).

The files themselves are EA's and need the game's disc: set LEGACY_ROSTER_DISC to a disc image (read only);
without it those tests skip."""
import os

import pytest

from legacy_roster import savedata
from legacy_roster.art import install, rendering, rpsgl

DISC = os.environ.get('LEGACY_ROSTER_DISC')


def test_a_chunkzip_packs_and_unpacks():
    data = bytes(range(256)) * 2000 + os.urandom(150000)        # more than one 128 KB chunk
    packed = rpsgl.pack(data)
    assert packed[:8] == b'chunkzip' and rpsgl.unpack(packed) == data
    assert rpsgl.unpack(b'plain') == b'plain'                    # not a chunkzip: as it is


@pytest.fixture(scope='module')
def disc():
    if not DISC or not os.path.exists(DISC):
        pytest.skip("no game disc (set LEGACY_ROSTER_DISC to your NHL Legacy disc image)")
    from legacy_roster.art.lab import Disc
    return Disc(DISC)


def test_the_disc_files_pack_back_to_the_same_bytes_and_a_raster_can_be_replaced(disc):
    pytest.importorskip('PIL')
    raw = disc.render(rendering.JERSEY.format(style=1, team=22, variant=3))
    f = rpsgl.Rpsgl(raw)
    assert f.build() == raw
    r = f.rasters['jersey_1_22_3_cm']
    assert (r['width'], r['height'], r['mips'], r['format']) == (1024, 1024, 11, 'DXT1')
    same = f.image('jersey_1_22_3_cm')
    f.replace('jersey_1_22_3_cm', same)
    assert len(f.build()) <= len(raw) * 1.1 and rpsgl.Rpsgl(f.build()).rasters['jersey_1_22_3_cm']['size'] == r['size']


def test_the_loud_test_files_are_written_and_taken_away_again(disc, tmp_path, monkeypatch):
    pytest.importorskip('PIL')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'local'))
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    root = tmp_path / 'rpcs3'
    (root / 'config').mkdir(parents=True)
    (root / 'dev_hdd0' / 'home' / '00000001' / 'savedata').mkdir(parents=True)
    (root / 'rpcs3.exe').write_bytes(b'MZ')
    title = 'BLUS31540' if 'USA' in DISC or 'NA' in os.path.basename(DISC) else 'BLES02153'
    (root / 'config' / 'games.yml').write_text(f'{title}: "{DISC.replace(chr(92), "/")}"\n', encoding='utf-8')
    found = savedata.find_rpcs3(str(root / 'rpcs3.exe'))
    n = rendering.rendering_test(found, title, lambda msg: None)
    assert n >= 5
    game = found.game_folder(title)
    centre = os.path.join(game, 'rendering', 'icesurface', 'centerlogo_22_cm.rpsgl')
    ring = rpsgl.Rpsgl(open(centre, 'rb').read()).image('centerlogo_22_cm').getpixel((512, 70))       # the magenta ring
    assert os.path.exists(centre) and ring[0] > 200 and ring[1] < 80 and ring[2] > 200 and ring[3] == 255
    jersey = os.path.join(game, 'rendering', 'jersey', 'texlib_1_22_3.rpsgl')
    from legacy_roster.art.lab import Disc
    own = rpsgl.Rpsgl(Disc(DISC).render('rendering/jersey/texlib_1_22_3.rpsgl')).image('jersey_1_22_3_cm')
    loud = rpsgl.Rpsgl(open(jersey, 'rb').read()).image('jersey_1_22_3_cm')
    px = (512, 512)
    assert loud.getpixel(px)[0] != own.getpixel(px)[0] or loud.getpixel(px)[2] != own.getpixel(px)[2]
    assert install.installed() == n
    install.remove(lambda msg: None)                               # "Restore the game's own pictures"
    assert not os.path.exists(centre) and not os.path.exists(jersey)
