"""The player's own edits (edits.py): applied after the update, kept through later updates."""
from legacy_roster import edits, faces, pipeline, verify
from legacy_roster.builder import NHL_COLOURS
from legacy_roster.editor import model
from legacy_roster import layout as L
from legacy_roster.roster import Roster
from legacy_roster.schema import LIST_SKATER, RATING_BASE


def find(R, name):
    return next(i for i in range(R.P.cur_rec) if R.name(i) == name and R.teams_of(i))


def key_of(R, prow):
    return edits.who_of(R.P, prow)


def club_teams(R, prow):
    return sorted(t for _, t in R.teams_of(prow) if t not in L.NATIONAL and t not in L.MIRROR_OF)


def my_edits(built):
    R = Roster(built.data)
    mcd, tkachuk = find(R, 'Connor McDavid'), find(R, 'Matthew Tkachuk')
    was = {'first': 'Connor', 'last': 'McDavid', 'birth': list(edits.birth_of(R.P, mcd))}
    return {
        key_of(R, mcd): {'label': 'Connor McDavid', 'was': was,
                         'set': {'last': 'McDavidson', 'num': 98, 'shoots': 'R'},
                         'ratings': {'Passing': 99, 'Deking': 41}},
        key_of(R, tkachuk): {'label': 'Matthew Tkachuk', 'team': L.API_TO_SLOT['TOR']},
        'nobody|here|1990-01-01': {'label': 'Nobody Here', 'set': {'num': 5}},
        edits.person_key('Puck', 'Peak', (2006, 5, 4)): {
            'label': 'Puck Peak', 'new': True, 'team': L.API_TO_SLOT['EDM'], 'ovr': 70,
            'set': {'first': 'Puck', 'last': 'Peak', 'pos': 'C', 'birth': [2006, 5, 4], 'country': 'SVK', 'num': 77}},
    }


def test_edits_are_applied_after_the_update(base_bytes, data, built):
    mine = my_edits(built)
    res = pipeline.build(base_bytes, data, my_edits=mine)
    assert res.ok, res.problems[:5]
    R = Roster(res.data)
    mcd = find(R, 'Connor McDavidson')
    assert R.P.get(mcd, 'tRVs') == 98 and R.P.get(mcd, 'pkRG') == 1
    assert all(R.U.get(e, 'tRVs') == 98 for e, _ in R.teams_of(mcd))
    row = next(i for i in range(R.f['yvSd'].cur_rec) if R.f['yvSd'].get(i, 'zIBw') == R.P.get(mcd, 'zIBw'))
    assert R.f['yvSd'].get(row, LIST_SKATER['Passing']) == 99 - RATING_BASE
    assert club_teams(R, find(R, 'Matthew Tkachuk')) == [L.API_TO_SLOT['TOR']]
    new = find(R, 'Puck Peak')
    assert club_teams(R, new) == [L.API_TO_SLOT['EDM']] and R.P.get(new, 'tRVs') == 77
    assert any(r[1] == 'edit skipped' and r[2] == 'Nobody Here' for r in res.log)


def test_edits_survive_the_next_update_and_change_nothing_twice(base_bytes, data, built):
    mine = my_edits(built)
    first = pipeline.build(base_bytes, data, my_edits=mine)
    again = pipeline.build(first.data, data, my_edits=mine)
    assert again.ok, again.problems[:5]
    assert again.data == first.data             # McDavidson is not created twice, Puck Peak not again
    R = Roster(again.data)
    assert sum(1 for i in range(R.P.cur_rec) if R.name(i) == 'Puck Peak') == 1


def test_a_refused_edit_changes_nothing(base_bytes, data, built):
    R = Roster(built.data)
    goalie = next(p for _, p, *_ in R.team_roster(L.API_TO_SLOT['EDM']) if R.P.get(p, 'aljv') == 4)
    full = next(t for t in range(R.T.cur_rec) if len(R.team_roster(t)) >= L.MAX_PER_TEAM and t not in L.MIRROR_OF)
    skater = find(R, 'Leon Draisaitl')
    mine = {key_of(R, goalie): {'label': 'goalie', 'set': {'pos': 'C'}},
            key_of(R, skater): {'label': 'Leon Draisaitl', 'team': full}}
    res = pipeline.build(built.data, data, my_edits=mine)
    assert res.ok
    after = Roster(res.data)
    assert after.P.get(goalie, 'aljv') == 4
    assert club_teams(after, find(after, 'Leon Draisaitl')) == [L.API_TO_SLOT['EDM']]
    assert sum(1 for r in res.log if r[1] == 'edit skipped') == 2


def test_edits_are_kept_on_the_pc(tmp_path):
    f = str(tmp_path / 'edits.json')
    assert edits.load(f) == {}
    edits.save({'a|b|2000-01-01': {'label': 'A B', 'set': {'num': 9}}}, f)
    edits.save(file=f, teams={'5': {'full': 'X'}})                # saving teams keeps the players
    assert edits.load(f)['a|b|2000-01-01']['set'] == {'num': 9} and edits.load_teams(f) == {'5': {'full': 'X'}}


def test_a_teams_colours_and_arena_from_the_jerseys_tab_reach_the_roster(base_bytes, data):
    """The Jerseys & ice tab's Main / Second colour and arena name are written into the team table and the arena table
    (the game's menus read them there), also with no update step (the Roster editor's Save), and a second build is the same."""
    teams = {'1': {'uniforms': {'colours': {'primary': '#112233'}}, 'ice': {'arena': 'Test Arena™'}},       # Winnipeg
             '0': {'ice': {'arena': 'Ducks Pond'}}}                                                         # Anaheim
    for steps in ([], pipeline.ALL_STEPS):                  # the editor's Save, and an update (the edit beats the NHL table)
        res = pipeline.build(base_bytes, data, steps=steps, team_edits=teams)
        assert res.ok, res.problems[:5]
        R, src = Roster(res.data), Roster(base_bytes)
        T, A = R.T, R.f['OEtS']
        assert tuple(T.get(1, f"primarycolor_{c}") for c in 'rgb') == (17, 34, 51)
        second = tuple(src.T.get(1, f"secondarycolor_{c}") for c in 'rgb') if not steps else NHL_COLOURS[1][1]
        assert tuple(T.get(1, f"secondarycolor_{c}") for c in 'rgb') == second                              # not given
        assert A.get(T.get(1, 'arenaid'), 'arenaname') == 'Test Arena™'
        assert T.get(44, 'arenaid') == src.T.get(44, 'arenaid') != T.get(1, 'arenaid')                       # Manitoba's own row
        assert A.get(T.get(44, 'arenaid'), 'arenaname') == src.f['OEtS'].get(src.T.get(44, 'arenaid'), 'arenaname') \
            or steps                                                                                         # (an update renames it)
        assert A.get(T.get(0, 'arenaid'), 'arenaname') == A.get(T.get(225, 'arenaid'), 'arenaname') == 'Ducks Pond'   # its copy
        assert pipeline.build(res.data, data, steps=steps, team_edits=teams).data == res.data


def test_a_team_edit_renames_the_team_and_gives_it_a_logo(base_bytes, data, pack, tmp_path):
    from legacy_roster.art import portraits
    from legacy_roster.builder import Data
    edm = L.API_TO_SLOT['EDM']
    teams = {str(edm): {'full': 'Edmonton Puckers', 'city': 'Edmonton', 'abbr': 'EPK', 'logo': 'file:C:/logo.png'}}
    d = Data(nhl_players=data.nhl_players, ratings_list=data.ratings_list, iihf=data.iihf, season_year=data.season_year,
             leagues=pack['leagues'], nhl_logos=pack['nhl_logos'])
    res = pipeline.build(base_bytes, d, steps=pipeline.steps_for(pack), team_edits=teams,
                         art_registry=portraits.Registry(str(tmp_path / 'ids.json')))
    assert res.ok
    R = Roster(res.data)
    assert R.T.get(edm, 'fullname') == 'Edmonton Puckers' and R.T.get(edm, 'abbrname') == 'EPK'
    _photos, logos, names = res.art
    assert logos[R.T.get(edm, 'artid')][0] == 'file:C:/logo.png'
    art = R.T.get(edm, 'artabbr')
    assert any(t[0] == art and t[1] == 'Edmonton Puckers' for t in names['teams']) and art in names['force']
    # the prospect pools get logos of their own: an NHL team's for a "System" pool, a badge for a draft class
    pools = {R.team_name(s): logos.get(R.T.get(s, 'artid'), (None,))[0] for s in L.SPARE if R.team_roster(s)}
    assert pools and all(v for v in pools.values())
    assert all(v.startswith('badge:') for k, v in pools.items() if k[:4].isdigit())
    assert len({R.T.get(s, 'artid') for s in L.SPARE if R.team_roster(s)}) == len(pools)


def test_the_editor_shows_the_roster_as_it_is_and_only_the_edits_made_now(base_bytes, built):
    """The Roster editor has no "To be": the view is the roster plus this visit's edits, nothing else
    changes (model.apply_edits builds with no update step)."""
    mine = my_edits(built)
    nothing = model.apply_edits(base_bytes, {}, {}, 2026)
    assert nothing.ok and nothing.data == base_bytes                    # no edit, no change
    R0 = Roster(base_bytes)
    mcd = find(R0, 'Connor McDavid')
    one = {k: v for k, v in mine.items() if v['label'] == 'Connor McDavid'}
    res = model.apply_edits(base_bytes, one, {}, 2026)
    assert res.ok, res.problems[:3]
    before, after = model.Snapshot(base_bytes), model.Snapshot(res.data)
    changed = {p.name for t in range(32) for p in after.roster(t)} ^ {p.name for t in range(32) for p in before.roster(t)}
    assert changed == {'Connor McDavid', 'Connor McDavidson'}           # only the edited player differs
    assert Roster(res.data).P.get(find(Roster(res.data), 'Connor McDavidson'), 'tRVs') == 98


def test_a_rating_edit_reaches_the_national_team_copy_of_a_player(base_bytes, data, built):
    """A person on a club and on a national team (23 goalies) has two player records: both get the edit."""
    from legacy_roster.schema import LIST_GOALIE
    R = Roster(built.data)
    by_person = {}
    for prow in range(R.P.cur_rec):
        if R.teams_of(prow):
            by_person.setdefault(key_of(R, prow), []).append(prow)
    who, rows = next((w, r) for w, r in by_person.items()
                     if len(r) == 2 and all(R.P.get(x, 'aljv') == 4 for x in r)
                     and any(t in L.NATIONAL for x in r for _, t in R.teams_of(x))
                     and any(t not in L.NATIONAL for x in r for _, t in R.teams_of(x)))
    label = next(iter(LIST_GOALIE))
    res = pipeline.build(built.data, data, my_edits={who: {'label': 'goalie', 'ratings': {label: 91}}})
    assert res.ok, res.problems[:5]
    R2, table = Roster(res.data), 'yuHm'
    for prow in rows:
        pid = R.P.get(prow, 'zIBw')
        row = next(i for i in range(R2.f[table].cur_rec) if R2.f[table].get(i, 'zIBw') == pid)
        assert R2.f[table].get(row, LIST_GOALIE[label]) == 91 - RATING_BASE


def test_equipment_edits_reach_the_player_and_his_team_and_change_nothing_twice(base_bytes, data, built):
    from legacy_roster import equipment
    R = Roster(built.data)
    mcd, tkachuk = find(R, 'Connor McDavid'), find(R, 'Matthew Tkachuk')
    edm = L.API_TO_SLOT['EDM']
    mine = {key_of(R, mcd): {'label': 'Connor McDavid',
                             'equipment': {'stick': 105, 'tape': 9, 'sock_tuck': 3, 'jersey_tuck': 2, 'shoulder_pads': 1,
                                  'pant_length': 1, 'visor_tint': 6, 'bogus': 5}}}
    teams = {str(edm): {'equipment': {'tape': 0, 'sock_tuck': 2, 'stick': 99}}}      # stick is not team-wide
    first = pipeline.build(base_bytes, data, my_edits=mine, team_edits=teams)
    assert first.ok, first.problems[:5]
    R = Roster(first.data)
    table = R.f[equipment.TABLE]
    rows = equipment.row_of(table)
    got = equipment.read(table, rows[R.P.get(find(R, 'Connor McDavid'), 'zIBw')])
    assert got['stick'] == 105 and got['tape'] == 9 and got['sock_tuck'] == 3 and got['jersey_tuck'] == 2
    assert got['shoulder_pads'] == 1 and got['pant_length'] == 1 and got['visor_tint'] == 6
    tucks = {equipment.read(table, rows[R.P.get(p, 'zIBw')])['sock_tuck']
              for _, p, _, _, _ in R.team_roster(edm) if p is not None and R.P.get(p, 'aljv') != 4 and p != find(R, 'Connor McDavid')}
    assert tucks == {2}
    assert any(r[1] == 'edit skipped' and 'bogus' in r[3] for r in first.log)
    again = pipeline.build(first.data, data, my_edits=mine, team_edits=teams)
    assert again.ok and again.data == first.data


def test_goalie_equipment_and_a_mask_picture_get_a_mask_number_nobody_wears(base_bytes, data, built):
    from legacy_roster import equipment
    R = Roster(built.data)
    goalie = find(R, 'Connor Hellebuyck')
    mine = {key_of(R, goalie): {'label': 'Connor Hellebuyck', 'mask_picture': 'file:C:/nowhere/mask.png',
                                'equipment': {'pads': 11, 'tape': 0, 'neck': 1, 'blocker': 12, 'bogus': 1}}}
    first = pipeline.build(base_bytes, data, my_edits=mine)
    assert first.ok, first.problems[:5]
    R = Roster(first.data)
    table = R.f[equipment.GOALIE_TABLE]
    row = equipment.row_of(table, 'goalie')[R.P.get(find(R, 'Connor Hellebuyck'), 'zIBw')]
    got = equipment.read(table, row, 'goalie')
    assert got['pads'] == 11 and got['tape'] == 0 and got['neck'] == 1 and got['blocker'] == 12   # models the game draws
    wears = [equipment.read(table, i, 'goalie')['mask'] for i in range(table.cur_rec) if i != row
             and table.get(i, equipment.GOALIE_CODE[equipment.MASK_TYPE]) == 0]
    assert wears.count(got['mask']) <= 1 and got['mask'] not in equipment.MASK_FILES_MISSING      # at most his national-team copy
    assert table.get(row, equipment.GOALIE_CODE[equipment.MASK_TYPE]) == 0
    assert first.builder.mask_looks == {got['mask']: 'file:C:/nowhere/mask.png'}
    assert any(r[1] == 'edit skipped' and 'bogus' in r[3] for r in first.log)
    again = pipeline.build(first.data, data, my_edits=mine)
    assert again.ok and again.data == first.data


def test_a_team_left_short_of_players_keeps_its_letters(base_bytes, data, built):
    """Moving a goalie off a team that then cannot dress 20 must not strip its captain and alternates
    (the safety check refused to save such a roster: 'has 0 captain(s) and 0 alternate(s)')."""
    R = Roster(built.data)
    team = L.API_TO_SLOT['SEA']
    goalies = [p for _, p, *_ in R.team_roster(team) if R.P.get(p, 'aljv') == 4]
    mine = {key_of(R, goalies[0]): {'label': 'goalie', 'team': L.API_TO_SLOT['EDM']}}
    res = pipeline.build(built.data, data, my_edits=mine)
    assert res.ok, res.problems[:5]
    skipped = [r for r in res.log if r[1] == 'edit skipped']
    assert skipped and 'would have only 1 goalie' in skipped[0][3]
    assert club_teams(Roster(res.data), goalies[0]) == [team]


def _style(R, prow):
    S, pid = R.f['yvSd'], R.P.get(prow, 'zIBw')
    return next(S.get(i, 'sFgQ') for i in range(S.cur_rec) if S.get(i, 'zIBw') == pid)


def test_type_and_face_edits_reach_the_player_and_his_copies_and_change_nothing_twice(data, built):
    R = Roster(built.data)
    mcd, makar, crosby = find(R, 'Connor McDavid'), find(R, 'Cale Makar'), find(R, 'Sidney Crosby')
    face = faces.read(R.P, crosby)
    drai = find(R, 'Leon Draisaitl')
    mine = {key_of(R, mcd): {'label': 'Connor McDavid', 'set': {'style': 7, **face}},
            key_of(R, makar): {'label': 'Cale Makar', 'set': {'style': 2}},
            key_of(R, drai): {'label': 'Leon Draisaitl', 'set': {'style': 2, 'head': 77}}}
    first = pipeline.build(built.data, data, my_edits=mine)
    assert first.ok, first.problems[:5]
    A = Roster(first.data)
    for name, style in (('Connor McDavid', 7), ('Cale Makar', 2)):
        rows = [i for i in range(A.P.cur_rec) if A.name(i) == name and A.teams_of(i)]
        for prow in rows:               # his club record and his national-team copy
            assert _style(A, prow) == style
            assert all(A.U.get(e, 'sFgQ') == style for e, _ in A.teams_of(prow))
    assert faces.read(A.P, find(A, 'Connor McDavid')) == face
    assert _style(A, find(A, 'Leon Draisaitl')) == _style(R, drai)       # a defence type on a forward: skipped
    assert faces.read(A.P, find(A, 'Leon Draisaitl')) == faces.read(R.P, drai)   # no head 77 in the game
    assert sum(1 for r in first.log if r[1] == 'edit skipped' and r[2] == 'Leon Draisaitl') == 2
    again = pipeline.build(first.data, data, my_edits=mine)
    assert again.data == first.data


def test_verify_refuses_a_type_or_face_the_game_does_not_have(built):
    R = Roster(built.data)
    makar = find(R, 'Cale Makar')
    S, pid = R.f['yvSd'], R.P.get(makar, 'zIBw')
    S.set(next(i for i in range(S.cur_rec) if S.get(i, 'zIBw') == pid), 'sFgQ', 7)
    R.P.set(makar, 'DaPp', 77)
    R.P.set(makar, 'QDTK', 0)
    problems, _ = verify.verify(R.f.build(), Roster(built.data))
    assert "Cale Makar has player type 7, which no defenceman has" in problems
    assert any(p.startswith("Cale Makar: a roster place shows another player type") for p in problems)
    assert "Cale Makar: head 77 is not one of the game's heads" in problems
