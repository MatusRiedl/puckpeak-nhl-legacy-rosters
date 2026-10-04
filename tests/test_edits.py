"""The player's own edits (edits.py): applied after the update, kept through later updates."""
from legacy_roster import edits, pipeline
from legacy_roster import layout as L
from legacy_roster.roster import Roster
from legacy_roster.schema import EA_SKATER, RATING_BASE


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
    assert R.f['yvSd'].get(row, EA_SKATER['Passing']) == 99 - RATING_BASE
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


def test_a_team_edit_renames_the_team_and_gives_it_a_logo(base_bytes, data, pack, tmp_path):
    from legacy_roster.art import portraits
    from legacy_roster.builder import Data
    edm = L.API_TO_SLOT['EDM']
    teams = {str(edm): {'full': 'Edmonton Puckers', 'city': 'Edmonton', 'abbr': 'EPK', 'logo': 'file:C:/logo.png'}}
    d = Data(nhl_players=data.nhl_players, ea_ratings=data.ea_ratings, iihf=data.iihf, season_year=data.season_year,
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
