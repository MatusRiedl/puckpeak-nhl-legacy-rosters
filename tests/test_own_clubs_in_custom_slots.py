"""The game's own roster with clubs of the player's own in the custom slots (a tester filled 222-227 with KHL clubs in the
game): those slots are clubs there, not the community roster's copies of NHL teams, and the spare records are never
copies of a player whose type is not his position's. Before, an update of that roster was refused: "Reilly Walsh is on
two club teams" (the builder sent him from Barys to Montreal's farm club) and "David ZZ has player type 4, which no
forward has". The disc test needs LEGACY_ROSTER_DISC (see test_stock.py)."""
import os

import pytest

from legacy_roster import builder as B
from legacy_roster import layout as L
from legacy_roster import ratings, stock
from legacy_roster.builder import Builder, Data
from legacy_roster.roster import Roster

DISC = os.environ.get('LEGACY_ROSTER_DISC')
BARYS = 222             # a copy of St. Louis on the community roster, the tester's Barys on the game's own


def _stray(base_bytes, layout, monkeypatch):
    """A player under contract with Montreal whose one club is slot 222, and what contract_strays does with him."""
    R = Roster(base_bytes)
    U = R.U
    e = next(i for i in range(U.cur_rec) if U.get(i, 'BSXd') == L.API_TO_SLOT['BOS'])
    pid = R.link_to_pid[U.get(e, 'TWSX')]
    for i in range(U.cur_rec):
        if R.link_to_pid.get(U.get(i, 'TWSX')) == pid:
            U.set(i, 'BSXd', BARYS)
    prow = R.p_by_id[pid]
    deal = {'first': R.P.get(prow, 'PedH'), 'last': R.P.get(prow, 'RMbQ'), 'birth': [2000, 1, 1], 'org': 'MTL',
            'two_way': True}
    b = Builder(R, Data(season_year=2026, contracts=[deal]), layout=layout)
    monkeypatch.setattr(B, 'match', lambda R_, people: [dict(people[0], row=prow)])
    return b.contract_strays(), b


def test_a_club_in_a_custom_slot_of_the_games_own_roster_keeps_its_player(base_bytes, monkeypatch):
    joined, b = _stray(base_bytes, L.STOCK, monkeypatch)
    assert joined == 0 and b.mirror_of == {} and b.same_team(BARYS) == {BARYS}


def test_on_the_community_roster_slot_222_is_still_a_copy(base_bytes, monkeypatch):
    joined, b = _stray(base_bytes, L.COMMUNITY, monkeypatch)
    assert joined == 1 and b.mirror_of[BARYS] == L.API_TO_SLOT['STL']


def test_spare_records_never_copy_a_player_whose_type_is_not_his_positions():
    if not DISC or not os.path.exists(DISC):
        pytest.skip("no game disc (set LEGACY_ROSTER_DISC to your NHL Legacy disc image)")
    R = Roster(stock.from_disc(DISC))
    S = R.f['yvSd']
    rows = {S.get(i, 'zIBw'): i for i in range(S.cur_rec)}
    forwards = [R.P.get(i, 'zIBw') for i in range(R.P.cur_rec) if R.P.get(i, 'aljv') < 3 and R.P.get(i, 'zIBw') in rows]
    for pid in forwards[::2]:                       # every second forward plays as a defenceman type (as moved in the game)
        S.set(rows[pid], 'sFgQ', 4)
    before = R.P.cur_rec
    assert stock.add_spares(R) > 0
    R.reindex()
    S = R.f['yvSd']
    styles = {S.get(i, 'zIBw'): S.get(i, 'sFgQ') for i in range(S.cur_rec)}
    for prow in range(before, R.P.cur_rec):
        pid, pos = R.P.get(prow, 'zIBw'), R.P.get(prow, 'aljv')
        if pos != 4:
            assert styles[pid] in ratings.STYLE_CHOICES[ratings.style_class(pos)], R.name(prow)
