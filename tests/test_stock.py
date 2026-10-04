"""Starting from the game's own roster (stock.py): made from the player's disc, prepared, updated.

These need the game's disc (EA's data, never part of the project): set LEGACY_ROSTER_DISC to a disc
image or extracted game folder of NHL Legacy Edition (EU or NA), read only. Without it they skip."""
import os
from collections import Counter

import pytest

from legacy_roster import layout as L
from legacy_roster import pipeline, stock, tdb
from legacy_roster.builder import Data
from legacy_roster.roster import Roster

DISC = os.environ.get('LEGACY_ROSTER_DISC')


@pytest.fixture(scope='module')
def stock_bytes():
    if not DISC or not os.path.exists(DISC):
        pytest.skip("no game disc (set LEGACY_ROSTER_DISC to your NHL Legacy disc image)")
    return stock.from_disc(DISC)


@pytest.fixture(scope='module')
def stock_built(stock_bytes, pack):
    data = Data(nhl_players=_nhl(pack), ea_ratings=pack['ea_ratings'], iihf=pack['iihf'], season_year=pack['season'],
                leagues=pack['leagues'], nhl_logos=pack.get('nhl_logos'))
    return pipeline.build(stock_bytes, data, pipeline.steps_for(pack)), data


def _nhl(pack):
    from legacy_roster import datasource
    return datasource.flatten_nhl(pack['nhl'])


def test_the_games_own_roster_becomes_a_roster_save(stock_bytes, base_bytes):
    assert len(stock_bytes) == stock.SAVE_SIZE and tdb.check_chain(stock_bytes) == []
    f, base = tdb.RosterFile(data=stock_bytes), tdb.RosterFile(data=base_bytes)
    assert f.order == base.order                                 # a roster save's tables, in its order
    for name in f.order:
        mine, theirs = f[name], base[name]
        assert (mine.max_rec, mine.rec_len, mine.field_defs) == (theirs.max_rec, theirs.rec_len, theirs.field_defs)
        assert mine.header[7] == theirs.header[7] and mine.header[0x1D] == theirs.header[0x1D]
        assert mine.tail == theirs.tail or name == f.order[-1]
    assert stock_bytes[:0x10] == base_bytes[:0x10] and f.db_trailer == base.db_trailer
    R = Roster(stock_bytes)
    assert L.check_base(R) == L.STOCK and R.T.cur_rec == L.TEAM_COUNT
    assert R.team_name(22).startswith('Arizona') and not R.T.get(222, 'active')


def test_preparing_makes_room_and_happens_once(stock_bytes):
    R = Roster(stock_bytes)
    players = R.P.cur_rec
    assert not stock.prepared(R)
    done = stock.prepare(R, 2026)
    assert done and stock.prepared(R)
    assert not [i for i in range(R.U.cur_rec) if R.U.get(i, 'team') in stock.ALL_STAR]
    spare = [i for i in range(R.P.cur_rec) if R.P.get(i, 'lastname') == 'ZZ']
    assert len(spare) == R.P.cur_rec - players and R.P.cur_rec <= stock.MOST_PLAYERS
    assert len({R.P.get(i, 'game_id') for i in range(R.P.cur_rec)}) == R.P.cur_rec      # ids stay unique
    assert Counter(R.P.get(i, 'position') for i in spare)[4] > 50
    assert stock.prepare(R, 2026) == []


def test_the_games_own_roster_is_updated_and_a_second_run_changes_nothing(stock_built, stock_bytes):
    res, data = stock_built
    assert res.problems == []
    R = Roster(res.data)
    assert L.check_base(R) == L.STOCK
    for t in list(range(32)) + list(range(133, 154)):
        assert res.info['teams'][t]['dressed'] == 20, R.team_name(t)
    for m in L.MIRROR_OF:                                        # no custom copies (owner, 2026-10-04)
        assert res.info['teams'][m]['players'] == 0
    assert not any(r[1] == 'skipped' for r in res.log)          # 2014's retired players make the room
    assert R.Q.cur_rec < R.Q.max_rec and R.C.cur_rec < R.C.max_rec * 0.8
    again = pipeline.build(res.data, data, pipeline.steps_for({'leagues': data.leagues}))
    assert again.problems == [] and again.data == res.data


def test_clubs_in_switched_off_custom_slots_are_left_out(stock_bytes, pack):
    R = Roster(stock_bytes)
    ahl = pipeline.usable_clubs(R, pack['leagues']['ahl'])
    assert not {234, 235} & {t['slot'] for t in ahl['teams']}
    assert {'Coachella Valley Firebirds', 'Henderson Silver Knights'} <= set(ahl['left_out'])
