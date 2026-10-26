"""The main menu without the entries the game's servers took with them (art/menus.py) and the lab probe
that installs it (tools/menu_probe.py). The menu tests need the game disc (LEGACY_ROSTER_DISC, read
only); the probe's own tests run without it, in a fake lab under tmp_path."""
import os
import struct

import pytest

from legacy_roster.art import menus, refpack
from tools import menu_probe

DISC = os.environ.get('LEGACY_ROSTER_DISC')
needs_disc = pytest.mark.skipif(not DISC, reason="needs the game disc (LEGACY_ROSTER_DISC)")
KEPT = [('itemOnline', 'TXT_UNICORN_MODE'), ('itemOnline', 'OnlineVersusPlay'), ('itemOnline', 'OnlineTeamPlay'),
        ('itemOnline', 'OnlineShootout'), ('arrPlay', 'TXT_ONLINE'), ('arrPlay', 'PlayNow'),
        ('arrRootMenu', 'TXT_COMMUNITY'), ('arrOnlineCommunity', 'TXT_LOCAL_MEDIA')]


@pytest.fixture(scope='module')
def original():
    return menus.original_file(DISC)


def _movie(data):
    bigf = menus.Bigf(data)
    return bigf, menus.Movie(bigf.part('0'), bigf.part('1'))


@needs_disc
@pytest.mark.parametrize('mode', [menus.HIDE, menus.REMOVE])
def test_same_copy_twice(original, mode):
    assert menus.hidden_file(original, mode) == menus.hidden_file(original, mode)
    assert menus.hidden_files(DISC, mode) == {menus.REL: menus.hidden_file(original, mode)}


@needs_disc
def test_hide_marks_the_dead_entries_only(original):
    before = menus.menu_entries(original)
    after = menus.menu_entries(menus.hidden_file(original, menus.HIDE))
    assert [(a, k) for a, k, _h in after] == [(a, k) for a, k, _h in before]
    assert not any(h for _a, _k, h in before)
    assert sorted((a, k) for a, k, h in after if h) == sorted(menus.DEAD)
    for item in KEPT:
        assert (*item, False) in after


@needs_disc
def test_remove_leaves_the_dead_entries_out(original):
    before = [(a, k) for a, k, _h in menus.menu_entries(original)]
    after = [(a, k) for a, k, _h in menus.menu_entries(menus.hidden_file(original, menus.REMOVE))]
    assert after == [e for e in before if e not in menus.DEAD]
    assert len(before) - len(after) == len(menus.DEAD)
    assert set(KEPT) <= set(after)


@needs_disc
@pytest.mark.parametrize('mode', [menus.HIDE, menus.REMOVE])
def test_nothing_else_changes(original, mode):
    _bigf, old = _movie(original)
    bigf, new = _movie(menus.hidden_file(original, mode))
    assert len(new.data) == len(old.data)
    changed = menus.changes(old, mode)
    assert len(changed) == len(menus.DEAD)
    data = bytearray(old.data)
    for at, before, after in changed:
        assert len(before) == len(after) and old.data[at:at + len(before)] == before
        data[at:at + len(after)] = after
    assert bytes(data) == new.data              # outside the changed bytes the movie is as it was
    assert bigf.part('1') == menus.Bigf(original).part('1')
    for start in old.streams():                 # every script still reads to its own end
        assert new.code(start)[-1].end == old.code(start)[-1].end
    if mode == menus.HIDE:                      # 5 pairs swapped, 3 or 4 bytes each
        assert all(after.endswith(b'\x73') and len(after) in (3, 4) for _at, _b, after in changed)


@needs_disc
@pytest.mark.parametrize('mode', [menus.HIDE, menus.REMOVE])
def test_archive_layout(original, mode):
    copy = menus.hidden_file(original, mode)
    old, new = menus.Bigf(original), menus.Bigf(copy)
    assert [n for n, _o, _s in new.parts] == [n for n, _o, _s in old.parts] == ['0', 'sg2', '1']
    assert copy[:4] == b'BIGF' and copy[8:16] == original[8:16]
    assert copy[-16:] == original[-16:] and len(copy) == new.end + 16
    last = max(o + s for _n, o, s in new.parts)
    assert new.end == (last + 3) // 4 * 4
    offsets = {n: (o, s) for n, o, s in new.parts}
    assert offsets['0'][0] == 64 and all(o % 64 == 0 for o, _s in offsets.values())
    assert offsets['sg2'] == (offsets['1'][0], 0)
    assert offsets['1'][0] == (64 + offsets['0'][1] + 63) // 64 * 64
    packed = new.part('0')
    assert refpack.unpacked_size(packed) == refpack.unpacked_size(old.part('0')) == 33938
    for name, (o, s) in offsets.items():       # the table's places hold the parts
        assert struct.unpack_from('>II', copy, new.table[[n for n, _o, _s in new.parts].index(name)]) == (o, s)


@needs_disc
def test_rebuilt_archive_is_the_original(original):
    assert menus.Bigf(original).rebuilt({}) == original


def test_filler_does_nothing():
    for n in range(2, 40):
        code = menus._filler(n)
        assert len(code) == n and set(code) <= {0x59, 0x17, 0x12}
        assert code.count(0x59) == code.count(0x17)     # each push popped
    with pytest.raises(ValueError):
        menus._filler(1)
    assert menus._hidden_pair(3, 0x45) == b'\xa2\x45\x73'
    assert menus._hidden_pair(4, 0x45) == b'\xa3\x00\x45\x73'
    assert menus._hidden_pair(5, 0x45) == b'\x59\x17\xa2\x45\x73'
    assert menus._hidden_pair(4, 300) == b'\xa3\x01\x2c\x73'
    with pytest.raises(ValueError):
        menus._hidden_pair(3, 300)          # a constant above 255 needs the 3-byte push


# --- installed with "Photos, logos and team names" -----------------------------------------------

@pytest.fixture
def game(tmp_path, monkeypatch):
    from legacy_roster import datasource, savedata
    monkeypatch.setattr(datasource, 'data_home', lambda: str(tmp_path / 'appdata'))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    folder = tmp_path / 'dev_hdd0' / 'game' / 'BLES02153' / 'USRDIR'
    folder.mkdir(parents=True)
    return str(folder)


def test_the_menu_goes_in_once_and_restore_takes_it_away(game, monkeypatch):
    from legacy_roster.art import install
    made = []
    monkeypatch.setattr(menus, 'menu_files', lambda disc, mode: made.append(mode) or {menus.REL: b'BIGF ' + mode.encode()})
    says, path = [], os.path.join(game, *menus.REL)
    writer = install._Writer([game])
    assert install.install_menus('disc', writer, says.append) == 1
    writer.save()
    with open(path, 'rb') as f:
        assert f.read() == b'BIGF ' + menus.HIDE.encode()
    assert says == ["Photos and logos: the main menu leaves out the online entries that no longer work"]
    assert install.install_menus('disc', install._Writer([game]), says.append) == 0 and made == [menus.HIDE]
    install.remove(say=lambda m: None)                  # "Restore the game's own pictures"
    assert not os.path.exists(path)


def test_a_disc_without_the_menu_leaves_it_as_it_is(game, monkeypatch):
    from legacy_roster.art import install

    def broken(disc, mode):
        raise KeyError(menus.MENU_FILE)
    monkeypatch.setattr(menus, 'menu_files', broken)
    says = []
    assert install.install_menus('disc', install._Writer([game]), says.append) == 0
    assert says[0].startswith("Photos and logos: the main menu was left as it is")
    assert not os.path.exists(os.path.join(game, *menus.REL))


@needs_disc
def test_the_installed_menu_is_the_hidden_copy_with_the_online_start(game, original):
    from legacy_roster.art import install, onlinestart
    writer = install._Writer([game])
    assert install.install_menus(DISC, writer, lambda m: None) == 1
    writer.save()
    with open(os.path.join(game, *menus.REL), 'rb') as f:
        assert f.read() == onlinestart.start_file(original, menus.HIDE)


# --- the lab probe -------------------------------------------------------------------------------

def _lab(tmp_path, marker=True):
    usrdir = tmp_path / 'lab' / 'rpcs3' / 'dev_hdd0' / 'game' / 'BLES02153' / 'USRDIR'
    usrdir.mkdir(parents=True)
    if marker:
        (tmp_path / 'lab' / 'launch_lab.ps1').write_text('# lab')
    return usrdir


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.setattr(menu_probe.savedata, 'running_rpcs3', lambda: None)
    monkeypatch.setattr(menu_probe.menus, 'hidden_files', lambda disc, mode: {menus.REL: b'BIGF new ' + mode.encode()})
    monkeypatch.setenv('LEGACY_ROSTER_DISC', __file__)


def test_probe_refuses_anything_but_a_lab(tmp_path, probe):
    with pytest.raises(SystemExit):
        menu_probe.main(['install', '--game-dir', str(_lab(tmp_path, marker=False))])
    with pytest.raises(SystemExit):
        menu_probe.main(['install', '--game-dir', str(tmp_path)])
    assert not any(p.is_file() for p in tmp_path.rglob('*'))


def test_probe_refuses_while_rpcs3_runs(tmp_path, probe, monkeypatch):
    usrdir = _lab(tmp_path)
    monkeypatch.setattr(menu_probe.savedata, 'running_rpcs3', lambda: 'rpcs3.exe')
    with pytest.raises(SystemExit):
        menu_probe.main(['install', '--game-dir', str(usrdir)])
    assert not (usrdir / 'fe').exists()


def test_probe_install_and_remove(tmp_path, probe):
    usrdir = _lab(tmp_path)
    target = usrdir.joinpath(*menus.REL)
    assert menu_probe.main(['install', '--game-dir', str(usrdir)]) == 0
    assert target.read_bytes() == b'BIGF new hide'
    assert menu_probe.main(['install', '--game-dir', str(usrdir), '--mode', 'remove']) == 0
    assert target.read_bytes() == b'BIGF new remove'
    assert menu_probe.main(['remove', '--game-dir', str(usrdir)]) == 0
    assert not target.exists() and not (usrdir / 'fe').exists()     # the folders it made are gone too


def test_probe_keeps_and_puts_back_a_file_that_was_there(tmp_path, probe):
    usrdir = _lab(tmp_path)
    target = usrdir.joinpath(*menus.REL)
    target.parent.mkdir(parents=True)
    target.write_bytes(b'somebody else')
    menu_probe.main(['install', '--game-dir', str(usrdir)])
    menu_probe.main(['install', '--game-dir', str(usrdir)])          # a second install keeps the first kept copy
    assert target.read_bytes() == b'BIGF new hide'
    kept = tmp_path / 'lab' / 'menu_probe' / 'BLES02153' / 'kept' / os.path.join(*menus.REL)
    assert kept.read_bytes() == b'somebody else'
    menu_probe.main(['remove', '--game-dir', str(usrdir)])
    assert target.read_bytes() == b'somebody else' and not kept.exists()


def test_probe_leaves_a_changed_file_alone(tmp_path, probe):
    usrdir = _lab(tmp_path)
    target = usrdir.joinpath(*menus.REL)
    menu_probe.main(['install', '--game-dir', str(usrdir)])
    target.write_bytes(b'changed by hand')
    menu_probe.main(['remove', '--game-dir', str(usrdir)])
    assert target.read_bytes() == b'changed by hand'
