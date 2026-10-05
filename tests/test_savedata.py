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
    with pytest.raises(savedata.Rpcs3Error, match="no roster of NHL Legacy"):
        savedata.find_rpcs3(str(tmp_path / 'rpcs3.exe'))


def test_without_any_roster_the_games_own_roster_is_saved_from_scratch(tmp_path, monkeypatch, base_bytes):
    """A player who never saved a roster: RPCS3 lists the game, so it offers the game's own roster,
    and the new save gets a PARAM.SFO made from scratch and the icon of the player's disc."""
    from legacy_roster import stock
    (tmp_path / 'rpcs3.exe').write_bytes(b'MZ')
    disc = tmp_path / 'NHL Legacy (USA).iso'
    disc.write_bytes(b'not read here')
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config' / 'games.yml').write_text(f'BLUS31540: "{disc.as_posix()}"\n', encoding='utf-8')
    r = savedata.find_rpcs3(str(tmp_path / 'rpcs3.exe'))
    assert r.user == '00000001' and not os.path.exists(r.savedata)          # never saved anything
    [slot] = r.disc_slots()
    assert (slot.title_id, slot.region, slot.folder, slot.disc) == ('BLUS31540', 'NA', 'BLUS31540 game', True)
    monkeypatch.setattr(stock, 'disc_icon', lambda path: b'\x89PNG icon of the disc')
    new = savedata.install(r.savedata, slot, base_bytes, 'From the game')
    assert new.folder == 'BLUS315400200' and new.region == 'NA' and new.name == 'From the game'
    assert open(os.path.join(new.path, 'ICON0.PNG'), 'rb').read() == b'\x89PNG icon of the disc'
    sfo = Sfo.load(os.path.join(new.path, 'PARAM.SFO'))
    assert sfo.get('TITLE') == savedata.TITLES['BLUS31540'] and sfo.get('SAVEDATA_DIRECTORY') == new.folder
    again = savedata.install(r.savedata, slot, base_bytes, 'Again')      # from now on, from that save
    assert again.folder == 'BLUS315400201'


def test_a_roster_saves_param_sfo_can_be_made_from_scratch(base_dir):
    with open(os.path.join(base_dir, 'PARAM.SFO'), 'rb') as f:
        theirs = f.read()
    sfo = Sfo(theirs)
    mine = savedata.roster_sfo('BLES02153', sfo.get('SAVEDATA_DIRECTORY'), sfo.get('SUB_TITLE')).to_bytes()
    assert mine == theirs


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


def test_rosters_carry_their_version_of_the_game(rpcs3):
    sd, _ = savedata.find_savedata(str(rpcs3))
    slot = savedata.list_rosters(sd)[0]
    assert slot.region == 'EU' and 'EU' in slot.label()
    assert savedata.region('BLUS31540') == 'NA' and savedata.region('BLES01853') == 'BLES01853'
    assert savedata.title_of('na') == 'BLUS31540' and savedata.title_of('XX') is None


def test_a_roster_can_be_saved_for_the_other_version(rpcs3, base_bytes):
    """Both versions read the same SYS-DATA: an EU roster saved for NA gets an NA folder and the NA
    title; once the NA version has a roster save, new NA saves are made from that one."""
    sd, _ = savedata.find_savedata(str(rpcs3))
    source = savedata.list_rosters(sd)[0]
    before = {f: open(os.path.join(source.path, f), 'rb').read() for f in savedata.FILES}
    profile = os.path.join(sd, 'BLUS315400000')          # the NA game was started once: its profile save
    os.makedirs(profile)
    sfo = Sfo.load(os.path.join(source.path, 'PARAM.SFO'))
    sfo.set_str('TITLE', 'NHL® Legacy Edition (from its own save)')
    sfo.save(os.path.join(profile, 'PARAM.SFO'))
    na = savedata.install(sd, source, base_bytes, 'Both', title_id='BLUS31540')
    assert (na.folder, na.region, na.name) == ('BLUS315400200', 'NA', 'Both')
    got = Sfo.load(os.path.join(na.path, 'PARAM.SFO'))
    assert got.get('TITLE') == 'NHL® Legacy Edition (from its own save)' and got.get('SAVEDATA_DIRECTORY') == na.folder
    assert open(na.sys_data, 'rb').read() == base_bytes
    shutil.rmtree(profile)
    again = savedata.install(sd, source, base_bytes, 'Again', title_id='BLUS31540')
    assert again.folder == 'BLUS315400201'
    assert Sfo.load(os.path.join(again.path, 'PARAM.SFO')).get('TITLE') == got.get('TITLE')   # from the NA roster
    eu = savedata.install(sd, source, base_bytes, 'EU too')
    assert eu.folder == 'BLES021530203' and Sfo.load(os.path.join(eu.path, 'PARAM.SFO')).get('TITLE') == sfo_title(source)
    assert {f: open(os.path.join(source.path, f), 'rb').read() for f in savedata.FILES} == before


def sfo_title(slot):
    return Sfo.load(os.path.join(slot.path, 'PARAM.SFO')).get('TITLE')


def test_a_version_without_a_save_of_its_own_gets_its_standard_title(rpcs3, base_bytes):
    sd, _ = savedata.find_savedata(str(rpcs3))
    source = savedata.list_rosters(sd)[0]
    na = savedata.install(sd, source, base_bytes, 'NA', title_id='BLUS31540')
    assert Sfo.load(os.path.join(na.path, 'PARAM.SFO')).get('TITLE') == savedata.TITLES['BLUS31540']


def test_the_versions_rpcs3_has(rpcs3, tmp_path):
    (rpcs3 / 'rpcs3.exe').write_bytes(b'MZ')
    r = savedata.find_rpcs3(str(rpcs3))
    assert r.games() == ['BLES02153']                     # an EU save only
    disc = tmp_path / 'NHL Legacy (USA).iso'
    disc.write_bytes(b'')
    (rpcs3 / 'config').mkdir()
    (rpcs3 / 'config' / 'games.yml').write_text(f'BLUS31540: "{disc.as_posix()}"\n', encoding='utf-8')
    assert r.games() == ['BLES02153', 'BLUS31540']        # the NA game is in RPCS3's list


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


def test_on_linux_and_macs_rpcs3s_data_folder_is_found(rpcs3, tmp_path, monkeypatch):
    """Linux and Mac: RPCS3 keeps its data in a folder of its own (~/.config/rpcs3,
    ~/Library/Application Support/rpcs3), away from the program (an AppImage, RPCS3.app)."""
    monkeypatch.setattr(savedata, 'WINDOWS', False)
    monkeypatch.setattr(savedata, 'data_folders', lambda: [str(rpcs3)])
    sd = str(rpcs3 / 'dev_hdd0' / 'home' / '00000001' / 'savedata')
    image = tmp_path / 'apps' / 'rpcs3-v0.0.43-linux64.AppImage'
    image.parent.mkdir()
    image.write_bytes(b'\x7fELF')
    mac_app = tmp_path / 'Applications' / 'RPCS3.app'
    (mac_app / 'Contents' / 'MacOS').mkdir(parents=True)
    for program in (image, mac_app):
        found = savedata.find_rpcs3(str(program))
        assert (found.exe, found.folder, found.savedata, found.where) == (str(program), str(rpcs3), sd, str(program))
    for pointed_at in (rpcs3, rpcs3 / 'dev_hdd0' / 'home'):    # the data folder itself, or a folder inside it
        found = savedata.find_rpcs3(str(pointed_at))
        assert (found.exe, found.where, found.savedata) == (None, str(rpcs3), sd)
    assert savedata.default_rpcs3() == str(rpcs3)


def test_a_running_rpcs3_is_seen_on_linux(tmp_path):
    for pid, cmd in (('12', b'/usr/bin/bash\0'), ('40', b'/tmp/.mount_rpcs3Xy/usr/bin/rpcs3\0--no-gui\0'),
                     ('self', b'x\0')):
        (tmp_path / pid).mkdir()
        (tmp_path / pid / 'cmdline').write_bytes(cmd)
    assert savedata._running_posix(str(tmp_path)) == '/tmp/.mount_rpcs3Xy/usr/bin/rpcs3'
    (tmp_path / '40' / 'cmdline').write_bytes(b'/usr/bin/vim\0')
    assert savedata._running_posix(str(tmp_path)) is None


def test_the_programs_own_folder_follows_the_system(monkeypatch, tmp_path):
    from legacy_roster import datasource
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'share'))
    home = datasource.data_home()
    assert home in (str(tmp_path), str(tmp_path / 'share')) or home.endswith(os.path.join('Library', 'Application Support'))


def test_roster_saves_work_without_rpcs3(rpcs3, tmp_path):
    """Testers, 0.8.0: the program in CrossOver on a Mac, RPCS3 the Mac one: no rpcs3.exe to pick. A
    folder with roster saves, or one roster save, will do; the game's own roster and photos need RPCS3."""
    copied = tmp_path / 'copied saves'
    shutil.copytree(rpcs3 / 'dev_hdd0' / 'home' / '00000001' / 'savedata', copied)
    with pytest.raises(savedata.Rpcs3Error):
        savedata.find_rpcs3(str(copied))
    found, picked = savedata.open_saves(str(copied))
    assert (found.savedata, found.where, found.plain, picked) == (str(copied), str(copied), True, None)
    assert found.games() == ['BLES02153'] and found.disc_slots() == [] and found.game_folder('BLES02153') is None
    assert [s.folder for s in savedata.list_rosters(found.savedata)] == ['BLES021530202']
    found, picked = savedata.open_saves(str(copied / 'BLES021530202'))
    assert (found.savedata, picked) == (str(copied), 'BLES021530202')
    with pytest.raises(FileNotFoundError):
        savedata.open_saves(str(tmp_path / 'nothing here'))
