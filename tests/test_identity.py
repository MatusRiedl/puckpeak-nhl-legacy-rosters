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
