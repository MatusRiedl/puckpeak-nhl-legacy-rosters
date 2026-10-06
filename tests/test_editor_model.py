"""The roster editor's view of a roster (editor/model.py): teams, players, as is vs to be."""
from legacy_roster import layout as L
from legacy_roster.editor import model


def test_a_roster_reads_into_teams_and_players(base_bytes):
    snap = model.Snapshot(base_bytes, season_year=2026)
    assert snap.leagues()[0] == 'NHL' and snap.leagues()[-1] == 'Free agents'
    assert L.API_TO_SLOT['EDM'] in snap.teams_in('NHL') and len(snap.teams_in('NHL')) == 32
    mcd = next(p for p in snap.roster(L.API_TO_SLOT['EDM']) if p.name == 'Connor McDavid')
    assert mcd.pos == 'C' and mcd.num == 97 and 80 < mcd.ovr < 100 and mcd.ratings['Passing'] > 80
    assert mcd.age(2026) in (29, 30) and mcd.country == 'CAN'
    assert mcd.artid == 9857 and mcd.hasportrait            # his menu photo on the disc (the card shows it)
    assert snap.search('mcdav')[0].name == 'Connor McDavid'
    assert snap.roster(model.FREE_AGENTS)


def test_compare_tells_where_two_rosters_differ(base_bytes, built):
    before, after = model.Snapshot(base_bytes), model.Snapshot(built.data)
    joined = left = 0
    for team in range(32):
        diff = model.compare(before, after, team)
        joined += len(diff['joined'])
        left += len(diff['left'])
        names = {p.name for p in after.roster(team)}
        assert all(p.name not in names for p in diff['left'])
    moved = sum(1 for r in built.log if r[1] in ('moved', 'added', 'created') and r[0] in L.API_TO_SLOT)
    assert joined == moved and left > 0
