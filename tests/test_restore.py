"""Putting the game's own rosters and calendar back (restore.py, pipeline.update(restore_parts=...))."""
import os
import shutil

import pytest

from legacy_roster import pipeline, restore, savedata
from legacy_roster.roster import Roster


@pytest.fixture
def save_folder(tmp_path, base_dir, monkeypatch):
    """A pretend save folder with the base roster; the program's own files in a temp folder, RPCS3 closed."""
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'local'))
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    folder = tmp_path / 'savedata'
    shutil.copytree(base_dir, folder / 'BLES021530202')
    return str(folder)


@pytest.fixture
def default(tmp_path, base_dir):
    """The game's own roster as a slot: here the base roster in a folder of its own (it is only read)."""
    folder = tmp_path / 'clean' / 'BLES021530200'
    shutil.copytree(base_dir, folder)
    return savedata.Slot(str(folder))


def sysdata(save_folder):
    return open(os.path.join(save_folder, 'BLES021530202', 'SYS-DATA'), 'rb').read()


def tables(raw, *tags):
    R = Roster(raw)
    return {t: [R.f[t].record_bytes(i) for i in range(R.f[t].cur_rec)] for t in tags}


def test_the_game_calendar_is_put_back_and_the_rest_stays_updated(save_folder, base_bytes, data, pack, default, tmp_path,
                                                                  monkeypatch):
    monkeypatch.setattr(data, 'schedule', pack['schedule'])
    steps = list(pipeline.CORE_STEPS) + [pipeline.SCHEDULE]
    first = pipeline.update(save_folder, 'BLES021530202', steps, None, data=data, in_place=True,
                            backup_root=str(tmp_path / 'b'))
    assert first.build.ok and first.build.builder.calendar, "the pack has a calendar to put in"
    assert tables(first.build.data, 'ihmS') != tables(base_bytes, 'ihmS')
    res = pipeline.update(save_folder, 'BLES021530202', steps, None, data=data, in_place=True,
                          backup_root=str(tmp_path / 'b'), restore_parts={restore.CALENDAR}, default=default)
    assert res.build.ok, res.build.problems
    assert tables(res.build.data, 'ihmS', 'Iwiq') == tables(base_bytes, 'ihmS', 'Iwiq')
    assert res.restored == ["The calendar is the game's own."]
    assert res.build.data == sysdata(save_folder)
    assert Roster(res.build.data).U.cur_rec == Roster(first.build.data).U.cur_rec     # the players stay as updated


def test_the_game_roster_is_written_as_it_is_when_nothing_is_left_to_update(save_folder, base_bytes, data, default, tmp_path):
    steps = list(pipeline.CORE_STEPS)
    pipeline.update(save_folder, 'BLES021530202', steps, None, data=data, in_place=True, backup_root=str(tmp_path / 'b'))
    assert sysdata(save_folder) != base_bytes
    res = pipeline.update(save_folder, 'BLES021530202', [], None, data=data, in_place=True,
                          backup_root=str(tmp_path / 'b'), restore_parts={restore.ROSTERS, restore.CALENDAR},
                          default=default)
    assert res.slot.folder == 'BLES021530202'
    assert sysdata(save_folder) == base_bytes == open(default.sys_data, 'rb').read()
    assert os.path.exists(res.report_path)


def test_a_restore_can_save_as_a_new_roster_and_never_touches_the_default(save_folder, base_bytes, data, default):
    before = open(default.sys_data, 'rb').read()
    res = pipeline.update(save_folder, 'BLES021530202', [], None, data=data, restore_parts={restore.ROSTERS},
                          default=default)
    assert not res.in_place and res.slot.folder != 'BLES021530202'
    assert open(res.slot.sys_data, 'rb').read() == before
    assert open(default.sys_data, 'rb').read() == before


def test_a_restore_refuses_without_a_default_and_while_rpcs3_runs(save_folder, data, default, monkeypatch):
    with pytest.raises(FileNotFoundError, match="game's own roster"):
        pipeline.update(save_folder, 'BLES021530202', [], None, data=data, restore_parts={restore.ROSTERS})
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: 'rpcs3.exe')
    with pytest.raises(savedata.InPlaceError, match="Close RPCS3"):
        pipeline.update(save_folder, 'BLES021530202', [], None, data=data, restore_parts={restore.PICTURES},
                        default=default)


def test_the_default_is_a_clean_roster_save_else_the_disc(save_folder, base_dir):
    class Fake:
        savedata = save_folder

        def disc_slots(self):
            return [savedata.DiscSlot('BLES02153', 'x.iso')]
    # the base roster is a community roster, so it is not the game's own: the disc is
    found = restore.default_slot(Fake(), 'BLES02153')
    assert getattr(found, 'disc', False)
    assert restore.default_slot(Fake(), 'BLUS31540') is None
