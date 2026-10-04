import datetime
import os
import shutil

import pytest

from legacy_roster import savedata
from legacy_roster.sfo import Sfo


@pytest.fixture
def rpcs3(tmp_path, base_dir):
    """A pretend RPCS3 folder with one roster save and one save of another kind."""
    sd = tmp_path / 'rpcs3' / 'dev_hdd0' / 'home' / '00000001' / 'savedata'
    shutil.copytree(base_dir, sd / 'BLES021530202')
    other = sd / 'BLES021530000'
    other.mkdir()
    (other / 'SYS-DATA').write_bytes(b'PS3ProfileFile\0\0' + b'\0' * 64)
    (other / 'PARAM.SFO').write_bytes((sd / 'BLES021530202' / 'PARAM.SFO').read_bytes())
    return tmp_path / 'rpcs3'


def test_the_save_folder_is_found_from_any_level(rpcs3):
    sd = str(rpcs3 / 'dev_hdd0' / 'home' / '00000001' / 'savedata')
    for start in (rpcs3, rpcs3 / 'dev_hdd0', rpcs3 / 'dev_hdd0' / 'home', rpcs3 / 'dev_hdd0' / 'home' / '00000001', sd):
        assert savedata.find_savedata(str(start)) == (sd, None)
    assert savedata.find_savedata(os.path.join(sd, 'BLES021530202')) == (sd, 'BLES021530202')
    assert savedata.find_savedata(os.path.join(sd, 'BLES021530202', 'SYS-DATA')) == (sd, 'BLES021530202')
    assert savedata.find_savedata(os.path.join(sd, 'BLES021530000')) == (sd, None)   # the profile save's folder


def test_the_game_is_found_in_rpcs3s_game_list(rpcs3, tmp_path):
    (rpcs3 / 'rpcs3.exe').write_bytes(b'MZ')
    disc = tmp_path / 'NHL Legacy.iso'
    disc.write_bytes(b'')
    (rpcs3 / 'config').mkdir()
    # written by a tool that puts a byte-order mark first: the first key must still be found
    (rpcs3 / 'config' / 'games.yml').write_text(f'BLES02153: "{disc.as_posix()}"\nBLUS31540: x\n', encoding='utf-8-sig')
    r = savedata.find_rpcs3(str(rpcs3 / 'rpcs3.exe'))
    assert r.game_disc('BLES02153') == str(disc) and r.game_disc('BLUS31540') is None
    assert r.game_folder('BLES02153') == os.path.join(str(rpcs3), 'dev_hdd0', 'game', 'BLES02153', 'USRDIR')


def test_rpcs3_is_resolved_to_its_save_folder(rpcs3):
    sd = str(rpcs3 / 'dev_hdd0' / 'home' / '00000001' / 'savedata')
    (rpcs3 / 'rpcs3.exe').write_bytes(b'MZ')
    for pointed_at in (rpcs3 / 'rpcs3.exe', rpcs3, f'"{rpcs3 / "rpcs3.exe"}"'):
        found = savedata.find_rpcs3(str(pointed_at))
        assert (found.savedata, found.user, found.folder) == (sd, '00000001', str(rpcs3))
        assert found.exe == str(rpcs3 / 'rpcs3.exe')


def test_a_folder_inside_rpcs3_leads_to_it(rpcs3):
    """Version 0.1 remembered the save folder; the program is found above it."""
    sd = rpcs3 / 'dev_hdd0' / 'home' / '00000001' / 'savedata'
    (rpcs3 / 'rpcs3.exe').write_bytes(b'MZ')
    for inside in (sd, sd / 'BLES021530202', rpcs3 / 'dev_hdd0'):
        found = savedata.find_rpcs3(str(inside))
        assert (found.exe, found.savedata) == (str(rpcs3 / 'rpcs3.exe'), str(sd))


def test_anything_that_is_not_rpcs3_is_refused_in_plain_words(rpcs3, tmp_path):
    (tmp_path / 'notepad.exe').write_bytes(b'MZ')
    sd = rpcs3 / 'dev_hdd0' / 'home' / '00000001' / 'savedata'
    for wrong in (tmp_path / 'notepad.exe', tmp_path, sd, sd / 'BLES021530202', rpcs3, ''):
        with pytest.raises(savedata.Rpcs3Error, match="not RPCS3"):      # rpcs3: the exe is not there yet
            savedata.find_rpcs3(str(wrong))


def test_rpcs3_without_a_roster_says_what_to_do(tmp_path):
    (tmp_path / 'rpcs3.exe').write_bytes(b'MZ')
    (tmp_path / 'dev_hdd0' / 'home' / '00000001' / 'savedata').mkdir(parents=True)
    with pytest.raises(savedata.Rpcs3Error, match="no roster saved"):
        savedata.find_rpcs3(str(tmp_path / 'rpcs3.exe'))


def test_a_relocated_dev_hdd0_is_followed(rpcs3, tmp_path):
    """RPCS3 lets the virtual hard disk live elsewhere (config/vfs.yml)."""
    (rpcs3 / 'rpcs3.exe').write_bytes(b'MZ')
    moved = tmp_path / 'elsewhere' / 'hdd0'
    shutil.move(str(rpcs3 / 'dev_hdd0'), str(moved))
    (rpcs3 / 'config').mkdir()
    for line in (f'/dev_hdd0/: {moved.as_posix()}/', '/dev_hdd0/: "$(EmulatorDir)../elsewhere/hdd0/"'):
        (rpcs3 / 'config' / 'vfs.yml').write_text(f'$(EmulatorDir): ""\n{line}\n/dev_hdd1/: $(EmulatorDir)dev_hdd1/\n',
                                                  encoding='utf-8')
        assert savedata.find_rpcs3(str(rpcs3)).savedata == str(moved / 'home' / '00000001' / 'savedata')


def test_with_several_rpcs3_users_the_active_one_wins_else_the_newest_roster(rpcs3):
    (rpcs3 / 'rpcs3.exe').write_bytes(b'MZ')
    home = rpcs3 / 'dev_hdd0' / 'home'
    shutil.copytree(home / '00000001' / 'savedata' / 'BLES021530202', home / '00000002' / 'savedata' / 'BLES021530202')
    (home / '00000003' / 'savedata').mkdir(parents=True)             # a user without rosters
    os.utime(home / '00000002' / 'savedata' / 'BLES021530202' / 'SYS-DATA', (2_000_000_000, 2_000_000_000))
    assert savedata.find_rpcs3(str(rpcs3)).user == '00000002'       # newest roster
    (rpcs3 / 'GuiConfigs').mkdir()
    (rpcs3 / 'GuiConfigs' / 'persistent_settings.dat').write_text('[Playtime]\nX=1\n\n[Users]\nactive_user=00000001\n')
    assert savedata.find_rpcs3(str(rpcs3)).user == '00000001'       # what RPCS3 is set to
    (rpcs3 / 'GuiConfigs' / 'persistent_settings.dat').write_text('[Users]\nactive_user=00000003\n')
    assert savedata.find_rpcs3(str(rpcs3)).user == '00000002'       # the active user has none: newest again


def test_a_folder_without_rosters_gives_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="No NHL Legacy roster save"):
        savedata.find_savedata(str(tmp_path))


def test_only_roster_saves_are_listed(rpcs3):
    sd, _ = savedata.find_savedata(str(rpcs3))
    slots = savedata.list_rosters(sd)
    assert [(s.folder, s.name, s.title_id, s.number) for s in slots] == [('BLES021530202', 'ROSTER2526', 'BLES02153', 2)]
    assert not slots[0].tool_made


def test_install_writes_a_new_save_and_leaves_the_source_alone(rpcs3, base_bytes):
    sd, _ = savedata.find_savedata(str(rpcs3))
    source = savedata.list_rosters(sd)[0]
    before = {f: open(os.path.join(source.path, f), 'rb').read() for f in savedata.FILES}
    new = savedata.install(sd, source, base_bytes, '2026-10-02 20:45')
    assert new.folder == 'BLES021530203' and new.name == '2026-10-02 20:45' and new.tool_made
    assert sorted(os.listdir(new.path)) == sorted(savedata.FILES)
    sfo = Sfo.load(os.path.join(new.path, 'PARAM.SFO'))
    assert sfo.get('SAVEDATA_DIRECTORY') == 'BLES021530203' and sfo.get('DETAIL') == 'Rosters'
    assert open(new.sys_data, 'rb').read() == base_bytes
    assert {f: open(os.path.join(source.path, f), 'rb').read() for f in savedata.FILES} == before
    assert savedata.install(sd, source, base_bytes, 'again').folder == 'BLES021530204'
    assert not [n for n in os.listdir(os.path.dirname(sd)) if n.startswith('.roster-updater')]   # no leftovers


def test_next_free_skips_other_titles_and_wraps(tmp_path):
    for name in ('BLES021530200', 'BLES021530207', 'BLUS315400250', 'BLES021530000'):
        (tmp_path / name).mkdir()
    assert savedata.next_free(str(tmp_path), 'BLES02153') == 'BLES021530208'
    assert savedata.next_free(str(tmp_path), 'BLUS31540') == 'BLUS315400251'
    (tmp_path / 'BLES021530299').mkdir()
    assert savedata.next_free(str(tmp_path), 'BLES02153') == 'BLES021530201'


def test_names():
    assert savedata.default_name(datetime.datetime(2026, 10, 2, 20, 45)) == '2026-10-02 20:45'
    assert savedata.clean_name('  My roster™ <1>  ') == 'My roster 1'
    assert savedata.clean_name('x' * 80) == 'x' * 40
    assert savedata.TOOL_NAME.match('R261002-2045') and not savedata.TOOL_NAME.match('ROSTER2526')
