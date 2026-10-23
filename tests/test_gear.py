"""Gear in colours the team wears and models the game can draw (0.30.0, 'gear colours'): Builder.club_gear (club helmets
and gloves), Builder.goalie_gear (goalies in colours their club does not wear), equipment.fix_models / model_problems
(models 85-88 the game draws plain blue)."""
from legacy_roster import equipment, sticks
from legacy_roster import layout as L
from legacy_roster.builder import Builder, Data
from legacy_roster.roster import Roster

ZONES = [[f"zone{z}_{c}" for c in 'rgb'] for z in range(1, 10)]
GOALIE_ZONES = [[f"{part}zone{z}color_{c}" for c in 'rgb'] for part in Builder.GEAR_PARTS for z in range(1, 10)]


def colours(table, row, zones=ZONES):
    return [tuple(table.get(row, n) for n in trio) for trio in zones]


def test_a_model_the_game_can_draw():
    assert equipment.drawable('goalie', 'pads', 30) == 30
    assert equipment.drawable('goalie', 'blocker', 86, mates=(86, 30)) == 30     # the goalie's own pads' number
    assert equipment.drawable('goalie', 'pads', 86) == 84                        # else the closest lower one
    assert equipment.drawable('skater', 'helmet', 0) == 1                        # else the lowest


def test_models_the_game_cannot_draw_are_swapped_once(base_bytes):
    R = Roster(base_bytes)
    assert any('cannot draw' in p for p in equipment.model_problems(R))         # the community's 85-88
    swapped = equipment.fix_models(R)
    assert swapped and all(new in equipment.DRAWABLE[kind][choice] for kind, _g, choice, _o, new in swapped)
    assert equipment.model_problems(R) == []
    once = R.f.build()
    assert equipment.fix_models(R) == [] and R.f.build() == once
    src = Roster(base_bytes)                    # verify accepts what the roster carried before
    assert equipment.model_problems(src, also=equipment.worn(src)) == []


def _club(slot):
    return 32 <= slot < 214 and slot not in L.NATIONAL and slot not in L.MIRROR_OF


def test_club_helmets_and_gloves_wear_the_clubs_colours(base_bytes):
    R, src = Roster(base_bytes), Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    assert b.club_gear() > 0
    E, S = R.f['vbHh'], src.f['vbHh']
    for row in range(E.cur_rec):
        slot, eq = E.get(row, 'team') - 1, E.get(row, 'equipment')
        if colours(E, row) != colours(S, row):
            assert _club(slot) and eq in Builder.TEAM_GEAR, (slot, eq)
        own = [c for c in sticks.team_colours(R, slot) if sticks.hue_of(c) is not None]
        if _club(slot) and eq in Builder.TEAM_GEAR and own:
            hues = [sticks.hue_of(c) for c in own]
            assert not any(b.off_hue(c, hues) for c in colours(E, row)), (R.team_name(slot), eq)
    assert R.f['NDEo'].build() == src.f['NDEo'].build()      # the custom teams' rows: their own (layout.OWN_KIT)
    once = R.f.build()
    assert b.club_gear() == 0 and R.f.build() == once


def test_goalies_wear_their_clubs_colours(base_bytes):
    R = Roster(base_bytes)
    b = Builder(R, Data(season_year=2026), layout=L.check_base(R))
    b.nhl_identity()
    b.goalie_gear()
    G = R.f['lVMf']
    rows = {G.get(i, 'zIBw'): i for i in range(G.cur_rec)}
    checked = 0
    for pid, team in b.home_teams().items():
        prow = R.p_by_id.get(pid)
        if prow is None or R.P.get(prow, 'aljv') != 4 or pid not in rows:
            continue
        hues = [h for h in (sticks.hue_of(c) for c in sticks.team_colours(R, team)) if h is not None]
        assert not any(b.off_hue(c, hues) for c in colours(G, rows[pid], GOALIE_ZONES)), R.name(prow)
        checked += 1
    assert checked > 100
    once = R.f.build()
    b.goalie_gear()
    assert R.f.build() == once                                  # a second time changes nothing
