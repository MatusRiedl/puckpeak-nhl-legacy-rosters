"""The Roster editor follows the roster's own layout for slots 222-233 (0.90.0 phase 8): on the community roster they
are copies of NHL teams (not a team to pick, no lines of their own), on the game's own roster they may be clubs of the
player's own (a tester's KHL clubs) and are teams like any other. The disc tests need LEGACY_ROSTER_DISC (test_stock.py)."""
import os

import pytest

from legacy_roster import layout as L
from legacy_roster import stock
from legacy_roster.editor import model
from legacy_roster.roster import Roster

DISC = os.environ.get('LEGACY_ROSTER_DISC')
BARYS = 222


def _disc_with_a_club_in_222():
    """The game's own roster with three Boston players moved to slot 222, as a club of the player's own; (bytes, keys)."""
    if not DISC or not os.path.exists(DISC):
        pytest.skip("no game disc (set LEGACY_ROSTER_DISC to your NHL Legacy disc image)")
    R = Roster(stock.from_disc(DISC))
    U = R.U
    moved = [i for i in range(U.cur_rec) if U.get(i, 'BSXd') == L.API_TO_SLOT['BOS']][:3]
    for i in moved:
        U.set(i, 'BSXd', BARYS)
    raw = R.f.build()
    snap = model.Snapshot(raw)
    keys = [p.who for p in snap.roster(BARYS)]
    return raw, snap, keys


def test_the_community_roster_keeps_its_copies(base_bytes):
    snap = model.Snapshot(base_bytes)
    assert snap.copies == L.MIRROR_OF
    p = next(iter(snap.roster(L.API_TO_SLOT['STL'])))
    assert BARYS in p.teams and BARYS not in p.clubs


def test_a_club_in_slot_222_of_the_games_own_roster_is_a_team_of_its_own():
    raw, snap, keys = _disc_with_a_club_in_222()
    assert snap.copies == {} and len(keys) == 3
    assert all(BARYS in snap.by_who[k].clubs for k in keys)     # (also on an All-Star team of 2014)


def test_an_edit_moves_a_player_to_the_club_in_slot_222():
    raw, snap, keys = _disc_with_a_club_in_222()
    other = next(p for p in snap.roster(L.API_TO_SLOT['TOR']))
    built = model.apply_edits(raw, {other.who: {'team': BARYS}}, {}, 2026)
    assert not built.problems, built.problems
    after = model.Snapshot(built.data)
    assert BARYS in after.by_who[other.who].clubs
