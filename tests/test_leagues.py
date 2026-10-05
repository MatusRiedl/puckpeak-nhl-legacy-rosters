"""Club leagues: real clubs put back into the slots the base roster uses for prospect pools."""
import difflib
from collections import Counter

import pytest

from legacy_roster import layout as L
from legacy_roster import pipeline, ratings, schema
from legacy_roster.builder import Data
from legacy_roster.leagues import pools
from legacy_roster.matching import match_club, norm, same_first_name
from legacy_roster.roster import Roster


@pytest.fixture(scope='module')
def everything(base_bytes, data, pack):
    full = Data(nhl_players=data.nhl_players, ea_ratings=data.ea_ratings, iihf=data.iihf,
                season_year=data.season_year, leagues=pack['leagues'], drafts=pack.get('drafts'))
    return full, pipeline.build(base_bytes, full, steps=pipeline.steps_for(pack))


def clubs_of(pack):
    """Every club of every league in the data pack, with its league id (per club in the CHL)."""
    return [dict(team, league_id=team.get('league_id', league.get('league_id')))
            for league in pack['leagues'].values() for team in league['teams']]


# how far below the NHL a league's median player sits (rating points); juniors are far below,
# Switzerland's league is the closest
GAP = {'chl': (9, 20), 'nl': (2, 10)}


def free_agents(R):
    return {R.link_to_pid[R.Q.get(k, 'playerindex')] for k in range(R.Q.cur_rec)}


def members(R, team):
    return [R.p_by_id[R.link_to_pid[R.U.get(e, 'playerindex')]] for e in range(R.U.cur_rec) if R.U.get(e, 'team') == team]


def test_the_build_with_club_leagues_passes_every_check(everything):
    _, result = everything
    assert result.problems == []
    assert result.builder.league_stats['liiga']['created'] > 300


def test_every_club_has_its_real_name_and_its_listed_players(everything, pack):
    _, result = everything
    R = Roster(result.data)
    names = lambda rows: {(norm(R.P.get(r, 'firstname')), norm(R.P.get(r, 'lastname'))) for r in rows}
    in_the_nhl = names(r for t in range(32) for r in members(R, t))
    skipped = {norm(r[2]) for r in result.log if r[1] == 'skipped'}
    fillers = {}
    for r in result.log:
        if r[1] in ('stays to fill the line-up', 'signed to fill the line-up', 'stays', 'prospect joined'):
            fillers.setdefault(r[0], []).append(r[2])
    on_some_club = set()
    for team in clubs_of(pack):
        on_some_club |= names(members(R, team['slot']))
    near = lambda last, lasts: any(difflib.SequenceMatcher(None, last, n).ratio() >= 0.8 for n in lasts)
    for team in clubs_of(pack):
        slot = team['slot']
        assert R.T.get(slot, 'fullname') == team['full'] and R.T.get(slot, 'artabbr') == team['art']
        assert R.T.get(slot, 'league') == team['league_id']
        on_club = names(members(R, slot))
        listed = {(norm(p['first']), norm(p['last'])) for p in team['players']}
        # A player already in the save keeps the save's spelling of his name (Trent for Trenton,
        # Gueby for Guebey), so last names are compared loosely. A club may lack only players
        # NHL.com has on an NHL roster, players another league listed first, and players no record
        # was left for; it may hold extra players only to fill its line-up.
        missing = {p for p in listed - on_club if not near(p[1], {last for _, last in on_club})}
        assert {p for p in missing - in_the_nhl - on_some_club if p[0] + p[1] not in skipped} == set(), team['full']
        filled = {norm(n) for n in fillers.get(team['abbr'], [])}         # whole names: "Ian Luca" Scheerschmidt
        assert not {p for p in on_club - listed if p[0] + p[1] not in filled
                    and not near(p[1], {last for _, last in listed})}, team['full']


def test_every_club_is_playable(everything, pack):
    _, result = everything
    R = Roster(result.data)
    U, P = R.U, R.P
    junior = {t['slot'] for t in pack['leagues'].get('chl', {}).get('teams', [])}
    for team in clubs_of(pack):
        slot = team['slot']
        if slot not in result.info['rebuilt_teams']:
            # only a junior club, last in line for player records, may end up unable to dress 20
            assert slot in junior, team['full']
            continue
        ents = [e for e in range(U.cur_rec) if U.get(e, 'team') == slot]
        dressed = [e for e in ents if U.get(e, 'rosterstatus')]
        pos = Counter(P.get(R.p_by_id[R.link_to_pid[U.get(e, 'playerindex')]], 'position') for e in dressed)
        assert 20 <= len(ents) <= L.MAX_PER_TEAM
        assert (len(dressed), pos[4], pos[3]) == (20, 2, 6)
        assert all(sum(U.get(e, s) for e in ents) == 1 for s in schema.LINE_SLOTS)
        assert sorted(U.get(e, 'captain') for e in ents if U.get(e, 'captain')) == [1, 2, 2]
        numbers = [U.get(e, 'jersey') for e in ents]
        assert len(set(numbers)) == len(numbers) and 0 not in numbers


def test_a_club_player_is_under_contract_to_his_club_only(everything, pack):
    _, result = everything
    R = Roster(result.data)
    for team in clubs_of(pack):
        for r in members(R, team['slot']):
            assert R.P.get(r, 'team') == team['slot'] + 1
            clubs = [t for _, t in R.teams_of(r) if t not in L.NATIONAL]
            assert clubs == [team['slot']], R.name(r)                 # one club, national team aside


def test_club_players_are_rated_below_the_nhl_but_not_absurdly(everything, pack):
    _, result = everything
    R = Roster(result.data)
    S = R.f['yvSd']
    rows = {S.get(i, 'game_id'): i for i in range(S.cur_rec)}

    def median_level(teams):
        levels = sorted(ratings.level(S, rows[R.P.get(r, 'game_id')]) for t in teams for r in members(R, t)
                        if R.P.get(r, 'game_id') in rows)
        return levels[len(levels) // 2]
    nhl = median_level(range(32))
    for key, league in pack['leagues'].items():
        gap = nhl - median_level(t['slot'] for t in league['teams'])
        low, high = GAP.get(key, (4, 12))
        assert low < gap < high, league['label']


def test_displaced_pools_move_to_spare_custom_slots_and_no_slot_changes_league(everything, base_bytes, pack):
    _, result = everything
    src, R = Roster(base_bytes), Roster(result.data)
    assert R.T.column('league') == src.T.column('league') and R.T.cur_rec == src.T.cur_rec
    assert not any(src.T.get(t, 'active') for t in pools.SPARE_SLOTS)    # switched off in the base
    rebuilt = [team['slot'] for team in clubs_of(pack)]
    pool_slots = [t for t in rebuilt if pools.is_pool(src, t)]
    pool_names = {src.T.get(t, 'fullname') for t in pool_slots}
    assert pool_slots and not any(pools.is_pool(R, t) for t in rebuilt)  # the clubs have their names back
    assert not any(pools.is_pool(src, t) for t in L.EVENTS)              # "Top Prospects" teams are no pools
    spare = [t for t in pools.SPARE_SLOTS if R.T.get(t, 'active')]
    assert {R.T.get(t, 'fullname') for t in spare} <= pool_names          # a spare slot takes a pool's name
    before = {src.P.get(r, 'game_id') for t in pool_slots for r in members(src, t)}
    after = {R.P.get(r, 'game_id') for t in spare for r in members(R, t)}
    on_a_team = {R.P.get(r, 'game_id') for t in range(R.T.cur_rec) if t not in L.NATIONAL for r in members(R, t)}
    assert after <= before
    # nobody was lost: every displaced pool player is on a team or a free agent who can be signed
    assert before - on_a_team <= free_agents(R)
    assert all(len(members(R, t)) <= L.MAX_PER_TEAM for t in spare)


def test_released_players_are_free_agents_without_a_contract_and_keep_their_rights(everything, base_bytes):
    _, result = everything
    R, src = Roster(result.data), Roster(base_bytes)
    rights_before = {src.P.get(r, 'game_id'): src.P.get(r, 'proteam') for r in range(src.P.cur_rec)}
    for pid in free_agents(R):
        r = R.p_by_id[pid]
        assert not R.P.get(r, 'team') and not R.P.get(r, 'contractlength'), R.name(r)
        assert not [t for _, t in R.teams_of(r) if t not in L.NATIONAL], R.name(r)
        assert R.P.get(r, 'proteam') == rights_before.get(pid, R.P.get(r, 'proteam')), R.name(r)


def test_ahl_players_on_nhl_contracts_belong_to_the_parent_club(everything, pack):
    if 'ahl' not in pack['leagues']:
        pytest.skip("the data pack has no AHL rosters")
    _, result = everything
    R = Roster(result.data)
    parent = {R.T.get(n, 'ahlaffiliate') - 1: n for n in range(32) if R.T.get(n, 'ahlaffiliate')}
    parent.update(L.AHL_PARENT_EXTRA)
    checked = 0
    for team in pack['leagues']['ahl']['teams']:
        nhl_signed = {(norm(p['first']), norm(p['last'])) for p in team['players'] if p.get('nhl_contract')}
        for r in members(R, team['slot']):
            assert R.P.get(r, 'team') == team['slot'] + 1, R.name(r)
            if (norm(R.P.get(r, 'firstname')), norm(R.P.get(r, 'lastname'))) in nhl_signed and parent[team['slot']] < 31:
                assert R.P.get(r, 'proteam') == parent[team['slot']] + 1, R.name(r)
                assert R.P.get(r, 'contractlength') and R.P.get(r, 'contractdollars'), R.name(r)
                checked += 1
    assert checked > 300


def test_a_second_run_with_club_leagues_changes_nothing(everything, pack):
    full, result = everything
    again = pipeline.build(result.data, full, steps=pipeline.steps_for(pack))
    assert again.problems == [] and again.data == result.data


def test_a_league_can_be_added_later_on_its_own(built, pack):
    later = pipeline.build(built.data, Data(season_year=pack['season'], leagues=pack['leagues']), steps=['liiga'])
    assert later.problems == []
    R, before = Roster(later.data), Roster(built.data)
    for t in range(32):
        assert sorted(members(R, t)) == sorted(members(before, t))           # NHL rosters untouched


def test_running_out_of_player_records_skips_players_instead_of_failing(built, pack, monkeypatch):
    from legacy_roster import donors
    taken = []
    real_take = donors.Donors.take

    def scarce(self, pos, target=None):        # only 40 new players fit in this save
        if len(taken) >= 40:
            return None
        taken.append(pos)
        return real_take(self, pos, target)
    monkeypatch.setattr(donors.Donors, 'take', scarce)
    said = []
    data = Data(season_year=pack['season'], leagues=pack['leagues'])
    later = pipeline.build(built.data, data, steps=['shl'], progress=said.append)
    assert later.problems == []
    skipped = later.builder.league_stats['shl']['skipped: no free record']
    assert skipped > 0 and len([r for r in later.log if r[1] == 'skipped']) == skipped
    assert any('no free player record left' in s for s in said)


def test_first_names_keep_twins_apart():
    assert same_first_name('matt', 'matthew') and same_first_name('yegor', 'egor') and same_first_name('mikko', 'mikko')
    assert not same_first_name('julius', 'jesper') and not same_first_name('daniel', 'henrik')


def test_club_matching_needs_the_birthdate_to_agree(base_bytes):
    R = Roster(base_bytes)
    row = next(r for r in range(R.P.cur_rec) if R.entries_by_pid.get(R.P.get(r, 'game_id')) and 'ZZ' not in R.P.get(r, 'lastname'))
    first, last = R.P.get(row, 'firstname'), R.P.get(row, 'lastname')
    birth = (R.P.get(row, 'year') + 1910, R.P.get(row, 'month') + 1, R.P.get(row, 'day') + 1)
    same, namesake, twin = ({'first': first, 'last': last, 'birth': birth},
                            {'first': first, 'last': last, 'birth': (birth[0] - 6, birth[1] % 12 + 1, birth[2])},
                            {'first': 'Xavier-Quentin', 'last': last, 'birth': birth})
    match_club(R, [same, namesake, twin])
    assert same['row'] == row and not same['stale']
    assert namesake['row'] is None and twin['row'] is None


def test_a_players_own_team_named_after_a_left_out_club_gets_its_players(base_bytes, pack):
    """Point 7 of the testers (0.7.0): the game has no slot for Jokerit; a custom team the player made
    and named after it gets Jokerit's players, and keeps its league, name and city."""
    extra = {c['full']: c for c in pack['leagues']['liiga'].get('extra', [])}
    assert 'Jokerit' in extra
    R = Roster(base_bytes)
    T = R.T
    slot = next(t for t in pools.SPARE_SLOTS if not T.get(t, 'NYKk')
                and not any(R.U.get(i, 'BSXd') == t for i in range(R.U.cur_rec)))
    T.set(slot, 'NYKk', 1)
    T.set(slot, 'JkmY', 'Jokerit Helsinki')
    T.set(slot, 'shortname', 'HELSINKI')
    league_before = T.get(slot, 'league')
    res = pipeline.build(R.f.build(), Data(season_year=pack['season'], leagues=pack['leagues']), steps=['liiga'])
    assert res.problems == []
    after = Roster(res.data)
    assert after.T.get(slot, 'league') == league_before == L.CUSTOM_LEAGUE
    assert after.T.get(slot, 'JkmY') == 'Jokerit Helsinki' and after.T.get(slot, 'shortname') == 'HELSINKI'
    names = {(norm(after.P.get(r, 'firstname')), norm(after.P.get(r, 'lastname'))) for r in members(after, slot)}
    listed = {(norm(p['first']), norm(p['last'])) for p in extra['Jokerit']['players']}
    assert len(names & listed) >= 20
    assert any(r[1] == 'summary' and 'your own team' in str(r[2]) for r in res.log)


def test_an_own_team_with_another_name_is_left_alone(base_bytes, pack):
    R = Roster(base_bytes)
    T = R.T
    slot = next(t for t in pools.SPARE_SLOTS if not T.get(t, 'NYKk')
                and not any(R.U.get(i, 'BSXd') == t for i in range(R.U.cur_rec)))
    T.set(slot, 'NYKk', 1)
    T.set(slot, 'JkmY', 'Bratislava Dragons')
    res = pipeline.build(R.f.build(), Data(season_year=pack['season'], leagues=pack['leagues']), steps=['liiga'])
    assert res.problems == [] and not members(Roster(res.data), slot)


def test_a_junior_the_list_leaves_out_stays_with_his_club(everything):
    """Testers, 0.8.0: the WHL's 2026-27 list has no Landon DuPont (2027's top prospect); as a free
    agent the draft would not see him, so a junior under 20 stays with his club."""
    _, result = everything
    R = Roster(result.data)
    rows = [r for r in range(R.P.cur_rec) if (R.P.get(r, 'firstname'), R.P.get(r, 'lastname')) == ('Landon', 'Dupont')]
    assert rows and [R.team_name(t) for _, t in R.teams_of(rows[0])] == ['Everett Silvertips']
    assert result.builder.league_stats['chl']['juniors kept'] > 0


def test_the_draft_test_puts_prospects_in_six_places(everything, pack):
    from legacy_roster.art import lab
    _, result = everything
    built, groups = lab.draft_lab(result.data, pack['season'])
    assert len(groups) == len(lab.DRAFT_GROUPS) and all(len(names) == 2 for _, names in groups)
    R = Roster(built)
    fa = free_agents(R)
    where = dict(zip([k for k, _ in lab.DRAFT_GROUPS], [names for _, names in groups]))
    find = lambda name: next(r for r in range(R.P.cur_rec) if R.name(r) == name)
    for name in where['fa']:
        assert R.P.get(find(name), 'game_id') in fa and not R.teams_of(find(name))
    for name in where['top']:
        assert [t for _, t in R.teams_of(find(name))] == [lab.TOP_PROSPECTS_RED]
    for name in where['whl-no-year']:
        assert R.P.get(find(name), 'draftyear') == 255
    for name in where['whl'] + where['liiga']:
        assert R.P.get(find(name), 'draftyear') == pack['season'] + 1 - 1900


def test_undrafted_prospects_play_for_real_clubs_of_their_country(everything, pack):
    """Owner, 0.8.0: the community's prospect pools end up on custom teams, where the draft does not
    look. Undrafted prospects of the next drafts join a real club of their country's league (the CHL
    for the rest), as EA's own roster keeps its draft classes."""
    from legacy_roster.leagues import clubs
    _, result = everything
    R = Roster(result.data)
    P, T = R.P, R.T
    season = pack['season']
    joined = {(row[2], row[0]) for row in result.log if row[1] == 'prospect joined'}       # (name, club)
    assert len(joined) > 150
    league_of = {'shl': 2, 'liiga': 3, 'del': 4, 'extraliga': 5, 'nl': 6, 'norway': 7}
    on_pools = 0
    for prow in range(P.cur_rec):
        year = P.get(prow, 'draftyear')
        if (P.get(prow, 'draftround') or year == 255 or year + 1900 <= season
                or season - (P.get(prow, 'year') + 1910) >= clubs.STAY_AGE):
            continue
        teams = [t for _, t in R.teams_of(prow) if t not in L.NATIONAL]
        if any(pools.is_pool(R, t) for t in teams):
            on_pools += 1
        elif teams and (R.name(prow), T.get(teams[0], 'abbrname')) in joined:
            home = clubs.HOME_LEAGUE.get(clubs.NATION_OF.get(P.get(prow, 'intlcountry')), 'chl')
            want = {league_of[home]} if home in league_of else {9, 10, 11}
            assert T.get(teams[0], 'league') in want, R.name(prow)
    assert on_pools <= 40          # only those who found no club with room
