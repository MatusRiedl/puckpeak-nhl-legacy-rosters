"""Utah, Seattle and Vegas for the game's own roster (builder.nhl_identity): arena, city and colours."""
from legacy_roster import layout as L
from legacy_roster.builder import NHL_LOOK, Builder, Data
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
    assert b.nhl_identity() == 3 and R.f.build() == once                           # a second time changes nothing


def test_the_three_teams_wear_their_own_colours_on_their_helmets_and_gear(base_bytes):
    R = Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    assert b.nhl_gear() > 0
    E = R.f['vbHh']
    seen = {slot: set() for slot in NHL_LOOK}
    for row in range(E.cur_rec):
        slot = E.get(row, 'team')
        if slot in seen:
            seen[slot] |= {tuple(E.get(row, f"zone{z}_{c}") for c in 'rgb') for z in range(1, 10)}
    assert (218, 57, 28) not in seen[22] and (207, 61, 28) not in seen[22]          # Arizona's red is gone
    assert NHL_LOOK[22][2] in seen[22] and NHL_LOOK[30][2] in seen[30] and NHL_LOOK[31][2] in seen[31]
    assert (186, 28, 32) not in seen[30] and (158, 16, 28) not in seen[31]          # nor the All-Star colours
    once = R.f.build()
    assert b.nhl_gear() == 0 and R.f.build() == once
