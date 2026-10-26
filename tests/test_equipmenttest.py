"""The equipment test roster (equipmenttest.make): named test players, one number each, everything else plain."""
from legacy_roster import equipment as E, equipmenttest as T
from legacy_roster.roster import Roster


def test_the_plan_names_every_number_once():
    plan = T.plan()
    assert len(plan) == len(set(plan)) == 4 + 4 + 10 + 3 + 8 + 2 + 2
    assert ('tape', 9) in plan and ('visor_tint', 7) in plan and ('sock_tuck', 0) in plan
    names = {T.name_of(c, n) for c, n in plan}
    assert len(names) == len(plan)                          # the names tell the players apart
    assert T.name_of('sock_tuck', 2) == ('Sock', 'Two')
    assert all(len(first) < 12 and len(last) < 12 for first, last in names)


def test_make_gives_each_test_player_one_number_and_plain_gear_elsewhere(base_bytes):
    R = Roster(base_bytes)
    lines = T.make(R)
    table, gtable = R.f[E.TABLE], R.f[E.GOALIE_TABLE]
    rows, grows = E.row_of(table), E.row_of(gtable, 'goalie')
    for choice, n in T.plan():
        first, last = T.name_of(choice, n)
        found = R.find_player(first, last)
        assert len(found) == 1, (first, last)
        got = E.read(table, rows[R.P.get(found[0], 'zIBw')])
        want = dict(T.SKATER_PLAIN, **({'visor': 1} if choice == 'visor_tint' else {}), **{choice: n})
        assert {c: got[c] for c in want} == want, (first, last)
    for last, values in T.GOALIE_TESTS:
        found = R.find_player('Goalie', last)
        assert len(found) == 1, last
        got = E.read(gtable, grows[R.P.get(found[0], 'zIBw')], 'goalie')
        want = dict(T.GOALIE_PLAIN, **values)
        assert {c: got[c] for c in want} == want, last
    assert len(lines) > len(T.plan()) + len(T.GOALIE_TESTS)


def test_make_twice_gives_the_same_roster(base_bytes):
    a, b = Roster(base_bytes), Roster(base_bytes)
    T.make(a)
    T.make(b)
    assert a.f.build() == b.f.build()
