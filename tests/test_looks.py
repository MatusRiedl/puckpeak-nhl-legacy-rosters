"""The new jerseys and centre-ice logos (art/looks.py).

The files themselves are EA's and need the game's disc: set LEGACY_ROSTER_DISC to a disc image (read only); the tests
that need it skip without it. The drawing helpers are tested on small invented pictures."""
import os

import pytest

from legacy_roster import savedata
from legacy_roster.art import install, looks, rpsgl

PIL = pytest.importorskip('PIL')
from PIL import Image  # noqa: E402

DISC = os.environ.get('LEGACY_ROSTER_DISC')


def test_recolour_swaps_flat_colours_keeps_shading_and_blends_edges():
    masters = ((130, 17, 19), (27, 27, 27), (234, 234, 234))
    targets = ((0, 0, 200), (10, 200, 10), (255, 255, 0))
    img = Image.new('RGBA', (3, 1))
    img.putpixel((0, 0), (130, 17, 19, 255))
    img.putpixel((1, 0), (134, 21, 23, 128))                 # a little lighter than the master: stays a little lighter
    img.putpixel((2, 0), (182, 125, 126, 255))               # halfway between red and white: halfway between blue and yellow
    out = looks.recolour(img, masters, targets)
    assert out.getpixel((0, 0)) == (0, 0, 200, 255)
    assert out.getpixel((1, 0)) == (4, 4, 204, 128)          # the alpha is kept
    r, g, b, _ = out.getpixel((2, 0))
    assert 100 < r < 155 and 100 < g < 155 and 90 < b < 110


def test_arena_names_split_into_two_halves():
    assert looks.split_arena("The Delta Center") == ("DELTA", "CENTER")
    assert looks.split_arena("Climate Pledge Arena") == ("CLIMATE", "PLEDGE ARENA")
    assert looks.split_arena("T-Mobile Arena") == ("T-MOBILE", "ARENA")
    assert looks.split_arena("") == ("", "")


def test_the_centre_ice_logo_follows_the_games_own_rules():
    logo = Image.new('RGBA', (100, 80), (200, 30, 30, 255))
    img = looks.centre_logo(logo, "Delta Center", (30, 30, 30))
    assert img.size == (1024, 1024)
    assert img.getpixel((5, 5)) == looks.ICE + (0,)                   # ice-white under what is transparent
    assert img.getpixel((520, 5))[3] == 0 and img.getpixel((520, 512))[3] == 0     # the strip the red line crosses
    assert img.getpixel((520, 512))[0] > 150                          # ... carries the logo's colours
    assert img.getpixel((300, 512))[3] == 255 and img.getpixel((600, 300))[3] == 255
    assert looks.centre_logo(None, "", (0, 0, 0)).getpixel((300, 300)) == looks.ICE + (255,)


def test_a_kit_is_made_from_two_colours():
    kit = looks.kit_for((106, 179, 230), (32, 32, 32))
    assert kit.home.body == (32, 32, 32) and kit.home.trim == (106, 179, 230)
    assert kit.away.trim == looks.WHITE and kit.away.body == (106, 179, 230)


@pytest.fixture(scope='module')
def disc():
    if not DISC or not os.path.exists(DISC):
        pytest.skip("no game disc (set LEGACY_ROSTER_DISC to your NHL Legacy disc image)")
    from legacy_roster.art.lab import Disc
    return Disc(DISC)


def _look(art=22, versions=((3, False), (4, True))):
    logo = Image.new('RGBA', (120, 90), (20, 120, 200, 255))
    return looks.Look(art, looks.kit_for((106, 179, 230), (32, 32, 32)), (logo, logo), "The Delta Center", (32, 32, 32),
                      versions)


def test_every_file_keeps_the_size_and_layout_of_the_discs_and_is_made_the_same_way_twice(disc):
    maker = looks.Maker(disc)
    files = maker.files(_look(30, ((4, False), (5, True))))
    assert sorted(files) == sorted(looks.look_paths(_look(30, ((4, False), (5, True)))))
    for inner, data in files.items():
        if inner.endswith('.rpsgl'):
            mine, own = rpsgl.Rpsgl(data), rpsgl.Rpsgl(disc.render(inner))
            assert {k: (r['width'], r['height'], r['mips'], r['format'], r['size']) for k, r in mine.rasters.items()} == \
                   {k: (r['width'], r['height'], r['mips'], r['format'], r['size']) for k, r in own.rasters.items()}
            assert mine.build() == data
    assert looks.Maker(disc).files(_look(30, ((4, False), (5, True)))) == files          # rule 4: deterministic
    jersey = rpsgl.Rpsgl(files['rendering/jersey/texlib_1_30_4.rpsgl']).image('jersey_1_30_4_cm')
    assert jersey.getpixel((100, 100))[:3] != rpsgl.Rpsgl(disc.render('rendering/jersey/texlib_1_30_4.rpsgl')).image(
        'jersey_1_30_4_cm').getpixel((100, 100))[:3]


def test_installing_twice_writes_once_and_restoring_puts_the_game_back(disc, tmp_path, monkeypatch):
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
    look = _look(22, ((3, False),))
    n = looks.install_looks(found, title, [look], lambda msg: None)
    assert n == len(looks.look_paths(look))
    game = found.game_folder(title)
    centre = os.path.join(game, 'rendering', 'icesurface', 'centerlogo_22_cm.rpsgl')
    assert os.path.exists(centre) and os.path.exists(os.path.join(game, 'fe', 'ion', 'artassets', 'jerseys', 'jersey_1_22_3.big'))
    assert looks.install_looks(found, title, [look], lambda msg: None) == 0           # nothing to do the second time
    assert looks.install_looks(found, title, [_look(22, ((3, False),))._replace(arena="Other Arena")], lambda msg: None) == n
    install.remove(lambda msg: None)                                                  # "Restore the game's own pictures"
    assert not os.path.exists(centre) and install.installed() == 0


def _fake_rpcs3(tmp_path, monkeypatch):
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
    return savedata.find_rpcs3(str(root / 'rpcs3.exe')), title


def test_a_players_own_jersey_and_ice_are_installed_and_put_back_when_chosen_away(disc, base_dir, tmp_path, monkeypatch):
    from legacy_roster import layout as L
    from legacy_roster.roster import Roster
    R = Roster(os.path.join(base_dir, 'SYS-DATA'))
    slot = L.API_TO_SLOT['EDM']
    found, title = _fake_rpcs3(tmp_path, monkeypatch)
    maker = looks.Maker(disc)
    versions = looks.roster_versions(R, slot)
    variant, light = versions[0][0], versions[0][1]
    own = maker.own_colour_map(slot, variant).convert('RGB')
    own.paste((0, 200, 0), (100, 300, 200, 700))                        # a green bar painted on the game's own
    mine = tmp_path / 'mine.png'
    own.save(mine)
    ice = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
    ice.paste((200, 0, 200, 255), (200, 200, 800, 800))
    ice_png = tmp_path / 'ice.png'
    ice.save(ice_png)
    other = versions[-1][0]
    edit = {slot: {'uniforms': {'colours': {'primary': '#ff00ff'}, 'versions': {str(variant): 'file:' + str(mine),
                                                                                   str(other): 'colours'}},
                   'ice': {'use': 'file:' + str(ice_png), 'arena': 'Test Arena'}}}
    made = [m for m in looks.looks_from(R, edit, {}, {}) if m.art == slot]
    assert len(made) == 1 and made[0].files[0][0] == variant and made[0].versions == ((other, versions[-1][1]),)
    n = looks.install_looks(found, title, made, lambda msg: None)
    game = found.game_folder(title)
    jersey = os.path.join(game, 'rendering', 'jersey', f'texlib_1_{slot}_{variant}.rpsgl')
    centre = os.path.join(game, 'rendering', 'icesurface', f'centerlogo_{slot}_cm.rpsgl')
    bar = rpsgl.Rpsgl(open(jersey, 'rb').read()).image(f'jersey_1_{slot}_{variant}_cm').getpixel((150, 500))
    assert bar[1] > 150 and bar[0] < 80                                        # the player's green bar is in the game's file
    ring = rpsgl.Rpsgl(open(centre, 'rb').read()).image(f'centerlogo_{slot}_cm')
    assert ring.getpixel((500, 500))[3] == 0 and ring.getpixel((300, 500))[0] > 150      # own picture, strip made clear
    assert looks.install_looks(found, title, made, lambda msg: None) == 0       # installed already
    again = [m._replace(centre='game', files=()) for m in made]                 # chosen "the game's own" since
    looks.install_looks(found, title, again, lambda msg: None)
    assert not os.path.exists(jersey) and not os.path.exists(centre)             # the game's own is back
    assert os.path.exists(os.path.join(game, 'rendering', 'jersey', f'texlib_1_{slot}_{other}.rpsgl'))
    install.remove(lambda msg: None)
    assert install.installed() == 0 and n > 3
