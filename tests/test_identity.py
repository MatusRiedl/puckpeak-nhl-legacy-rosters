"""The 32 NHL teams' arena names and colours on any roster (builder.nhl_identity), and Utah's, Seattle's and Vegas's cities.
Both rosters hold old or half-right names and colours (lab round 32; the testers' lists of 2026-10-26)."""
from legacy_roster import layout as L
from legacy_roster.builder import (AHL_ARENAS, GEAR_SLIPS, NHL_ARENAS, NHL_CITIES, NHL_COLOURS, NHL_GEAR, NHL_LOOK, Builder, Data)
from legacy_roster.roster import Roster


def test_every_nhl_team_gets_its_arena_and_colours_once(base_bytes):
    R = Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    assert b.nhl_identity() >= 30
    A, T = R.f['OEtS'], R.T
    for slot in range(32):
        row = T.get(slot, 'arenaid')
        assert A.get(row, 'arenaname') == NHL_ARENAS[slot] and A.get(row, 'index') == row
        if slot in NHL_CITIES:
            assert A.get(row, 'cityname') == NHL_CITIES[slot]
        assert tuple(T.get(slot, f"primarycolor_{c}") for c in 'rgb') == NHL_COLOURS[slot][0]
        assert tuple(T.get(slot, f"secondarycolor_{c}") for c in 'rgb') == NHL_COLOURS[slot][1]
    assert len({T.get(s, 'arenaid') for s in range(32)}) == 32                    # each its own arena (Seattle, Vegas split)
    once = R.f.build()
    assert b.nhl_identity() == 0 and R.f.build() == once                           # a second time changes nothing


def test_a_custom_copy_and_a_farm_club_in_the_same_building_follow_the_rename(base_bytes):
    R = Roster(base_bytes)
    T, A = R.T, R.f['OEtS']
    shared = {t: T.get(t, 'arenaid') for t in (0, 225, 1, 44)}                    # Anaheim and its copy, Winnipeg and Manitoba
    assert shared[0] == shared[225] and shared[1] == shared[44]
    Builder(R, Data(season_year=2026), layout=L.check_base(R)).nhl_identity()
    assert T.get(225, 'arenaid') == T.get(0, 'arenaid') and A.get(T.get(225, 'arenaid'), 'arenaname') == "Honda Center®"
    assert T.get(44, 'arenaid') == T.get(1, 'arenaid') and A.get(T.get(44, 'arenaid'), 'arenaname') == "Canada Life Centre™"


def test_a_full_arena_table_keeps_the_shared_row_but_still_paints_the_colours(base_bytes):
    R = Roster(base_bytes)
    A, T = R.f['OEtS'], R.T
    while A.cur_rec < A.max_rec:                                                  # use up the free rows
        A.add_record(template=0)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    b.nhl_identity()
    assert T.get(30, 'arenaid') == T.get(31, 'arenaid')                           # no room to split them
    assert tuple(T.get(31, f"primarycolor_{c}") for c in 'rgb') == NHL_COLOURS[31][0]
    assert b.set_arena(31, "Somewhere Arena") is False


def test_set_arena_gives_a_team_alone_in_a_shared_building_a_row_of_its_own(base_bytes):
    R = Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    T, A = R.T, R.f['OEtS']
    row = T.get(1, 'arenaid')
    assert b.set_arena(1, "Moose Ice", alone=True) is True                        # Manitoba (44) shares it: Winnipeg splits
    assert T.get(1, 'arenaid') != row and A.get(T.get(1, 'arenaid'), 'arenaname') == "Moose Ice"
    assert A.get(row, 'arenaname') != "Moose Ice" and T.get(44, 'arenaid') == row
    assert b.set_arena(1, "Moose Ice", alone=True) is None


def test_every_ahl_club_plays_in_its_own_current_arena_and_the_table_has_room(base_bytes):
    R = Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    b.nhl_identity()
    rows_before = R.f['OEtS'].cur_rec
    assert b.ahl_identity() == len(AHL_ARENAS)
    A, T = R.f['OEtS'], R.T
    for slot, (name, city, capacity) in AHL_ARENAS.items():
        row = T.get(slot, 'arenaid')
        assert (A.get(row, 'arenaname'), A.get(row, 'cityname'), A.get(row, 'maxattendance')) == (name, city, capacity), slot
        assert len(name.encode()) <= A.field('arenaname').bits // 8 - 1
    assert A.cur_rec - rows_before == 3 and A.cur_rec <= A.max_rec              # the Barracuda, Coachella and Henderson
    own = [T.get(s, 'arenaid') for s in (54, 234, 235)]
    assert len(set(own)) == 3 and not set(own) & {T.get(s, 'arenaid') for s in range(32)}
    assert T.get(44, 'arenaid') == T.get(1, 'arenaid')                           # Manitoba stays with Winnipeg
    assert A.get(T.get(25, 'arenaid'), 'arenaname') == NHL_ARENAS[25]            # the Sharks keep SAP Center
    assert A.get(T.get(37, 'arenaid'), 'arenaname') == "Blue Arena"
    once = R.f.build()
    assert b.ahl_identity() == 0 and R.f.build() == once                          # a second time changes nothing


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
    assert any(NHL_LOOK[22][2] in colours(E, row) for row in range(E.cur_rec) if E.get(row, 'team') == 22)
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
