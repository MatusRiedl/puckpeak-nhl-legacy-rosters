"""The community roster's copies of NHL teams (Kraken = 228, Seattle's copy) stay exact copies: a copy that lists a
player twice no longer grows past 40 ("Kraken has 49 players (max 40)", a tester's export of 0.51.1)."""
from collections import Counter

from legacy_roster import pipeline
from legacy_roster.roster import Roster
from legacy_roster.verify import structure

COPY, PRIMARY = 228, 30


def _on(R, team):
    U = R.U
    return [i for i in range(U.cur_rec) if U.get(i, 'BSXd') == team]


def _copy_with_twins(base_bytes):
    """The base with Seattle's copy holding 40 entries, 16 of them second entries of players it already lists."""
    R = Roster(base_bytes)
    U = R.U
    ents = _on(R, COPY)
    links = [U.get(e, 'TWSX') for e in ents]
    for k, e in enumerate(ents[-4:]):               # four of its own become twins
        U.set(e, 'TWSX', links[k])
    spare = [i for i in range(U.cur_rec) if 32 <= U.get(i, 'BSXd') < 60 and not U.get(i, 'jZSh')]
    for k, e in enumerate(spare[:40 - len(ents)]):  # and club entries fill it to 40 with more twins
        U.set(e, 'BSXd', COPY)
        U.set(e, 'TWSX', links[k % 6])
    out = R.f.build()
    assert len(_on(Roster(out), COPY)) == 40
    return out


def test_a_copy_with_players_listed_twice_becomes_an_exact_copy(base_bytes, data):
    source = _copy_with_twins(base_bytes)
    result = pipeline.build(source, data)          # stopped with "Kraken has 43 players (max 40)" before
    assert result.ok, result.problems
    R = Roster(result.data)
    pid = lambda i: R.link_to_pid[R.U.get(i, 'TWSX')]
    copy = Counter(pid(i) for i in _on(R, COPY))
    assert max(copy.values()) == 1
    assert set(copy) == {pid(i) for i in _on(R, PRIMARY)}
    assert pipeline.build(result.data, data).data == result.data


def test_verify_names_a_player_listed_twice(base_bytes):
    before, _ = structure(Roster(base_bytes))
    assert not [k for k in before if k[0] == 'twice']
    R = Roster(base_bytes)
    U = R.U
    a, b = _on(R, PRIMARY)[:2]
    U.set(b, 'TWSX', U.get(a, 'TWSX'))
    problems, _ = structure(Roster(R.f.build()))
    assert ('twice', PRIMARY, R.link_to_pid[U.get(a, 'TWSX')]) in problems
