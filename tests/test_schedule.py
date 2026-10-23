"""The game's calendar (schedule.py): the real schedule of the season in the roster's schedule tables."""
import datetime
import os
import shutil

import pytest

from legacy_roster import calendartest, pipeline, savedata, schedule
from legacy_roster.builder import Data
from legacy_roster.roster import Roster
from legacy_roster.verify import verify


@pytest.fixture(scope='module')
def games(pack):
    assert pack.get('schedule'), "the data pack has no schedule (tools/build_datapack.py --refresh schedule)"
    return pack['schedule']


def counts(rows):
    total, home = {}, {}
    for _d, h, a in rows:
        total[h] = total.get(h, 0) + 1
        total[a] = total.get(a, 0) + 1
        home[h] = home.get(h, 0) + 1
    return total, home


def test_the_pack_has_the_real_season(games):
    assert len(games) == 1344 and games[0][0] == '2026-09-29' and games[-1][0] == '2027-04-10'
    total, home = counts(schedule.slot_games(games))
    assert set(total.values()) == {84} and set(home.values()) == {42} and len(total) == 32


def test_thirty_teams_leave_seattle_and_vegas_out(games):
    rows = schedule.rows_for(games, schedule.THIRTY)
    total, _ = counts(rows)
    assert len(rows) == 1180 and set(total) == set(range(30)) and 76 <= min(total.values()) and max(total.values()) <= 80
    assert [r[0] for r in rows] == sorted(r[0] for r in rows)                      # in date order
    star = schedule.rows_for(games, schedule.ALL_STAR)
    assert len(star) == 1181 and (star[[r[1:] for r in star].index((30, 31))][0]) == schedule.all_star_date(games)
    assert datetime.date.fromisoformat(schedule.all_star_date(games)).month == 2


def test_thirty_two_teams_get_the_same_number_of_home_and_away_games(games):
    rows = schedule.rows_for(games, schedule.ALL)
    total, home = counts(rows)
    assert len(rows) == 1280 and set(total.values()) == {80} and set(home.values()) == {40} and len(total) == 32
    assert rows == schedule.rows_for(games, schedule.ALL)                           # deterministic
    played = {}
    for date, h, a in rows:
        for t in (h, a):
            assert (date, t) not in played
            played[(date, t)] = 1


def test_the_game_patch_calendar_has_one_all_star_row_in_the_break(base_bytes, games):
    rows = schedule.rows_for(games, schedule.ALL_PATCH)
    own = [g for g in rows if g[1] == g[2]]
    assert rows == sorted(schedule.slot_games(games) + own, key=lambda g: g[0])          # every game of the real season
    assert len(rows) == schedule.PATCH_ROWS == 1345
    assert own == [(schedule.all_star_date(games), 0, 0)]                     # nobody plays in the break: Anaheim's row
    source = Roster(base_bytes)
    R = Roster(base_bytes)
    assert R.f[schedule.TABLE].max_rec == 1291
    info = schedule.apply(R, games, schedule.ALL_PATCH)
    assert 0 < min(info['per_team'].values()) == max(info['per_team'].values()) == 84        # the row is nobody's game
    assert R.f[schedule.TABLE].max_rec == 1345 and R.f[schedule.FAVOURITE].max_rec == 1431    # room the patch's meta gives
    again = Roster(R.f.build())
    assert schedule.apply(again, games, schedule.ALL_PATCH) == info and again.f.build() == R.f.build()   # rule 4
    assert schedule.check(R, source, info) == []
    assert schedule.check(R, source, dict(info, variant=schedule.ALL))[0] ==         f"schedule row {rows.index(own[0])}: 0 against 0"                     # only the patch's calendar may have it
    T, at = R.f[schedule.TABLE], rows.index(own[0])
    T.set(at, schedule.ROW['home'], 5)                                        # an ordinary game instead: per team wrong
    assert "the calendar has 0 All-Star rows" in schedule.check(R, source, info)


def test_the_calendar_is_written_into_the_tables_and_checked(base_bytes, games):
    R = Roster(base_bytes)
    source = Roster(base_bytes)
    for variant in schedule.VARIANTS:
        R = Roster(base_bytes)
        info = schedule.apply(R, games, variant)
        assert info['games'] == len(schedule.rows_for(games, variant)) and schedule.check(R, source, info) == []
        assert R.f[schedule.TABLE].cur_rec == R.f[schedule.FAVOURITE].cur_rec == info['games']
        first = schedule.read(R)[0]
        assert first[:2] == (8, 28)                                                    # 29 September: month 8, day 28
        assert schedule.read(R) == schedule.read(R, schedule.FAVOURITE)
    assert R.f['byED'].cur_rec == source.f['byED'].cur_rec                               # nhlfutureschedule untouched


def test_the_check_finds_what_the_game_cannot_use(base_bytes, games):
    R, source = Roster(base_bytes), Roster(base_bytes)
    info = schedule.apply(R, games, schedule.THIRTY)
    T = R.f[schedule.TABLE]
    T.set(1, schedule.ROW['home'], T.get(0, schedule.ROW['away']))                       # team 2 plays itself or twice
    T.set(1, schedule.ROW['month'], T.get(0, schedule.ROW['month']))
    T.set(1, schedule.ROW['day'], T.get(0, schedule.ROW['day']))
    T.set(1, schedule.ROW['away'], T.get(0, schedule.ROW['home']))
    problems = schedule.check(R, source, info)
    assert any("twice" in p for p in problems) and any("favoriteteamschedule" in p for p in problems)
    with pytest.raises(schedule.ScheduleError, match="do not fit"):
        schedule.apply(R, games + [['2027-04-11', 'ANA', 'EDM']] * 200, schedule.ALL_STAR)


def test_the_calendar_step_builds_a_roster_that_passes_and_builds_again_the_same(base_bytes, data, games):
    d = Data(nhl_players=data.nhl_players, ratings_list=data.ratings_list, iihf=data.iihf, season_year=data.season_year,
             nhl_last=data.nhl_last, drafts=data.drafts, schedule=games)
    steps = list(pipeline.CORE_STEPS) + [pipeline.SCHEDULE]
    res = pipeline.build(base_bytes, d, steps)
    assert res.ok, res.problems[:3]
    assert res.builder.calendar['games'] == 1180 and any(t == "Calendar" for t, _ in res.lines())
    again = pipeline.build(res.data, d, steps)
    assert again.ok and again.data == res.data                                          # rule 4
    plain = pipeline.build(base_bytes, d, pipeline.CORE_STEPS)
    assert Roster(plain.data).f[schedule.TABLE].cur_rec == 1231                          # without the step: untouched
    assert pipeline.SCHEDULE in pipeline.default_steps({'schedule': games})              # on by default (owner, 2026-10-06)
    assert pipeline.SCHEDULE not in pipeline.EXPERIMENTAL
    broken = Roster(res.data)
    broken.f[schedule.TABLE].cur_rec -= 1
    problems, _ = verify(broken.f.build(), Roster(base_bytes), calendar=res.builder.calendar)
    assert any("schedule" in p for p in problems)


def test_every_club_league_gets_its_real_season_in_its_own_table(base_bytes, pack):
    parts = schedule.league_schedules(pack)
    assert set(parts) == set(schedule.LEAGUES)                     # Norway has no table
    R = Roster(base_bytes)
    infos = {}
    for part, games in sorted(parts.items()):
        tag, slots = schedule.LEAGUES[part]
        rows = schedule.league_rows(games, set(slots))
        info = infos[part] = schedule.apply_league(R, part, games)
        assert info['games'] == len(rows) == R.f[tag].cur_rec <= R.f[tag].max_rec
        assert set(info['per_team']) == set(slots)                 # every club of the game plays
        assert schedule.check_league(R, part, info) == []
        day = datetime.date.fromisoformat(rows[0][0])
        assert schedule.read_league(R, part)[0] == (day.month - 1, day.day - 1, rows[0][1], rows[0][2])
        assert R.f[tag].get(0, schedule.ROW['home']) == list(slots).index(rows[0][1])     # a team = its place in the league
    for part in ('shl', 'del', 'extraliga'):                       # 14 clubs, all with a slot: the real 52 games each
        assert set(infos[part]['per_team'].values()) == {52}
    assert len(parts['liiga']) == 544 and infos['liiga']['games'] < 544      # Jokerit's / Jukurit's games left out
    again = Roster(R.f.build())
    for part, games in sorted(parts.items()):
        assert schedule.apply_league(again, part, games) == infos[part]
    assert again.f.build() == R.f.build()                          # rule 4
    # what the game cannot use
    T = R.f['LmeT']
    for field in ('month', 'day'):
        T.set(1, schedule.ROW[field], T.get(0, schedule.ROW[field]))
    T.set(1, schedule.ROW['home'], T.get(0, schedule.ROW['home']))
    assert any("twice" in p for p in schedule.check_league(R, 'shl', infos['shl']))
    T.set(2, schedule.ROW['month'], 6)                             # July
    assert any("the date 7/" in p for p in schedule.check_league(R, 'shl', infos['shl']))
    assert schedule.league_rows([['2026-10-01', 62, 63], ['2026-10-01', 63, 64], ['2026-07-30', 62, 64],
                                 ['2026-10-02', 62, 'Frisk Asker']], set(schedule.LEAGUES['shl'][1])) == \
        [('2026-10-01', 62, 63)]                                   # twice a day, July, a club without a slot
    with pytest.raises(schedule.ScheduleError, match="no games"):
        schedule.apply_league(R, 'nl', [['2026-10-01', 'HC Ajoie', 'SCRJ Lakers']])


def test_the_calendar_step_writes_the_calendars_of_the_leagues_it_updates(base_bytes, data, pack, games):
    d = Data(nhl_players=data.nhl_players, ratings_list=data.ratings_list, iihf=data.iihf, season_year=data.season_year,
             nhl_last=data.nhl_last, drafts=data.drafts, schedule=games, leagues={'shl': pack['leagues']['shl']},
             league_schedules=schedule.league_schedules(pack))
    steps = list(pipeline.CORE_STEPS) + ['shl', pipeline.SCHEDULE]
    res = pipeline.build(base_bytes, d, steps)
    assert res.ok, res.problems[:3]
    assert set(res.builder.league_calendars) == {'shl'}            # the other leagues were not updated: kept
    assert ("League calendars", "SHL 364 games") in res.lines()
    source, built = Roster(base_bytes), Roster(res.data)
    assert schedule.read(built, 'RBQQ') == schedule.read(source, 'RBQQ')
    assert schedule.read(built, 'LmeT') != schedule.read(source, 'LmeT')
    again = pipeline.build(res.data, d, steps)
    assert again.ok and again.data == res.data                     # rule 4
    assert 'league calendars' not in pipeline.EXPERIMENTAL          # played in the lab (round 46)
    # verify: a league table nobody wrote stays the source's
    broken = Roster(res.data)
    broken.f['RBQQ'].set(0, schedule.ROW['day'], 3)
    problems, _ = verify(broken.f.build(), source, calendar=res.builder.calendar,
                         league_calendars=res.builder.league_calendars)
    assert "schedule table RBQQ changed" in problems


def test_the_calendar_test_writes_new_rosters_and_a_list_of_what_to_look_at(tmp_path, base_dir, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'local'))
    monkeypatch.setenv('HOME', str(tmp_path))
    folder = str(tmp_path / 'savedata')
    shutil.copytree(base_dir, os.path.join(folder, 'BLES021530202'))
    slot = savedata.list_rosters(folder)[0]
    before = open(slot.sys_data, 'rb').read()
    said = []
    made = calendartest.calendar_test(folder, slot, said.append)
    assert [s.name for s in made] == [name for name, _v, _y in calendartest.RUNGS]
    assert open(slot.sys_data, 'rb').read() == before                                    # the roster it started from stays
    sizes = [len(schedule.read(Roster(open(s.sys_data, 'rb').read()))) for s in made]
    assert sizes == [1180, 1181, 1280, 1180]
    year = Roster(open(made[3].sys_data, 'rb').read()).f['vaHq']
    assert {year.get(i, 'dnFq') for i in range(year.cur_rec)} == {126, 127, 128, 129, 130, 131}   # 2015-2020 + 11
    text = chr(10).join(said)
    assert 'Anaheim:' in text and 'home vs' in text and 'CAL 3 all 32 teams 80 games' in text
