"""Sticks in team colours (sticks.py): the tables measured from the disc's stick textures, the step on an updated
roster, and the check for verify."""
from legacy_roster import equipment, sticks
from legacy_roster.roster import Roster

UTAH = 22


def _column(R):
    A = R.f[equipment.TABLE]
    stick = equipment.tag('stick')
    return [A.get(i, stick) for i in range(A.cur_rec)]


def _skater_sticks(R, slot):
    """{player row: stick} of the skaters on a team."""
    A, rows = R.f[equipment.TABLE], equipment.row_of(R.f[equipment.TABLE])
    out = {}
    for _entry, prow, _name, _jersey, _style in R.team_roster(slot):
        if prow is None or R.P.get(prow, 'aljv') == sticks.GOALIE:
            continue
        row = rows.get(R.P.get(prow, 'zIBw'))
        if row is not None:
            out[prow] = A.get(row, equipment.tag('stick'))
    return out


def _red(stick):
    return any(sticks.hue_name(hue) == 'red' for hue, _share in sticks.colours(stick))


def test_tables():
    assert sticks.DRAWABLE and set(sticks.BRAND) == set(sticks.DRAWABLE) == set(sticks.COLOURS)
    assert sticks.CURRENT <= sticks.DRAWABLE
    assert sticks.COLOURS[sticks.DEFAULT] == 'neutral'
    assert sticks.COLOURS[86] == sticks.COLOURS[102] == 'red'          # CCM RBZ: the red sticks Utah carried
    assert sticks.COLOURS[112] == 'neutral' and sticks.BRAND[112] == 'CCM'


def test_pick_fits_and_keeps_the_brand():
    for hues in ([205], [], [0, 210], [42]):                         # Utah blue; black / silver; red and navy; gold
        for stick in sorted(sticks.DRAWABLE):
            new = sticks.pick(stick, hues)
            assert sticks.fits(new, hues), (stick, hues, new)
            assert new == sticks.DEFAULT or sticks.BRAND[new] == sticks.BRAND[stick]


def test_no_utah_player_keeps_a_red_stick(base_bytes, built):
    R = Roster(base_bytes)
    before = _skater_sticks(R, UTAH)
    assert any(_red(s) for s in before.values())                     # the base has some (Schmaltz, Carcone, ...)
    assert not any(sticks.hue_name(h) == 'red' for h in
                   (sticks.hue_of(c) for c in sticks.team_colours(R, UTAH)) if h is not None)
    changes = sticks.team_sticks(R)
    after = _skater_sticks(R, UTAH)
    assert not [p for p, s in after.items() if _red(s)]
    assert {c.prow for c in changes if c.slot == UTAH} == {p for p, s in before.items() if s != after[p]}
    done = Roster(built.data)                                        # the update's NHL step swapped them already
    assert not [p for p, s in _skater_sticks(done, UTAH).items() if _red(s)]
    assert sticks.team_sticks(done) == []


def test_only_coloured_sticks_change(base_bytes):
    R = Roster(base_bytes)
    old = _column(R)
    changes = sticks.team_sticks(R)
    assert changes
    assert all(sticks.COLOURS[c.old] != 'neutral' and c.old != c.new for c in changes)
    rows = equipment.row_of(R.f[equipment.TABLE])
    changed = {rows[R.P.get(c.prow, 'zIBw')] for c in changes}
    new = _column(R)
    assert [i for i in range(len(old)) if old[i] != new[i]] == sorted(changed)


def test_keep_and_second_run(base_bytes):
    R = Roster(base_bytes)
    first = sticks.team_sticks(R)
    data = R.f.build()
    again = Roster(data)
    assert sticks.team_sticks(again) == []
    assert again.f.build() == data
    kept = Roster(base_bytes)
    mine = first[0].prow
    assert mine not in {c.prow for c in sticks.team_sticks(kept, keep={mine})}


def test_problems(base_bytes):
    R = Roster(base_bytes)
    assert sticks.problems(R) == []
    A = R.f[equipment.TABLE]
    A.set(0, equipment.tag('stick'), 1)                              # a model of an older game: drawn plain blue
    assert len(sticks.problems(R)) == 1 and 'model 1' in sticks.problems(R)[0]
    assert sticks.problems(R, also={1}) == []
