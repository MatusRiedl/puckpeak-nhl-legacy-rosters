"""Export files to a folder (export.py): the update's files made into a folder laid out like RPCS3's, for a player who
cannot let the program write into RPCS3 (Linux, a Mac, another PC) or wants to look first. Nothing else is written."""
import os
import shutil

import pytest

from legacy_roster import datasource, export, gamepatch, patchinstall, pipeline, savedata
from legacy_roster.art import pressstart
from legacy_roster.roster import Roster
from legacy_roster.sfo import Sfo

EU = 'BLES02153'
STEPS = list(pipeline.CORE_STEPS)


@pytest.fixture(autouse=True)
def _quiet_rpcs3(monkeypatch):
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)


def _files(root):
    return sorted(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, '/')
                  for dp, _d, fs in os.walk(root) for f in fs)


def _snapshot(*roots, skip=()):
    seen = {}
    for root in roots:
        for dp, dns, fs in os.walk(root):
            dns[:] = [d for d in dns if os.path.join(dp, d) not in skip]
            for f in fs:
                path = os.path.join(dp, f)
                with open(path, 'rb') as h:
                    seen[path] = h.read()
    return seen


def _rpcs3(tmp_path, base_dir, numbers=('02',), disc=None):
    """The player's own RPCS3 with roster saves (copies of the base roster) in its savedata folder."""
    root = tmp_path / 'rpcs3'
    folder = root / 'dev_hdd0' / 'home' / '00000001' / 'savedata'
    for n in numbers:
        shutil.copytree(base_dir, str(folder / f'{EU}02{n}'))
    (root / 'rpcs3.exe').parent.mkdir(parents=True, exist_ok=True)
    return savedata.Rpcs3(str(root / 'rpcs3.exe'), str(folder), '00000001', games={EU: disc} if disc else None)


def test_a_roster_file_becomes_a_folder_laid_out_like_rpcs3_and_nothing_else_is_written(tmp_path, base_dir, data):
    source = os.path.join(base_dir, 'SYS-DATA')
    app = datasource.app_dir()
    before = _snapshot(app, skip=(os.path.join(app, 'reports'),))
    res = export.run(str(tmp_path / 'out'), source, steps=STEPS, name='My roster', data=data, system='Linux')
    assert res.folder and os.path.dirname(res.folder) == str(tmp_path / 'out') and res.update.build.ok
    folder = f"{EU}0201"
    assert res.rosters == [(folder, 'EU', 'My roster')] and res.top == ['dev_hdd0']
    assert _files(res.folder) == sorted([export.HOW_TO] + [f'dev_hdd0/home/00000001/savedata/{folder}/{n}'
                                                           for n in ('ICON0.PNG', 'PARAM.SFO', 'SYS-DATA')])
    new = os.path.join(res.folder, 'dev_hdd0', 'home', '00000001', 'savedata', folder)
    with open(os.path.join(new, 'SYS-DATA'), 'rb') as f:
        made = f.read()
    with open(source, 'rb') as f:
        assert made == pipeline.build(f.read(), data, STEPS).data                 # what an update makes, and it was checked
    sfo = Sfo.load(os.path.join(new, 'PARAM.SFO'))
    assert sfo.get('SAVEDATA_DIRECTORY') == folder and sfo.get('SUB_TITLE') == 'My roster'
    assert 'config/patch_config.yml' not in _files(res.folder) and not os.path.exists(os.path.join(res.folder, export.WORK))
    assert _snapshot(app, skip=(os.path.join(app, 'reports'),)) == before         # the program's own lists are untouched
    with open(os.path.join(res.folder, export.HOW_TO), encoding='utf-8') as f:
        assert f.read() == res.text


def test_a_second_export_of_the_same_roster_is_byte_identical(tmp_path, base_dir, data):
    source = os.path.join(base_dir, 'SYS-DATA')
    one = export.run(str(tmp_path / 'a'), source, steps=STEPS, name='Same', data=data, system='Windows')
    two = export.run(str(tmp_path / 'b'), source, steps=STEPS, name='Same', data=data, system='Windows')
    assert one.files == two.files and one.text == two.text
    for rel in one.files:
        with open(os.path.join(one.folder, rel), 'rb') as f1, open(os.path.join(two.folder, rel), 'rb') as f2:
            assert f1.read() == f2.read(), rel


def test_a_roster_of_rpcs3_is_exported_under_a_free_name_and_rpcs3_is_not_touched(tmp_path, base_dir, data):
    rpcs3 = _rpcs3(tmp_path, base_dir, numbers=('01', '02'))
    slot = next(s for s in savedata.list_rosters(rpcs3.savedata) if s.folder.endswith('02'))
    before = _snapshot(str(tmp_path / 'rpcs3'))
    res = export.run(str(tmp_path / 'out'), slot, rpcs3=rpcs3, steps=STEPS, name='Free', data=data)
    assert res.rosters == [(f'{EU}0203', 'EU', 'Free')]                         # 01 and 02 are used in the player's save folder
    assert _snapshot(str(tmp_path / 'rpcs3')) == before
    assert res.update.build.ok and os.path.isdir(os.path.join(res.folder, 'dev_hdd0', 'home', '00000001', 'savedata', f'{EU}0203'))


def test_the_roster_that_fails_its_checks_leaves_no_folder(tmp_path, base_dir, data, monkeypatch):
    real = pipeline.build

    def broken(*a, **kw):
        out = real(*a, **kw)
        out.problems.append("a pretend problem")
        return out
    monkeypatch.setattr(pipeline, 'build', broken)
    res = export.run(str(tmp_path / 'out'), os.path.join(base_dir, 'SYS-DATA'), steps=STEPS, data=data)
    assert res.folder is None and not res.update.build.ok
    assert not os.path.exists(str(tmp_path / 'out')) or not os.listdir(str(tmp_path / 'out'))


def test_a_file_that_is_no_roster_or_a_missing_game_is_told_in_plain_words(tmp_path, base_dir, data):
    bad = tmp_path / 'SYS-DATA'
    bad.write_bytes(b'not a roster')
    with pytest.raises(export.ExportError, match="not a roster"):
        export.run(str(tmp_path / 'out'), str(bad), steps=STEPS, data=data)
    with pytest.raises(export.ExportError, match="Pick your copy of the game"):
        export.run(str(tmp_path / 'out'), os.path.join(base_dir, 'SYS-DATA'), steps=STEPS, data=data, photos=True)
    with pytest.raises(export.ExportError, match="Pick your copy of the game"):
        export.run(str(tmp_path / 'out'), os.path.join(base_dir, 'SYS-DATA'), steps=STEPS, data=data, game_patch=True)
    assert not os.path.exists(str(tmp_path / 'out')) or not os.listdir(str(tmp_path / 'out'))      # no half-made folder


def test_the_game_patch_goes_into_the_folder_without_touching_the_patch_config(tmp_path, base_dir, data, pack, monkeypatch):
    import copy
    made = copy.copy(data)
    made.schedule, made.leagues = pack['schedule'], {'ahl': pack['leagues']['ahl']}
    monkeypatch.setattr(patchinstall, 'db_files', lambda disc, roster: (b'META', b'DB'))
    monkeypatch.setattr(patchinstall, 'NO_PRESS', True)
    monkeypatch.setattr(pressstart, 'skip_files', lambda disc: {pressstart.REL: b'NO PRESS'})
    disc = tmp_path / 'game'
    disc.mkdir()
    res = export.run(str(tmp_path / 'out'), os.path.join(base_dir, 'SYS-DATA'), steps=STEPS, name='Patched', data=made,
                     game_patch=True, games={EU: str(disc)}, system='Mac')
    assert res.update.build.ok, res.update.build.problems[:5]
    files = _files(res.folder)
    assert f'patches/{EU}_patch.yml' in files and 'config/patch_config.yml' not in files
    assert [f for f in files if f.startswith(f'dev_hdd0/game/{EU}/USRDIR/')], files          # the db files and the title screen
    assert res.top == ['dev_hdd0', 'patches'] and [r['head'] for r in res.rows] == ['dev_hdd0', 'patches']
    assert res.entries == export.entry_names(True, False) and all(name in res.text for name in res.entries)
    assert gamepatch.is_patch_roster(Roster(open(os.path.join(res.folder, 'dev_hdd0', 'home', '00000001', 'savedata',
                                                              f'{EU}0201', 'SYS-DATA'), 'rb').read()))
    with open(os.path.join(res.folder, 'patches', f'{EU}_patch.yml'), encoding='utf-8') as f:
        assert f.read() == gamepatch.player_patch_text()


def test_the_words_name_every_folder_that_exists_and_none_that_does_not_and_every_system():
    parts = ['dev_hdd0/home', 'dev_hdd0/game', 'patches']
    entries = export.entry_names(True, False)
    for system, first in (('Windows', 'Windows:'), ('Linux', 'Linux:'), ('Mac', 'Mac:')):
        intro, rows, after = export.instructions(parts, [(f'{EU}0201', 'EU', 'x')], entries, [], system=system)
        assert [r['head'] for r in rows] == ['dev_hdd0', 'patches']
        text = "\n".join(r['text'] for r in rows)
        assert text.index(first) == min(text.index(w) for w in ('Windows:', 'Linux:', 'Mac:') if w in text), system
        for word in ('rpcs3.exe', '~/.config/rpcs3', '.var/app/net.rpcs3.RPCS3', 'Application Support/rpcs3'):
            assert word in text
        assert any('Manage > Game Patches' in line for line in after) and any('Customize > Save/Load/Delete' in line for line in after)
        assert any('delete the files you copied' in line for line in after)
    _intro, rows, after = export.instructions(['dev_hdd0/home'], [(f'{EU}0201', 'EU', 'x')], [], ['EU'])
    assert [r['head'] for r in rows] == ['dev_hdd0'] and 'patches' not in rows[0]['text'] + "\n".join(after)
    assert 'already lists 10 rosters' in rows[0]['text'] and not any('Game Patches' in line for line in after)
    assert export.TITLE in export.how_to_text(_intro, rows, after)


@pytest.mark.skipif(not os.environ.get('LEGACY_ROSTER_DISC'), reason="needs the game disc (LEGACY_ROSTER_DISC)")
def test_the_games_own_roster_is_exported_with_the_patch_from_the_disc(tmp_path, data, pack):
    import copy
    made = copy.copy(data)
    made.schedule, made.leagues = pack['schedule'], {'ahl': pack['leagues']['ahl']}
    disc = os.environ['LEGACY_ROSTER_DISC']
    slot = savedata.DiscSlot(EU, disc)
    res = export.run(str(tmp_path / 'out'), slot, steps=STEPS, name='Own', data=made, game_patch=True, games={EU: disc})
    assert res.update.build.ok and res.folder, res.update.build.problems[:5]
    files = _files(res.folder)
    assert f'dev_hdd0/game/{EU}/USRDIR/db/nhlng.db' in files and f'patches/{EU}_patch.yml' in files
    assert os.path.getsize(os.path.join(res.folder, 'dev_hdd0', 'game', EU, 'USRDIR', 'db', 'nhlng.db')) > 1000


def test_the_command_line_exports_a_roster_file_and_prints_the_words(tmp_path, base_dir, capsys, monkeypatch):
    from legacy_roster import cli
    monkeypatch.setattr(cli, '_download_packs', lambda: None)
    cli.main(['export-files', '--source', os.path.join(base_dir, 'SYS-DATA'), '--out', str(tmp_path / 'o'),
              '--leagues', 'nhl', '--offline'])
    said = capsys.readouterr().out
    assert 'Your files are ready' in said and 'Nothing in RPCS3 was changed' in said
    (folder,) = os.listdir(tmp_path / 'o')
    assert os.path.isfile(tmp_path / 'o' / folder / export.HOW_TO)
    with pytest.raises(SystemExit):                 # nothing to start from
        cli.main(['export-files', '--out', str(tmp_path / 'o2')])
