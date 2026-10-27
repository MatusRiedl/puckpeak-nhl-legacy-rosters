"""The picture parts of 0.76.0 (art/parts.py): arenas, bright ice and team masks from small downloaded packs, team names
on their own, and Restore of one part at a time. Synthetic discs as in test_art.py: no game files are needed."""
import hashlib
import io
import json
import os
import zipfile
from types import SimpleNamespace

import pytest

from legacy_roster import packs, pipeline
from legacy_roster.art import arenas, brightice, install, lab, masks, menus, parts, rpsgl
from legacy_roster.art.extrapack import ExtraPack

from .test_art import SizedDisc, fake_rpcs3

QUIET = lambda msg: None
TITLE = 'BLES02153'


@pytest.fixture(autouse=True)
def no_menu(monkeypatch):
    monkeypatch.setattr(menus, 'menu_files', lambda disc, mode: {})


class Files:
    """Stands in for the player's disc: the 3D files by inner path (their unpacked bytes), packed on request."""
    files = {}

    def __init__(self, _path):
        pass

    def render(self, inner):
        data = self.files.get(inner)
        return None if data is None else rpsgl.pack(data)


def make_zip(path, index, members=None):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('index.json', json.dumps(index))
        for name, data in (members or {}).items():
            z.writestr(name, data)
    return ExtraPack(path)


def loose(r, *rel):
    return os.path.join(r.game_folder(TITLE), *rel)


def arena_pack(tmp_path, base, art='3', runs=((0, 4), (100, 3)), new=b'NEWBYTES', ident='r1'):
    entry = {'base': hashlib.sha1(base).hexdigest(), 'id': ident, 'runs': [list(r) for r in runs], 'file': f"a/{art}.bin"}
    return make_zip(str(tmp_path / f"arenas-{ident}.zip"), {'format': 1, 'built': 'test', 'arenas': {art: entry}},
                    {f"a/{art}.bin": new[:sum(n for _o, n in runs)]})


# --- arenas ---------------------------------------------------------------------------------------------
def test_arena_runs_are_laid_over_the_discs_file_and_nothing_else(base_dir, tmp_path, monkeypatch):
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    base = bytes(range(256)) * 8
    Files.files = {arenas.STADIUM.format(a=3): base}
    monkeypatch.setattr(lab, 'Disc', Files)
    pack = arena_pack(tmp_path, base)
    assert arenas.install_arenas(r, TITLE, pack, QUIET) == 1
    path = loose(r, *arenas.STADIUM.format(a=3).split('/'))
    made = rpsgl.unpack(open(path, 'rb').read())
    want = bytearray(base)
    want[0:4], want[100:103] = b'NEWB', b'YTE'
    assert made == bytes(want) and len(made) == len(base)
    assert arenas.install_arenas(r, TITLE, pack, QUIET) == 0                 # the same pack again: nothing written


def test_an_arena_for_another_version_of_the_game_is_left_as_it_is(base_dir, tmp_path, monkeypatch):
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    Files.files = {arenas.STADIUM.format(a=3): b'a different file' * 50}
    monkeypatch.setattr(lab, 'Disc', Files)
    skipped = []
    pack = arena_pack(tmp_path, b'the file the pack was made for' * 20)
    assert arenas.install_arenas(r, TITLE, pack, QUIET, skipped=skipped) == 0
    assert [a for a, _why in skipped] == ['3'] and 'another version' in skipped[0][1]
    assert not os.path.exists(loose(r, *arenas.STADIUM.format(a=3).split('/')))


def test_an_arena_the_pack_no_longer_holds_goes_back_to_the_games_own(base_dir, tmp_path, monkeypatch):
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    base = bytes(range(256)) * 8
    Files.files = {arenas.STADIUM.format(a=3): base, arenas.STADIUM.format(a=4): base}
    monkeypatch.setattr(lab, 'Disc', Files)
    both = arena_pack(tmp_path, base, art='3', ident='r1')
    arenas.install_arenas(r, TITLE, both, QUIET)
    four = arena_pack(tmp_path, base, art='4', ident='r2')
    arenas.install_arenas(r, TITLE, four, QUIET)
    assert not os.path.exists(loose(r, *arenas.STADIUM.format(a=3).split('/')))
    assert os.path.exists(loose(r, *arenas.STADIUM.format(a=4).split('/')))


# --- bright ice ------------------------------------------------------------------------------------------
def png(color=(250, 250, 250, 255)):
    from PIL import Image
    out = io.BytesIO()
    Image.new('RGBA', (8, 8), color).save(out, 'PNG')
    return out.getvalue()


def ice_pack(tmp_path, ident='i1'):
    pytest.importorskip('PIL')
    index = {'format': 1, 'built': ident, 'hotspots': {'ice_hotspot_0_2_cm': 'h/a.png'}, 'centres': {'7': 'c/7.png', '22': 'c/22.png'}}
    return make_zip(str(tmp_path / f"ice-{ident}.zip"), index, {'h/a.png': png(), 'c/7.png': png(), 'c/22.png': png()})


def test_bright_ice_writes_its_files_and_leaves_a_centre_the_look_pack_installed(base_dir, tmp_path, monkeypatch):
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    Files.files = {}
    monkeypatch.setattr(lab, 'Disc', Files)
    monkeypatch.setattr(brightice, '_file', lambda disc, inner, raster, picture: f"ICE {raster}".encode())
    centre22 = tuple(brightice.CENTRE.format(a=22).split('/'))
    writer = install._Writer([r.game_folder(TITLE)])
    writer.write(centre22, b'this season', 'looks:abc')                       # the look pack's centre ice for team 22
    writer.save()
    pack = ice_pack(tmp_path)
    assert brightice.install_bright(r, TITLE, pack, QUIET) == 2                # the hotspot and centre 7
    assert open(loose(r, *centre22), 'rb').read() == b'this season'
    assert open(loose(r, 'rendering', 'icesurface', 'ice_hotspot_0_2_cm.rpsgl'), 'rb').read() == b'ICE ice_hotspot_0_2_cm'
    assert brightice.install_bright(r, TITLE, pack, QUIET) == 0


# --- team masks ------------------------------------------------------------------------------------------
def test_team_masks_leave_a_mask_picture_of_the_players_own(base_dir, tmp_path, monkeypatch):
    pytest.importorskip('PIL')
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    Files.files = {}
    monkeypatch.setattr(lab, 'Disc', Files)
    monkeypatch.setattr(masks, 'mask_file', lambda disc, n, picture: f"MASK {n}".encode())
    pack = make_zip(str(tmp_path / 'masks.zip'), {'format': 1, 'built': 'm1', 'masks': {'2': 'm/2.png', '9': 'm/9.png', '10': 'm/10.png'}},
                    {'m/2.png': png(), 'm/9.png': png(), 'm/10.png': png()})
    assert masks.install_team_masks(r, TITLE, pack, QUIET, own={9}) == 2
    assert open(loose(r, *masks.MASK.format(n=2).split('/')), 'rb').read() == b'MASK 2'
    assert not os.path.exists(loose(r, *masks.MASK.format(n=9).split('/')))
    assert masks.install_team_masks(r, TITLE, pack, QUIET, own={9}) == 0


# --- one part at a time -----------------------------------------------------------------------------------
def test_restoring_one_part_puts_back_only_its_files(base_dir, tmp_path, monkeypatch):
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    base = bytes(range(256)) * 8
    Files.files = {arenas.STADIUM.format(a=3): base}
    monkeypatch.setattr(lab, 'Disc', Files)
    arenas.install_arenas(r, TITLE, arena_pack(tmp_path, base), QUIET)
    writer = install._Writer([r.game_folder(TITLE)])
    other = ('fe', 'ion', 'artassets', 'teamlogos', 't22.big')
    writer.write(other, b'a logo', 'https://logo/uta.png#2')                  # a logo: the photos part
    writer.save()
    stadium = loose(r, *arenas.STADIUM.format(a=3).split('/'))
    assert install.remove_parts([parts.ARENAS], QUIET) == 1
    assert not os.path.exists(stadium) and os.path.exists(loose(r, *other))
    assert install.remove_parts([parts.ARENAS], QUIET) == 0                   # nothing of it is left
    assert install.remove_parts([parts.PHOTOS], QUIET) == 1 and not os.path.exists(loose(r, *other))


def test_every_installed_file_belongs_to_exactly_one_part():
    assert parts.belongs('looks:abc', parts.LOOKS) and not parts.belongs('looks:abc', parts.PHOTOS)
    assert parts.belongs('arenas:#1:3:x', parts.ARENAS) and not parts.belongs('arenas:#1:3:x', parts.PHOTOS)
    assert parts.belongs('names:abc', parts.NAMES) and parts.belongs('menus:#3hide', parts.NAMES)
    assert parts.belongs('https://photo/a.png#4', parts.PHOTOS) and parts.belongs('crests:x', parts.PHOTOS)
    assert parts.belongs('mask:#1:200:abc', parts.PHOTOS) and parts.belongs('teammask:#1:2:b', parts.TEAM_MASKS)
    assert parts.packs_for({parts.NAMES}) == [] and parts.packs_for(parts.LEGACY) == ['photos', 'looks']
    assert parts.packs_for(set(parts.ALL)) == ['photos', 'looks', 'arenas', 'ice', 'masks']


# --- the update puts in only what is switched on ---------------------------------------------------------------
def result_of(names=None):
    return SimpleNamespace(art=({}, {}, names), builder=SimpleNamespace(bad_pictures={}, mask_looks={}), log=[], data=b'')


def test_pictures_do_only_the_parts_that_are_on(base_dir, tmp_path, monkeypatch):
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    names = SimpleNamespace(photos=pipeline.Pictures(r, TITLE, parts={parts.NAMES}).photos,
                            own=pipeline.Pictures(r, TITLE, parts={parts.NAMES}).own_only)
    assert names.photos is False and names.own            # team names alone: photos and logos stay as they are
    legacy = pipeline.Pictures(r, TITLE)
    assert legacy.parts == parts.LEGACY and legacy.photos and legacy.names_on
    mine = pipeline.Pictures(r, TITLE, own_only=True)
    assert mine.parts == frozenset() and mine.own_only and not mine.names_on

    called = []
    monkeypatch.setattr(install, 'install', lambda *a, **k: called.append(k) or (0, 0, 0))
    monkeypatch.setattr(pipeline, 'install_arenas', lambda *a: called.append('arenas'))
    monkeypatch.setattr(pipeline, 'install_looks', lambda *a: called.append('looks') or 0)
    pipeline.Pictures(r, TITLE, parts={parts.ARENAS}).put_in(result_of(), QUIET)
    assert called == ['arenas']                           # no names, no photos: install.install is not even called
    called.clear()
    pipeline.Pictures(r, TITLE, parts={parts.NAMES}).put_in(result_of({'teams': []}), QUIET)
    assert len(called) == 1 and called[0]['menus'] and called[0]['pictures'] is False and called[0]['names'] == {'teams': []}
    called.clear()
    assert pipeline.Pictures(r, TITLE, parts=()).put_in(result_of(), QUIET) == (None, 0, False)   # nothing of the player's
    assert called == []
