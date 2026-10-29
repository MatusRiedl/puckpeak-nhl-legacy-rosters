"""Free editing (owner, 2026-10-29: "allow everything possible that will not really break the roster from loading"): the
player's own edits save whatever only our caution refused (a defence type on a forward, a team left short, players
released, a created player, a team of 40); what would stop the roster loading still refuses every save (41 on a team, a
player listed twice). A team the edits leave short gets one heads-up line (the game hangs its first game)."""
from legacy_roster import edits, layout as L, verify
from legacy_roster.builder import Builder, Data
from legacy_roster.editor import model
from legacy_roster.roster import Roster


def find(R, name):
    return next(i for i in range(R.P.cur_rec) if R.name(i) == name and R.teams_of(i))


def key_of(R, prow):
    return edits.who_of(R.P, prow)


def _style(R, prow):
    S, pid = R.f['yvSd'], R.P.get(prow, 'zIBw')
    return next(S.get(i, 'sFgQ') for i in range(S.cur_rec) if S.get(i, 'zIBw') == pid)


def _club(R, prow):
    return sorted(t for _, t in R.teams_of(prow) if t not in L.NATIONAL and t not in L.MIRROR_OF)


def go_nuts(R):
    """A created player, a defence type on a forward, Seattle's goalies to Edmonton (Seattle left short), five
    Torontos released, Anaheim filled to 40 from a CHL club."""
    sea, edm, tor, ana = (L.API_TO_SLOT[k] for k in ('SEA', 'EDM', 'TOR', 'ANA'))
    mine = {key_of(R, find(R, 'Leon Draisaitl')): {'label': 'Leon Draisaitl', 'set': {'style': 2}},
            edits.person_key('Puck', 'Peak', (2006, 5, 4)): {
                'label': 'Puck Peak', 'new': True, 'team': edm, 'ovr': 70,
                'set': {'first': 'Puck', 'last': 'Peak', 'pos': 'C', 'birth': [2006, 5, 4], 'country': 'SVK', 'num': 77}}}
    for _, p, *_ in R.team_roster(sea):
        if R.P.get(p, 'aljv') == 4:
            mine[key_of(R, p)] = {'label': R.name(p), 'team': edm}
    for _, p, *_ in R.team_roster(tor)[:5]:
        mine[key_of(R, p)] = {'label': R.name(p), 'team': 'FA'}
    room = L.MAX_PER_TEAM - len(R.team_roster(ana))
    chl = next(t for t in range(R.T.cur_rec) if t not in L.NHL_PRIMARY and t not in L.NATIONAL
               and t not in L.MIRROR_OF and len(R.team_roster(t)) >= room + 5 and t > 100)
    for _, p, *_ in R.team_roster(chl)[:room]:
        mine.setdefault(key_of(R, p), {'label': R.name(p), 'team': ana})
    return mine, chl


def test_a_go_nuts_roster_saves_and_a_second_save_changes_nothing(built):
    R = Roster(built.data)
    mine, chl = go_nuts(R)
    first = model.apply_edits(built.data, mine, {}, 2026)
    assert first.problems == [], first.problems[:5]
    A = Roster(first.data)
    assert _style(A, find(A, 'Leon Draisaitl')) == 2                 # a defence type on a forward
    assert _club(A, find(A, 'Puck Peak')) == [L.API_TO_SLOT['EDM']]
    assert len(A.team_roster(L.API_TO_SLOT['ANA'])) == L.MAX_PER_TEAM
    assert not [p for _, p, *_ in A.team_roster(L.API_TO_SLOT['SEA']) if A.P.get(p, 'aljv') == 4]
    heads = first.info['heads_up']
    assert any(verify._team(A, L.API_TO_SLOT['SEA']) in line and '0 goalies' in line for line in heads), heads
    assert ("Heads up", heads[0]) in first.lines()
    again = model.apply_edits(first.data, mine, {}, 2026)
    assert again.problems == [] and again.data == first.data


def test_the_roster_as_it_is_gets_no_heads_up(built):
    assert model.apply_edits(built.data, {}, {}, 2026).info['heads_up'] == []


def _over(built, how):
    R = Roster(built.data)
    b = Builder(R, Data(season_year=2026))
    team = L.API_TO_SLOT['EDM']
    if how == '41':
        others = (p for p in range(R.P.cur_rec) if R.P.get(p, 'aljv') != 4 and not R.teams_of(p))
        while len(b.entries_on(team)) <= L.MAX_PER_TEAM:
            p = next(others)
            b.new_entry(team, b.new_link(R.P.get(p, 'zIBw')), p)
        return R.f.build()          # (finish() itself refuses a 41st: the builder never makes one)
    p = find(R, 'Connor McDavid')
    b.new_entry(team, b.new_link(R.P.get(p, 'zIBw')), p)
    b.finish()
    return R.f.build()


def test_what_breaks_loading_still_refuses_a_free_save(built):
    source = Roster(built.data)
    problems, _ = verify.verify(_over(built, '41'), source, free=True)
    assert any(f"(the game allows {L.MAX_PER_TEAM})" in p or 'duplicate roster entry ids' in p for p in problems), problems[:5]
    problems, _ = verify.verify(_over(built, 'twice'), source, free=True)
    assert any("lists Connor McDavid 2 times" in p for p in problems), problems[:5]


def test_only_the_players_own_edits_are_free(built):
    """The same defence type on a forward: free when the player's edits did it, our bug when the builder did."""
    R = Roster(built.data)
    drai = find(R, 'Leon Draisaitl')
    S, pid = R.f['yvSd'], R.P.get(drai, 'zIBw')
    S.set(next(i for i in range(S.cur_rec) if S.get(i, 'zIBw') == pid), 'sFgQ', 2)
    for e, _ in R.teams_of(drai):
        R.U.set(e, 'sFgQ', 2)
    data = R.f.build()
    blamed = [p for p in verify.verify(data, Roster(built.data))[0] if 'Draisaitl' in p]
    assert blamed
    assert not [p for p in verify.verify(data, Roster(built.data), free=({drai}, set()))[0] if 'Draisaitl' in p]
    assert not [p for p in verify.verify(data, Roster(built.data), free=True)[0] if 'Draisaitl' in p]
