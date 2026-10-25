"""Players NHL.com's player search puts with an NHL team (datasource.find_missing) join it only while it has room: the
search names a farm player's NHL organisation (Coachella Valley's players 'SEA'), and a tester's roster with Seattle's
farm on Seattle stopped with "Kraken has 49 players (max 40)" in 0.51.1 and 0.51.2."""
import copy
from collections import Counter

from legacy_roster import pipeline
from legacy_roster.builder import Builder
from legacy_roster.matching import norm
from legacy_roster.roster import Roster

SEATTLE = 30


def _searched(R, count, listed=()):
    """`count` skaters of AHL clubs as the player search returns them, all with Seattle (never one the roster lists
    `listed` name: find_missing looks up only the others)."""
    P, U = R.P, R.U
    out, seen = [], set()
    names = {(norm(p['first']), norm(p['last'])) for p in listed}
    for i in range(U.cur_rec):
        if not 32 <= U.get(i, 'BSXd') < 62:
            continue
        prow = R.p_by_id.get(R.link_to_pid.get(U.get(i, 'TWSX')))
        if prow is None or prow in seen or P.get(prow, 'aljv') == 4 \
                or (norm(P.get(prow, 'PedH')), norm(P.get(prow, 'RMbQ'))) in names:
            continue
        seen.add(prow)
        out.append({'team': 'SEA', 'first': P.get(prow, 'PedH'), 'last': P.get(prow, 'RMbQ'), 'num': None,
                    'pos': 'CLRD'[P.get(prow, 'aljv')],
                    'birth': (P.get(prow, 'dnFq') + 1910, P.get(prow, 'pLKJ') + 1, P.get(prow, 'iwsK') + 1),
                    'source': 'player search'})
        if len(out) == count:
            break
    return out


def test_searched_players_join_their_nhl_team_only_while_it_has_room(base_bytes, data):
    made = copy.copy(data)
    made.nhl_players = data.nhl_players + _searched(Roster(base_bytes), 25, data.nhl_players)
    listed = sum(p['team'] == 'SEA' for p in data.nhl_players)
    result = pipeline.build(base_bytes, made)          # stopped with "... has 5x players (max 40)" before
    assert result.ok, result.problems
    R = Roster(result.data)
    on = Counter(R.U.get(i, 'BSXd') for i in range(R.U.cur_rec))
    assert on[SEATTLE] <= 40
    kept = [p for p in result.builder.nhl_listed if p.get('source') == 'player search']
    assert len(kept) == Builder.NHL_KEEP_ROOM - listed


def test_a_searched_player_a_club_league_lists_stays_in_the_minors(base_bytes, data):
    R = Roster(base_bytes)
    b = Builder(R, data)
    searched = _searched(R, 3)
    b.league_names = {(norm(p['first']), norm(p['last'])) for p in searched[:1]}
    assert b.searched_room(searched) == searched[1:]
