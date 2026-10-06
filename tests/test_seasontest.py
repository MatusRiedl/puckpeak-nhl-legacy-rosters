"""The Season mode test ladder (seasontest.py): LAB rosters with more and more update steps."""
import shutil

import pytest

from legacy_roster import savedata, seasontest
from legacy_roster.roster import Roster


@pytest.fixture
def saves(tmp_path, base_dir, monkeypatch):
    """A pretend save folder with one roster save, and the program's own files in the temp folder."""
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'local'))
    monkeypatch.setenv('HOME', str(tmp_path))
    folder = tmp_path / 'savedata'
    shutil.copytree(base_dir, folder / 'BLES021530202')
    return str(folder)


def test_the_ladder_adds_steps_and_leaves_out_what_the_pack_lacks():
    ladder = seasontest.rungs({'nhl', 'ratings', 'national', 'liiga', 'chl'})
    assert [name for name, _ in ladder] == ["SEASON 1 core", "SEASON 2 europe", "SEASON 3 ahl", "SEASON 4 everything"]
    assert ladder[0][1] == ['nhl', 'ratings', 'national'] and ladder[1][1] == ['nhl', 'ratings', 'national', 'liiga']
    assert ladder[3][1][-1] == 'chl' and all(set(a) <= set(b) for (_, a), (_, b) in zip(ladder, ladder[1:]))


def test_counts_measure_what_season_mode_loads(base_bytes):
    c = seasontest.counts(base_bytes)
    R = Roster(base_bytes)
    assert c['players'] == R.P.cur_rec and c['free agents'] == R.Q.cur_rec and c['entries'] == R.U.cur_rec
    assert 0 < c['entries on clubs'] <= c['entries'] and c['players loaded'] >= c['free agents']
    assert seasontest.limits(dict(c, **{'entries on clubs': 6000, 'links': 7000, 'players loaded': 6001})) and \
        not seasontest.limits(dict(c, **{'entries on clubs': 5000, 'links': 5000, 'players loaded': 5000}))


def test_the_ladder_writes_new_saves_and_a_report_and_changes_nothing_else(saves, monkeypatch):
    monkeypatch.setattr(seasontest, 'rungs', lambda available: [("SEASON 1 core", ['nhl', 'ratings', 'national'])])
    source = savedata.list_rosters(saves)[0]
    before = open(source.sys_data, 'rb').read()
    said = []
    made = seasontest.season_test(saves, source, said.append)
    assert made[0].name == "SEASON 1 core" and made[0].folder == 'BLES021530203'
    assert [s.name for s in made[1:]] in (["SEASON 1c core new links"],
                                          ["SEASON 1b core no Drouin", "SEASON 1c core new links"])   # 1b when Drouin is listed
    assert open(source.sys_data, 'rb').read() == before                       # the roster it started from is untouched
    assert sorted(s.folder for s in savedata.list_rosters(saves)) == sorted(['BLES021530202'] + [s.folder for s in made])
    text = '\n'.join(said)
    assert 'Start:' in text and 'SEASON 1 core (BLES021530203)' in text and "over Season's table sizes" in text


def test_the_source_is_the_newest_roster_the_program_did_not_make(saves):
    source = savedata.list_rosters(saves)[0]
    made = savedata.install(saves, source, open(source.sys_data, 'rb').read(), '2026-10-06 12:00')
    slots = savedata.list_rosters(saves)
    assert made.tool_made and seasontest.pick_source(slots).folder == source.folder
    assert seasontest.pick_source(slots, made.folder).folder == made.folder


def test_trim_takes_junior_players_off_their_teams_and_nothing_else(base_bytes):
    before = seasontest.counts(base_bytes)
    data, taken = seasontest.trim(base_bytes, 2026, 7)
    after = seasontest.counts(data)
    assert 0 <= taken <= 7
    assert after['entries on clubs'] == before['entries on clubs'] - taken
    assert after['free agents'] == before['free agents'] and after['players'] == before['players']
