"""Real sock tucks, pant lengths, neck guards and tape from the data pack's `equipment` part (Builder.real_equipment,
equipment.real_values): only those fields, only for a full name + birthdate match, the same on a second run, and a new
player starts plain (Builder.take_record)."""
from legacy_roster import equipment
from legacy_roster import layout as L
from legacy_roster.builder import Builder, Data
from legacy_roster.roster import Roster


def entry(b, prow, **gear):
    P = b.P
    shown = P.get(prow, 'dnFq') + 1910
    birth = [shown, P.get(prow, 'pLKJ') + 1, P.get(prow, 'iwsK') + 1]
    goalie = P.get(prow, 'aljv') == 4
    out = {'first': P.get(prow, 'PedH'), 'last': P.get(prow, 'RMbQ'), 'birth': birth, 'pos': 'G' if goalie else 'C'}
    if goalie:
        out['goalie'] = True
    return dict(out, **gear)


def people(b, n=3):
    """n skaters and a goalie with a gear row, a name and a birthdate no one else on the roster shares."""
    P, seen, skaters, goalies = b.P, {}, [], []
    for prow in range(P.cur_rec):
        key = (P.get(prow, 'PedH'), P.get(prow, 'RMbQ'))
        seen[key] = seen.get(key, 0) + 1
    for prow in range(P.cur_rec):
        key = (P.get(prow, 'PedH'), P.get(prow, 'RMbQ'))
        goalie = P.get(prow, 'aljv') == 4
        if not all(key) or seen[key] != 1 or b.equipment_row(prow, 'goalie' if goalie else 'skater') is None:
            continue
        (goalies if goalie else skaters).append(prow)
    return skaters[100:100 + n], goalies[100]


def builder(base_bytes, part):
    R = Roster(base_bytes)
    return R, Builder(R, Data(season_year=2026, equipment=part), layout=L.check_base(R))


def models(R):
    A, G = R.f[equipment.TABLE], R.f[equipment.GOALIE_TABLE]
    keep = [c for c in equipment.CHOICES if c not in ('sock_tuck', 'pant_length', 'tape')]
    return ([[A.get(i, equipment.tag(c)) for c in keep] for i in range(A.cur_rec)],
            [[G.get(i, equipment.tag(c, 'goalie')) for c in equipment.GOALIE_CHOICES if c not in ('neck', 'tape')]
             for i in range(G.cur_rec)])


def test_a_player_the_part_has_gets_his_real_tucks_and_nothing_else_changes(base_bytes):
    R = Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    (a, c, d), g = people(b)
    part = {'players': [entry(b, a, sock=1, pants=1, tape='white'), entry(b, c), entry(b, g, neck=1)]}
    R, b = builder(base_bytes, part)
    before = models(R)
    assert b.real_equipment() == 3
    A, G = R.f[equipment.TABLE], R.f[equipment.GOALIE_TABLE]
    want = equipment.real_values(part['players'][0])
    got = equipment.read(A, b.equipment_row(a))
    assert {k: got[k] for k in want} == want and want['sock_tuck'] == equipment.REAL['sock_tuck'][1]
    plain = equipment.read(A, b.equipment_row(c))
    assert plain['sock_tuck'] == equipment.REAL['sock_tuck'][0] and plain['pant_length'] == equipment.REAL['pant_length'][0]
    assert equipment.read(G, b.equipment_row(g, 'goalie'), 'goalie')['neck'] == equipment.REAL['neck'][1]
    assert models(R) == before                                    # no model, shoulder pad, jersey tuck or visor changed
    once = R.f.build()
    assert b.real_equipment() == 0 and R.f.build() == once        # a second run changes nothing


def test_a_name_without_the_birthdate_gets_nothing(base_bytes):
    R = Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    (a, _c, _d), _g = people(b)
    wrong = entry(b, a, sock=2)
    wrong['birth'] = [wrong['birth'][0] + 3] + wrong['birth'][1:]
    R, b = builder(base_bytes, {'players': [wrong]})
    once = R.f.build()
    assert b.real_equipment() == 0 and R.f.build() == once


def test_a_goalie_is_never_matched_by_a_skater_entry(base_bytes):
    R = Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    _skaters, g = people(b)
    e = entry(b, g, neck=1)
    e.pop('goalie')
    R, b = builder(base_bytes, {'players': [e]})
    assert b.real_equipment() == 0


def test_no_part_no_change(base_bytes):
    R, b = builder(base_bytes, None)
    once = R.f.build()
    assert b.real_equipment() == 0 and R.f.build() == once


def test_only_what_the_lab_named_is_written():
    assert set(equipment.real_values({'first': 'A', 'last': 'B', 'birth': [1990, 1, 1], 'pos': 'C', 'sock': 1})) \
        == {'sock_tuck', 'pant_length'}
    assert set(equipment.real_values({'neck': 1, 'goalie': True}, goalie=True)) == {'neck'}
    assert equipment.real_values({'sock': 9}) == {'pant_length': equipment.REAL['pant_length'][0]}   # an unknown number is skipped


def test_a_new_player_does_not_wear_the_last_holders_tucks(base_bytes):
    R = Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    pos = next(k for k, rows in b.donors.spare.items() if k != 4 and rows)
    spare = b.donors.spare[pos][0]
    A = R.f[equipment.TABLE]
    row = b.equipment_row(spare)
    A.set(row, equipment.tag('sock_tuck'), 3)
    A.set(row, equipment.tag('tape'), 7)
    taken = b.take_record(pos, 'Test Player', required=False)
    assert taken is not None
    r = equipment.read(A, b.equipment_row(taken))
    assert all(r[c] == v for c, v in equipment.NEW_PLAYER.items())
