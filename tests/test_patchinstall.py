"""The game patch in RPCS3 (patchinstall.py): RPCS3's switches as text, the files in and out again, on a fake RPCS3."""
import copy
import os
from types import SimpleNamespace

import pytest

from legacy_roster import gamepatch, patchinstall, savedata
from legacy_roster import layout as L
from legacy_roster.art import crests, install

EU, NA = 'BLES02153', 'BLUS31540'
PLAYER, INTRO, LOGIN, NEWS = gamepatch.PLAYER_ENTRY, gamepatch.INTRO_ENTRY, gamepatch.LOGIN_ENTRY, gamepatch.NEWS_ENTRY

# RPCS3's own file: another game, a lab entry under our EU hash, no newline at the end (as RPCS3 writes it)
CONFIG = "\n".join([
    "PPU-77278384022bc218f3910e476676b080aed0acd6:",
    "  60 FPS:",
    "    NHL 14:",
    "      BLUS31154:",
    "        01.00:",
    "          Enabled: true",
    f"PPU-{gamepatch.EU_HASH}:",
    "  NHL Legacy year 2026 (test):",
    "    NHL Legacy:",
    "      BLES02153:",
    "        01.00:",
    "          Enabled: true"])


def _subsequence(small, big):
    it = iter(big)
    return all(line in it for line in small)


def test_only_our_lines_of_rpcs3s_switches_change_and_come_out_again():
    text = patchinstall.config_with(CONFIG, EU, {PLAYER, INTRO})
    text = patchinstall.config_with(text, NA, {PLAYER})
    assert patchinstall.ticked(text, EU) == {PLAYER, INTRO} and patchinstall.ticked(text, NA) == {PLAYER}
    assert patchinstall.ticked(CONFIG, EU) == set()                   # the lab's own entry is not one of ours
    assert _subsequence(CONFIG.splitlines(), text.splitlines()) and not text.endswith('\n')
    assert patchinstall.config_with(patchinstall.config_with(text, EU, {PLAYER, INTRO}), NA, {PLAYER}) == text
    fewer = patchinstall.config_with(text, EU, {PLAYER})               # the intro switched off: its lines go
    assert patchinstall.ticked(fewer, EU) == {PLAYER} and INTRO not in fewer
    out = patchinstall.config_with(patchinstall.config_with(text, EU, set()), NA, set())
    assert out == CONFIG                                               # byte for byte; the emptied NA block went too
    windows = CONFIG.replace("\n", "\r\n") + "\r\n"
    assert patchinstall.config_with(patchinstall.config_with(windows, EU, {PLAYER}), EU, set()) == windows
    assert patchinstall.config_with('', EU, set()) == ''
    made = patchinstall.config_with('', NA, {PLAYER, LOGIN})
    assert made.startswith(f"PPU-{gamepatch.NA_HASH}:\n  {PLAYER}:\n    NHL Legacy:\n      BLUS31540:\n        01.00:\n")
    assert patchinstall.ticked(made, NA) == {PLAYER, LOGIN}


def _fake_rpcs3(tmp_path):
    root = tmp_path / 'rpcs3'
    game = lambda title: str(root / 'dev_hdd0' / 'game' / title / 'USRDIR')
    return SimpleNamespace(folder=str(root), plain=False, dev_hdd0=str(root / 'dev_hdd0'), game_folder=game,
                           game_disc=lambda title: 'disc.iso' if title == EU else None)


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def test_patch_this_game_and_unpatch_leave_rpcs3_as_it_was(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'local'))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    made = []
    monkeypatch.setattr(patchinstall, 'db_files', lambda disc, roster: made.append((disc, roster)) or (b'META', b'DB'))
    rpcs3 = _fake_rpcs3(tmp_path)
    config = os.path.join(rpcs3.folder, 'config', 'patch_config.yml')
    _write(config, CONFIG.encode())
    theirs = os.path.join(rpcs3.folder, 'patches', 'BLES02153_patch.yml')
    _write(theirs, b"Version: 1.2\n# someone's own patch\n")
    old_db = os.path.join(rpcs3.game_folder(EU), 'db', 'nhlng.db')
    _write(old_db, b'an older db')
    assert patchinstall.config_file(rpcs3) == config and not patchinstall.installed(rpcs3)

    assert patchinstall.install_patch(rpcs3, [NA, EU], b'roster', intro=True, login=False, say=lambda m: None) == [EU, NA]
    assert made == [('disc.iso', b'roster')]            # the EU disc makes NA's files too (the same files on both)
    for title in (EU, NA):
        assert patchinstall.state(rpcs3)[title] == {'patched': True, 'version': gamepatch.TEAMS_VERSION,
                                                     'intro': True, 'login': False, 'news': True,
                                                     'rights': None}   # a fake meta; the news always ticked
        assert _read(patchinstall.patch_file(rpcs3, title)) == gamepatch.player_patch_text([title]).encode()
        assert _read(os.path.join(rpcs3.game_folder(title), 'db', 'nhlng-meta.xml')) == b'META'
        assert _read(os.path.join(rpcs3.game_folder(title), 'db', 'nhlng.db')) == b'DB'
    assert patchinstall.installed(rpcs3)
    install.remove(say=lambda m: None)                  # "Restore the game's own pictures": the patch stays
    assert _read(old_db) == b'DB' and patchinstall.state(rpcs3)[EU]['patched']

    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: 'rpcs3.exe')
    with pytest.raises(patchinstall.PatchError, match="Close RPCS3"):
        patchinstall.remove(rpcs3, say=lambda m: None)
    with pytest.raises(patchinstall.PatchError, match="Close RPCS3"):
        patchinstall.install_patch(rpcs3, [EU], b'roster', say=lambda m: None)
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)

    patchinstall.remove(rpcs3, say=lambda m: None)
    assert _read(config) == CONFIG.encode()
    assert _read(theirs) == b"Version: 1.2\n# someone's own patch\n"            # the file that was there is back
    assert not os.path.exists(patchinstall.patch_file(rpcs3, NA))
    assert _read(old_db) == b'an older db'
    assert not os.path.exists(os.path.join(rpcs3.game_folder(EU), 'db', 'nhlng-meta.xml'))
    assert not os.path.exists(os.path.join(rpcs3.game_folder(NA), 'db'))        # folders we made are gone
    assert not patchinstall.installed(rpcs3)
    assert not any(t['patched'] for t in patchinstall.state(rpcs3).values())
    kept = os.listdir(os.path.join(str(tmp_path / 'local'), 'NHLLegacyRosterUpdater', 'patch', 'backup'))
    assert [n for n in kept if n.endswith('_patch_config.yml')]                  # RPCS3's own file, kept for good


def test_entries_of_our_names_that_were_ticked_before_come_back_where_they_were(tmp_path, monkeypatch):
    # the lab (or a player by hand) ticked patches named like our intro entries, between other entries
    entry = lambda name: [f"  {name}:", "    NHL Legacy:", "      BLUS31540:", "        01.00:", "          Enabled: true"]
    before = "\n".join([f"PPU-{gamepatch.NA_HASH}:", *entry("NHL Legacy year 2026 (test)"), *entry(INTRO),
                        *entry(LOGIN), *entry("ZamboniMultiplayerPatch")]) + "\n"
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'local'))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    monkeypatch.setattr(patchinstall, 'db_files', lambda disc, roster: (b'META', b'DB'))
    rpcs3 = _fake_rpcs3(tmp_path)
    config = os.path.join(rpcs3.folder, 'config', 'patch_config.yml')
    _write(config, before.encode())
    patchinstall.install_patch(rpcs3, [NA], b'roster', intro=True, login=False, say=lambda m: None)
    assert patchinstall.ticked(_read(config).decode(), NA) == {PLAYER, INTRO, NEWS}
    patchinstall.install_patch(rpcs3, [NA, EU], b'roster', intro=False, login=True, say=lambda m: None)   # again
    assert patchinstall.ticked(_read(config).decode(), NA) == {PLAYER, LOGIN, NEWS}
    patchinstall.remove(rpcs3, say=lambda m: None)
    assert _read(config) == before.encode()                 # as before our first change, byte for byte


def test_the_db_files_of_the_32_team_test_move_from_the_pictures_list(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'local'))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    rpcs3 = _fake_rpcs3(tmp_path)
    writer = install._Writer([rpcs3.game_folder(EU)])                # as team32-test wrote them before
    writer.write(gamepatch.DB_FILE, b'DB', 'db:1')
    writer.write(('fe', 'x.big'), b'PIC', 'pic')
    writer.save()
    assert patchinstall.installed(rpcs3)
    install.remove(say=lambda m: None)                                   # the picture goes, the db file stays
    assert not os.path.exists(os.path.join(rpcs3.game_folder(EU), 'fe', 'x.big'))
    assert _read(os.path.join(rpcs3.game_folder(EU), 'db', 'nhlng.db')) == b'DB'
    patchinstall.remove(rpcs3, say=lambda m: None)
    assert not os.path.exists(os.path.join(rpcs3.game_folder(EU), 'db', 'nhlng.db'))


def test_a_patch_needs_rpcs3_and_the_game(tmp_path, monkeypatch):
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    with pytest.raises(patchinstall.PatchError, match="needs RPCS3"):
        patchinstall.check(SimpleNamespace(plain=True), [EU])
    rpcs3 = _fake_rpcs3(tmp_path)
    rpcs3.game_disc = lambda title: None
    with pytest.raises(patchinstall.PatchError, match="where your copy of the game is"):
        patchinstall.check(rpcs3, [EU])


@pytest.fixture
def patch_data(data, pack):
    """The bundled pack with the calendar and the AHL, as the window gathers them for the game patch."""
    import copy
    made = copy.copy(data)
    made.schedule, made.leagues = pack['schedule'], {'ahl': pack['leagues']['ahl']}
    return made


def test_an_update_follows_rpcs3_a_patch_roster_while_patched_turned_back_after_unpatch(tmp_path, base_dir, patch_data,
                                                                                         monkeypatch):
    import shutil
    from legacy_roster import layout, pipeline, restore
    from legacy_roster.roster import Roster
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'local'))
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    monkeypatch.setattr(patchinstall, 'db_files', lambda disc, roster: (b'META', b'DB'))
    rpcs3 = _fake_rpcs3(tmp_path)
    folder = str(tmp_path / 'savedata')
    shutil.copytree(base_dir, os.path.join(folder, 'BLES021530202'))
    shutil.copytree(base_dir, str(tmp_path / 'clean' / 'BLES021530200'))
    default = savedata.Slot(str(tmp_path / 'clean' / 'BLES021530200'))
    original = Roster(open(os.path.join(base_dir, 'SYS-DATA'), 'rb').read())
    steps = list(pipeline.CORE_STEPS)
    run = lambda **kw: pipeline.update(folder, 'BLES021530202', steps, None, data=patch_data, in_place=True,
                                       backup_root=str(tmp_path / 'b'), rpcs3=rpcs3, **kw)

    plain = run()                                                       # not patched: a normal roster, as before
    assert plain.build.ok and plain.patch is None and not gamepatch.is_patch_roster(Roster(plain.build.data))

    patchinstall.install_patch(rpcs3, [EU], roster=b'roster', intro=True)     # step 2's Patch
    first = run()
    assert first.build.ok, first.build.problems[:5]
    R = Roster(first.build.data)
    assert gamepatch.is_patch_roster(R) and gamepatch.check_years(R, patch_data.season_year) == []
    assert gamepatch.check_games(R) == [] and gamepatch.check_future(R) == [] and gamepatch.check_all_star(R) == []
    assert first.patch == [EU] and first.db_note is None
    assert first.patch_lines()[0].startswith("Made for the patched game") and 'Photos, logos' in first.patch_lines()[1]

    again = run()                                                       # the patch roster updated again: the same bytes
    assert again.build.ok and again.unchanged and again.build.data == first.build.data

    with pytest.raises(layout.LayoutError, match="Your EU game is patched for 32 teams, your NA game is not"):
        pipeline.update(folder, 'BLES021530202', steps, None, data=patch_data, rpcs3=rpcs3, targets=[EU, NA])

    patchinstall.remove(rpcs3)                                          # Unpatch: the next update turns it back
    back = run(default=default)
    assert back.build.ok and back.build.turned_back and back.patch is None, back.build.problems[:5]
    B = Roster(back.build.data)
    assert not gamepatch.is_patch_roster(B) and B.f.section_size == original.f.section_size
    assert all(B.f[t].max_rec == original.f[t].max_rec for t in gamepatch.CALENDAR_TABLES)
    for slot, fields in gamepatch.PATCHED_TEAM_FIELDS.items():                # the game's own team fields back
        assert [B.T.get(slot, f) for f in fields] == [original.T.get(slot, f) for f in fields], slot
    assert B.T.get(30, 'nnsx') == original.T.get(30, 'nnsx') != 'SEA'       # also Seattle's name (lab round 36)
    assert "unpatched game" in back.patch_lines()[0]
    normal = run(default=default)                                       # and stays a normal roster, byte for byte
    assert normal.unchanged and not normal.build.turned_back and normal.build.data == back.build.data

    patchinstall.install_patch(rpcs3, [EU], roster=b'roster')
    assert run().patch == [EU]
    back = pipeline.update(folder, 'BLES021530202', [], None, data=patch_data, in_place=True,
                           backup_root=str(tmp_path / 'b'), rpcs3=rpcs3, default=default,
                           restore_parts={restore.ROSTERS, restore.PATCH})          # Restore default: unpatched too
    assert back.slot is not None and "The game patch is out: the game is as it was." in back.restored
    assert not patchinstall.installed(rpcs3) and not gamepatch.is_patch_roster(Roster(open(back.slot.sys_data, 'rb').read()))


def test_the_two_small_switches_change_only_patched_versions(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'local'))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    monkeypatch.setattr(patchinstall, 'db_files', lambda disc, roster: (b'META', b'DB'))
    rpcs3 = _fake_rpcs3(tmp_path)
    assert patchinstall.patched_titles(rpcs3) == [] and patchinstall.set_switches(rpcs3, [EU, NA], True, True) == []
    patchinstall.install_patch(rpcs3, [EU], b'roster', intro=True, login=False, say=lambda m: None)
    assert patchinstall.patched_titles(rpcs3) == [EU]
    assert patchinstall.set_switches(rpcs3, [EU, NA], False, True) == [EU]
    st = patchinstall.state(rpcs3)
    assert (st[EU]['patched'], st[EU]['intro'], st[EU]['login'], st[EU]['news']) == (True, False, True, True)
    assert not st[NA]['login'] and not st[NA]['news']
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: 'rpcs3.exe')
    with pytest.raises(patchinstall.PatchError, match="Close RPCS3 first"):
        patchinstall.set_switches(rpcs3, [EU], True, False)


@pytest.mark.skipif(not os.environ.get('LEGACY_ROSTER_DISC'), reason="needs the game disc (LEGACY_ROSTER_DISC)")
def test_the_games_own_roster_made_for_the_patch_fills_coachella_and_henderson_and_turns_back(patch_data, pack):
    from legacy_roster import contracts, pipeline, schedule, stock
    from legacy_roster.roster import Roster
    disc = os.environ['LEGACY_ROSTER_DISC']
    src = stock.from_disc(disc)
    steps = list(pipeline.CORE_STEPS) + [pipeline.SCHEDULE, 'ahl']
    data = copy.copy(patch_data)
    data.calendar = schedule.ALL_PATCH

    def patch_build(raw):
        res = pipeline.build(raw, data, steps, game_patch=True)
        assert res.ok, res.problems[:5]
        out, problems, _ = pipeline.patch_roster(res, raw, pack, data.season_year)
        assert problems == []
        return out

    out = patch_build(src)
    R = Roster(out)
    assert gamepatch.is_patch_roster(R) and gamepatch.check_rights(R) == []
    assert contracts.ufa_problems(R) == []                     # UFA years on the league's clock, as the birth years
    for slot, name, art in ((234, "Coachella Valley", 20073), (235, "Henderson", 20081)):
        assert R.T.get(slot, 'NYKk') == 1 and name in R.team_name(slot)
        assert R.T.get(slot, 'artid') == art                    # not the switched-off custom teams' shared 20054
        assert crests.palette(R, slot) == L.OWN_KIT[slot][11, 1][:3]     # the crest's colours, also on the game's own
        assert {k: R.T.get(slot, k) for k in L.OWN_DESIGN[slot]} == L.OWN_DESIGN[slot]   # jerseystyle 0 -> 1 (round 46)
        assert sum(1 for x in R.team_roster(slot) if x[1] is not None) >= 20
    assert sum(1 for x in R.team_roster(31) if x[1] is not None) >= 20         # Vegas dresses 20
    assert sum(1 for x in R.team_roster(235) if x[1] is not None and R.P.get(x[1], 'WBbd') == 32) >= 9   # Henderson: Vegas's
    assert patch_build(out) == out                                                  # a second run: the same bytes
    meta, db = patchinstall.db_files(disc, patchinstall.calendar_roster(disc, pack))
    assert gamepatch.check_db(db, meta, R) == []                                     # Patch's db fits the roster

    data.calendar = schedule.THIRTY                                                 # unpatched: turned back
    own = Roster(src)
    back = pipeline.build(out, data, steps, normal_from=own)
    assert back.ok and back.turned_back, back.problems[:5]
    B = Roster(back.data)
    assert not gamepatch.is_patch_roster(B) and B.f.section_size == own.f.section_size
    assert contracts.ufa_problems(B) == []
    assert pipeline.build(back.data, data, steps, normal_from=own).data == back.data


def test_the_intro_skip_also_skips_press_start_and_unpatch_takes_it_out(tmp_path, monkeypatch):
    from legacy_roster.art import pressstart
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'local'))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    monkeypatch.setattr(patchinstall, 'db_files', lambda disc, roster: (b'META', b'DB'))
    monkeypatch.setattr(patchinstall, 'NO_PRESS', True)
    made = []
    monkeypatch.setattr(pressstart, 'skip_files', lambda disc: made.append(disc) or {pressstart.REL: b'NO PRESS'})
    rpcs3 = _fake_rpcs3(tmp_path)
    press = lambda title: os.path.join(rpcs3.game_folder(title), *pressstart.REL)
    _write(press(NA), b"a player's own title screen")
    patchinstall.install_patch(rpcs3, [EU, NA], b'roster', intro=True, login=False, say=lambda m: None)
    assert made == ['disc.iso'] and _read(press(EU)) == _read(press(NA)) == b'NO PRESS'
    patchinstall.install_patch(rpcs3, [EU, NA], b'roster', intro=True, login=False, say=lambda m: None)
    assert made == ['disc.iso']                                     # already in: not made again
    assert patchinstall.set_switches(rpcs3, [EU, NA], False, False) == [EU, NA]
    assert not os.path.exists(press(EU)) and _read(press(NA)) == b"a player's own title screen"
    patchinstall.set_switches(rpcs3, [EU, NA], True, False)
    assert _read(press(EU)) == b'NO PRESS' and len(made) == 2
    patchinstall.remove(rpcs3, say=lambda m: None)
    assert not os.path.exists(press(EU)) and _read(press(NA)) == b"a player's own title screen"
    monkeypatch.setattr(pressstart, 'skip_files', lambda disc: (_ for _ in ()).throw(ValueError("another disc")))
    said = []
    patchinstall.install_patch(rpcs3, [EU], b'roster', intro=True, login=False, say=said.append)
    assert not os.path.exists(press(EU)) and any('waits for Start' in m for m in said)
    monkeypatch.setattr(patchinstall, 'NO_PRESS', False)                # until the lab passed: never written
    patchinstall.remove(rpcs3, say=lambda m: None)
    patchinstall.install_patch(rpcs3, [EU], b'roster', intro=True, login=False, say=lambda m: None)
    assert not os.path.exists(press(EU))
