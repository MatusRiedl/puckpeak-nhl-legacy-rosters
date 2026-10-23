"""Utah, Seattle and Vegas on any roster (builder.nhl_identity): arena, city and colours. The community roster
still holds Arizona Arena and Nashville's arena for them (lab round 32)."""
from legacy_roster import layout as L
from legacy_roster.builder import GEAR_SLIPS, NHL_GEAR, NHL_LOOK, Builder, Data
from legacy_roster.roster import Roster


def test_the_three_teams_get_their_arenas_and_colours_once(base_bytes):
    R = Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    assert b.nhl_identity() == 3
    A, T = R.f['OEtS'], R.T
    for slot, (arena, city, primary, secondary) in NHL_LOOK.items():
        row = T.get(slot, 'arenaid')
        assert (A.get(row, 'arenaname'), A.get(row, 'cityname')) == (arena, city) and A.get(row, 'index') == row
        assert tuple(T.get(slot, f"primarycolor_{c}") for c in 'rgb') == primary
        assert tuple(T.get(slot, f"secondarycolor_{c}") for c in 'rgb') == secondary
    assert len({T.get(s, 'arenaid') for s in NHL_LOOK}) == 3                      # each its own arena
    once = R.f.build()
    assert b.nhl_identity() == 0 and R.f.build() == once                           # a second time changes nothing


ZONES = [[f"zone{z}_{c}" for c in 'rgb'] for z in range(1, 10)]
GOALIE_ZONES = [[f"{part}zone{z}color_{c}" for c in 'rgb'] for part in ('blocker', 'pads', 'trapper') for z in range(1, 10)]


def colours(table, row, zones=ZONES):
    return [tuple(table.get(row, n) for n in trio) for trio in zones]


def hue(colour):
    return max(colour) and (max(colour) - min(colour)) / max(colour) >= 0.25


def test_the_three_teams_wear_their_own_colours_on_their_helmets_and_gear(base_bytes):
    R, src = Roster(base_bytes), Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    assert b.nhl_gear() > 0
    for name, zones in (('vbHh', ZONES), ('nAUy', GOALIE_ZONES)):
        E, S = R.f[name], src.f[name]
        painted = 0
        for row in range(E.cur_rec):
            slot = E.get(row, 'team') - 1                   # the equipment tables count teams from 1
            if slot in NHL_GEAR:                            # coloured parts only in the team's gear colours
                assert all(c in NHL_GEAR[slot] or not hue(c) for c in colours(E, row, zones)), (name, slot)
                painted += colours(E, row, zones) != colours(S, row, zones)
            else:                                           # every other team as it was (Philadelphia, Washington)
                assert colours(E, row, zones) == colours(S, row, zones), (name, slot)
        assert painted, name
    E = R.f['vbHh']
    utah = [colours(E, row)[0] for row in range(E.cur_rec) if E.get(row, 'team') == 23 and E.get(row, 'equipment') == 8]
    assert (130, 17, 19) not in utah and (32, 32, 32) in utah                    # Arizona's red helmet is Utah's black
    once = R.f.build()
    assert b.nhl_gear() == 0 and R.f.build() == once


def paint_the_old_way(R):
    """What 0.10.0 to 0.20.0 did: the team number taken for the slot (Philadelphia in Utah's colours, ...)."""
    E = R.f['vbHh']
    for row in range(E.cur_rec):
        slot = E.get(row, 'team')
        if slot not in NHL_LOOK:
            continue
        _a, _c, primary, secondary = NHL_LOOK[slot]
        for trio, colour in zip(ZONES, colours(E, row)):
            if hue(colour):
                new = secondary if max(colour) < 75 else primary
            elif max(colour) > 200 and colour[0] - colour[2] >= 15:
                new = (231, 231, 231)
            else:
                continue
            for n, v in zip(trio, new):
                E.set(row, n, v)


def test_the_colours_the_old_step_put_on_philadelphia_and_washington_go_back(base_bytes):
    R = Roster(base_bytes)
    paint_the_old_way(R)
    damaged = R.f.build()
    E = R.f['vbHh']
    assert any((106, 179, 230) in colours(E, row) for row in range(E.cur_rec) if E.get(row, 'team') == 22)
    # with the game's own roster: exactly as it was
    own = Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    b.nhl_gear(own=own)
    O = own.f['vbHh']
    for row in range(E.cur_rec):
        if E.get(row, 'team') - 1 in (21, 29):
            assert colours(E, row) == colours(O, row), row
    once = R.f.build()
    assert b.nhl_gear(own=own) == 0 and R.f.build() == once
    # without it: the team's own colours, none of Utah's or Seattle's
    R = Roster(damaged)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    b.nhl_gear()
    E = R.f['vbHh']
    for row in range(E.cur_rec):
        slot = E.get(row, 'team') - 1
        if slot in GEAR_SLIPS and slot not in NHL_GEAR:
            look = NHL_LOOK[GEAR_SLIPS[slot]]
            assert look[2] not in colours(E, row) and (slot != 29 or look[3] not in colours(E, row)), row
    once = R.f.build()
    assert b.nhl_gear() == 0 and R.f.build() == once
