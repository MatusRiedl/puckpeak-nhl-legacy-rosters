from collections import Counter

import pytest

from legacy_roster import layout as L
from legacy_roster import lines, pipeline, ratings, schema
from legacy_roster.builder import Builder, Data
from legacy_roster.matching import match
from legacy_roster.roster import Roster
from legacy_roster.verify import verify


def roster_of(R, team):
    return {prow for _, prow, _, _, _ in R.team_roster(team)}


def test_the_build_passes_every_integrity_check(built):
    assert built.problems == []
    assert built.info['empty_national_teams'] == []


def test_every_listed_nhl_player_is_on_his_team_and_nobody_else_is(built, data):
    R = Roster(built.data)
    people = match(R, [dict(p) for p in data.nhl_players])
    assert all(p['row'] is not None for p in people)
    for abbr, slot in L.API_TO_SLOT.items():
        assert roster_of(R, slot) == {p['row'] for p in people if p['team'] == abbr}, abbr


def test_mirror_teams_copy_their_primary(built):
    R = Roster(built.data)
    for prim, mirrors in L.MIRRORS.items():
        for m in mirrors:
            assert roster_of(R, m) == roster_of(R, prim)


def test_hard_limits_no_new_team_and_no_team_changes_league(built, base_bytes):
    src, new = Roster(base_bytes), Roster(built.data)
    assert new.T.cur_rec == src.T.cur_rec == L.TEAM_COUNT
    assert new.T.column('league') == src.T.column('league')
    assert new.T.records == src.T.records            # the team table is not touched at all


def test_nhl_and_national_teams_dress_a_legal_line_up(built):
    R = Roster(built.data)
    U, P = R.U, R.P
    for team in list(range(32)) + list(range(133, 154)):
        ents = [e for e in range(U.cur_rec) if U.get(e, 'team') == team]
        assert len(ents) <= L.MAX_PER_TEAM
        dressed = [e for e in ents if U.get(e, 'rosterstatus')]
        pos = Counter('FFFDG'[P.get(R.p_by_id[R.link_to_pid[U.get(e, 'playerindex')]], 'position')] for e in dressed)
        assert (len(dressed), pos['G']) == (20, 2) and pos['D'] >= 6, R.team_name(team)
        for slot in schema.LINE_SLOTS:
            assert sum(U.get(e, slot) for e in ents) == 1, (R.team_name(team), slot)
        assert sorted(U.get(e, 'key') for e in ents) == [team * 40 + k for k in range(len(ents))]


def test_published_attributes_are_stored_exactly(built, pack):
    R = Roster(built.data)
    S, G = R.f['yvSd'], R.f['yuHm']
    rows = {t.name: {t.get(i, 'game_id'): i for i in range(t.cur_rec)} for t in (S, G)}
    checked = 0
    for p in pack['ea_ratings']:
        if len(p['attrs']) < 10 or not p['birth']:
            continue
        first, _, last = p['name'].partition(' ')
        found = R.find_player(first, last)
        if len(found) != 1:
            continue
        t, amap = (G, schema.EA_GOALIE) if p['position'] == 'G' else (S, schema.EA_SKATER)
        row = rows[t.name].get(R.P.get(found[0], 'game_id'))
        if row is None:
            continue
        for label, value in p['attrs'].items():
            if label in amap:
                assert t.get(row, amap[label]) == max(0, min(63, value - schema.RATING_BASE)), (p['name'], label)
        checked += 1
    assert checked > 250


def test_fields_nobody_publishes_are_left_alone(built, base_bytes):
    src, new = Roster(base_bytes), Roster(built.data)
    created = {src.P.get(r, 'game_id') for r in built.builder.created}
    for tname in ('yvSd', 'yuHm'):
        a, b = src.f[tname], new.f[tname]
        for field in ('c_potential', 'growthtier', 'trait0', 'playerstyle'):
            changed = [i for i in range(a.cur_rec) if a.get(i, field) != b.get(i, field) and a.get(i, 'game_id') not in created]
            assert not changed, (tname, field)


def test_new_players_do_not_inherit_the_previous_owner_of_their_record(built):
    R = Roster(built.data)
    assert built.builder.created
    for prow in built.builder.created:
        P = R.P
        assert 'ZZ' not in P.get(prow, 'lastname')
        assert (P.get(prow, 'hasportrait'), P.get(prow, 'artid'), P.get(prow, 'audioid')) == (0, 0, 0)
        assert P.get(prow, 'headid') >= 60000
        assert P.get(prow, 'draftyear') == 255 and P.get(prow, 'nhlgamesplayedcareer') == 0


def test_roster_entries_carry_the_players_own_style(built):
    R = Roster(built.data)
    style = {}
    for tname in ('yvSd', 'yuHm'):
        t = R.f[tname]
        style.update({t.get(i, 'game_id'): t.get(i, 'playerstyle') for i in range(t.cur_rec)})
    for e in range(R.U.cur_rec):
        assert R.U.get(e, 'playerstyle') == style[R.link_to_pid[R.U.get(e, 'playerindex')]]


def test_a_second_run_on_its_own_output_changes_nothing(built, data):
    again = pipeline.build(built.data, data)
    assert again.problems == []
    assert again.builder.maintain
    assert again.data == built.data


def test_steps_can_be_run_on_their_own(base_bytes, data):
    only_ratings = pipeline.build(base_bytes, Data(ea_ratings=data.ea_ratings, season_year=data.season_year),
                                  steps=[pipeline.RATINGS])
    assert only_ratings.problems == []
    src, new = Roster(base_bytes), Roster(only_ratings.data)
    assert new.U.records == src.U.records and new.P.records == src.P.records     # nobody moved
    assert new.f['yvSd'].records != src.f['yvSd'].records
    nothing = pipeline.build(base_bytes, Data(), steps=[])
    assert nothing.data == base_bytes


def test_nhl_players_get_the_position_nhl_com_lists(built, data):
    R = Roster(built.data)
    people = match(R, [dict(p) for p in data.nhl_players])
    for p in people:
        if p['pos'] != 'G':
            assert R.P.get(p['row'], 'position') == L.POS_CODE[p['pos']], (p['first'], p['last'])
    smith = [p for p in people if (p['first'], p['last'], p['team']) == ('Cole', 'Smith', 'CHI')]
    if smith:                                       # the owner's report: Chicago had one right wing too few
        assert R.P.get(smith[0]['row'], 'position') == 2
        assert any(r[1] == 'position changed' and r[2] == 'Cole Smith' for r in built.builder.log)


def test_wingers_play_their_own_side_on_the_nhl_lines(built):
    R = Roster(built.data)
    U, P = R.U, R.P
    right, possible = 0, 0
    for team in range(32):
        ents = [e for e in range(U.cur_rec) if U.get(e, 'team') == team]
        pos = {e: P.get(R.p_by_id[R.link_to_pid[U.get(e, 'playerindex')]], 'position') for e in ents}
        possible += sum(min(4, list(pos.values()).count(side)) for side in (1, 2))
        for k in range(1, 5):
            for slot, want in ((f"l{k}lw", 1), (f"l{k}rw", 2)):
                right += pos[next(e for e in ents if U.get(e, slot))] == want
    assert right >= possible * 0.85                 # a much better winger may still cross over
    chicago = [e for e in range(U.cur_rec) if U.get(e, 'team') == 6]
    rw = [e for e in chicago if P.get(R.p_by_id[R.link_to_pid[U.get(e, 'playerindex')]], 'position') == 2]
    assert len(rw) >= 3 and all(U.get(e, 'rosterstatus') for e in rw)


def test_generic_line_builder_puts_wingers_on_their_side():
    assert lines.wing_side({schema.SLOT_TAG['l2lw'], schema.SLOT_TAG['pp1rw']}) == 1
    assert lines.wing_side({schema.SLOT_TAG['pp1rw']}) == 2
    assert lines.wing_side({schema.SLOT_TAG['l1c']}) is None


def test_generic_line_builder_follows_the_stock_rules(base_bytes):
    R = Roster(base_bytes)
    b = Builder(R, Data())
    for team in (0, 11, 142):                       # two NHL teams and a national team
        slots = lines.build_lines(b, team)
        assert set(slots) == set(schema.LINE_SLOTS)
        dressed = set(slots.values())
        pos = Counter(R.P.get(b.prow_of_entry(e), 'position') for e in dressed)
        assert len(dressed) == 20 and pos[4] == 2 and pos[3] == 6
        assert slots['g1'] != slots['g2'] and {R.P.get(b.prow_of_entry(slots[g]), 'position') for g in ('g1', 'g2')} == {4}
        for group in (schema.EVEN_STRENGTH, schema.POWER_PLAY, schema.POWER_PLAY_4, schema.PENALTY_KILL_4,
                      schema.OVERTIME, schema.SHOOTOUT, schema.EXTRA_ATTACKER):
            holders = [slots[s] for s in group]
            assert len(set(holders)) == len(holders), group
        for e in b.entries_on(team):
            assert bool(R.U.get(e, 'rosterstatus')) == (e in dressed)
        # the best forward leads the first power play and the shootout list is forwards only
        assert all(R.P.get(b.prow_of_entry(slots[s]), 'position') < 3 for s in schema.SHOOTOUT)


def test_line_builder_refuses_a_team_that_cannot_dress_twenty(base_bytes):
    R = Roster(base_bytes)
    b = Builder(R, Data())
    with pytest.raises(lines.NotEnoughPlayers):
        lines.build_lines(b, 132)                   # Valerenga: empty in the base


def test_verify_reports_what_it_is_given(built, base_bytes, data):
    src = Roster(base_bytes)
    R = Roster(built.data)
    R.U.set(0, 'key', R.U.get(1, 'key'))            # two entries with the same id
    R.T.set(40, 'league', 3)                        # an AHL team moved to another league
    problems, _ = verify(R.f.build(), src, data.nhl_players)
    assert "duplicate roster entry ids" in problems
    assert any("changed league" in p for p in problems)
    assert verify(b'not a save', src)[0][0].startswith("the save cannot be read back")


def community_style(base_bytes):
    """The base roster changed the way the community's 2026-27 roster is: the Ducks copy (225) out
    of step with Anaheim (half its players gone, a free agent on it), Italy and France emptied,
    Czech Republic dressed but without line slots."""
    R = Roster(base_bytes)
    U = R.U
    flags = [n for n, f in U.fields.items() if f.bits == 1 and n != 'jZSh']
    ducks = [i for i in range(U.cur_rec) if U.get(i, 'BSXd') == 225]
    U.set(ducks[0], 'TWSX', R.Q.get(0, 'TWSX'))           # someone who is only on the copy
    gone = ducks[1:13] + [i for i in range(U.cur_rec) if U.get(i, 'BSXd') in (139, 142)]
    for i in range(U.cur_rec):
        if U.get(i, 'BSXd') == 136:
            for f in flags:
                U.set(i, f, 0)
    for i in sorted(gone, reverse=True):
        U.delete_record(i)
    return R.f.build()


def test_a_community_roster_with_unfinished_teams_is_updated(base_bytes, data):
    src = community_style(base_bytes)
    L.check_base(Roster(src))                              # recognised by the copy's name
    res = pipeline.build(src, data)
    assert res.problems == []
    R = Roster(res.data)
    assert roster_of(R, 225) == roster_of(R, 0)
    for team in (136, 139, 142):                           # Czech lines dealt; Italy, France refilled (IIHF)
        assert res.info['teams'][team]['dressed'] == 20 and res.info['teams'][team]['slots'] == 71, team
    fa = {R.link_to_pid.get(R.Q.get(i, 'TWSX')) for i in range(R.Q.cur_rec)}
    alone = Roster(src).link_to_pid[Roster(src).Q.get(0, 'TWSX')]
    assert alone in fa and not [i for i in range(R.U.cur_rec) if R.link_to_pid.get(R.U.get(i, 'TWSX')) == alone]
    assert pipeline.build(res.data, data).data == res.data


def test_a_country_without_enough_players_keeps_its_empty_squad(base_bytes, data):
    no_iihf = Data(nhl_players=data.nhl_players, ea_ratings=data.ea_ratings, iihf={}, season_year=data.season_year)
    res = pipeline.build(community_style(base_bytes), no_iihf, steps=['national'])
    assert res.problems == []
    assert res.info['teams'][142]['players'] == 0          # Italy: no IIHF roster, too few Italians in the save
    assert any("left empty" in line and "Italy" in line for line in res.summary())


def test_a_roster_with_some_copies_missing_is_refused_with_an_explanation(base_bytes):
    R = Roster(base_bytes)
    for e in [e for e in range(R.U.cur_rec) if R.U.get(e, 'team') == 229][::-1]:
        R.U.delete_record(e)                        # no Utah copy: neither the community's nor the game's layout
    with pytest.raises(L.LayoutError, match="custom copies"):
        pipeline.build(R.f.build(), Data())
    assert L.check_base(Roster(base_bytes)) == L.COMMUNITY


def test_overall_only_players_land_on_their_overall(built, pack):
    """Someone published with just an overall has his attributes shifted until his level fits it."""
    R = Roster(built.data)
    S = R.f['yvSd']
    rows = {S.get(i, 'game_id'): i for i in range(S.cur_rec)}
    k = ratings.overall_offset(pack['ea_ratings'])[False]
    seen = 0
    for p in pack['ea_ratings']:
        if p['attrs'] or p['position'] == 'G' or not p['birth']:
            continue
        first, _, last = p['name'].partition(' ')
        found = R.find_player(first, last)
        if len(found) != 1 or R.P.get(found[0], 'game_id') not in rows:
            continue
        assert abs(p['ovr'] - k - ratings.level(S, rows[R.P.get(found[0], 'game_id')])) <= 0.5, p['name']
        seen += 1
    assert seen > 200
