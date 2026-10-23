"""The Roster editor's "Face of a player" window (app/editor.py): the generic heads as the game's own pictures (its
Create Player menu's, `createplayer/head/head<id>` in cache.big), read from the player's disc; without the disc they
are picked by number. Needs the base roster (conftest.py); the pictures also need LEGACY_ROSTER_DISC (read only)."""
import json
import os
import shutil
import time

import pytest

from legacy_roster import savedata

DISC = os.environ.get('LEGACY_ROSTER_DISC')


class FakeHost:
    def __init__(self):
        self.dirty = set()

    def changed(self, name):
        self.dirty.add(name)

    def log(self, *lines):
        pass

    def log_clear(self):
        pass

    def send(self, event, payload=None):
        pass


def wait(condition, seconds=120):
    end = time.time() + seconds
    while time.time() < end:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError("timed out")


def editor(base_dir, tmp_path, monkeypatch, pack, disc=None):
    """The editor on a pretend RPCS3 with the base roster (`disc`: the game's disc image, said to be in RPCS3's list),
    a player on the card."""
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'local'))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    sd = tmp_path / 'rpcs3' / 'dev_hdd0' / 'home' / '00000001' / 'savedata'
    shutil.copytree(base_dir, sd / os.path.basename(base_dir))
    exe = tmp_path / 'rpcs3' / 'rpcs3.exe'
    exe.write_bytes(b'')
    if disc:
        (tmp_path / 'rpcs3' / 'config').mkdir()
        (tmp_path / 'rpcs3' / 'config' / 'games.yml').write_text(
            ''.join(f'{t}: "{os.path.abspath(disc)}"\n' for t in savedata.GAMES), encoding='utf-8')
    from legacy_roster.app import settings as S
    monkeypatch.setattr(S, 'save', lambda values: None)
    from legacy_roster.app.editor import EditorController
    from legacy_roster.app.update import UpdateController
    host = FakeHost()
    upd = UpdateController(host, settings={'rpcs3': str(exe)}, pack=pack, photos=False)
    ed = EditorController(host, upd)
    upd.start_up()
    wait(lambda: not upd.scanning and upd.slots)
    ed.opened()
    wait(lambda: not ed.busy and ed.after_busy is None)
    rows = ed.snapshot()['rows']
    ed.pick_player(rows[0]['id'])
    return host, ed


def test_without_the_disc_the_generic_heads_are_picked_by_number(base_dir, tmp_path, monkeypatch, pack):
    _host, ed = editor(base_dir, tmp_path, monkeypatch, pack)
    ed.face_open()
    m = ed.snapshot()['modal']
    assert m['kind'] == 'face' and m['pics'] == 'none' and 'RPCS3' in m['note']
    assert m['generic'] and m['generic'][0] >= 60000 and m['current'] == ed.player.face['head']
    assert ed.face_pics_view() == {}


@pytest.mark.skipif(not DISC, reason="needs the game disc (LEGACY_ROSTER_DISC)")
def test_the_generic_heads_show_as_the_games_own_pictures(base_dir, tmp_path, monkeypatch, pack):
    host, ed = editor(base_dir, tmp_path, monkeypatch, pack, DISC)
    ed.face_open()
    assert ed.snapshot()['modal']['pics'] in ('loading', 'ready')
    wait(lambda: ed.snapshot()['modal']['pics'] != 'loading')
    m = ed.snapshot()['modal']
    pics = ed.face_pics_view()
    assert m['pics'] == 'ready' and m['note'] == '' and 'face_pics' in host.dirty
    # the disc has a picture for 211 of the 213 generic heads; the others keep their number
    assert 200 <= len(pics) < len(m['generic']) and set(pics) <= {str(h) for h in m['generic']}
    assert all(url.startswith('data:image/') for url in pics.values())
    json.dumps(ed.snapshot())
    ed.face_search('mc')                     # a search keeps the pictures' state
    assert ed.snapshot()['modal']['pics'] == 'ready'
    head = int(next(iter(pics)))
    ed.face_pick_generic(head)
    s = ed.snapshot()
    assert s['modal'] is None and s['card']['face_pick']['head'] == str(head)
    ed.face_open()                           # read once: the next window has them at once, the picked head marked
    m = ed.snapshot()['modal']
    assert m['pics'] == 'ready' and m['current'] == head and ed.face_pics_view() is pics
