"""Players' contracts (contracts.py): the money scale, the real 2026-27 deals in a build, the checks."""
import pytest

from legacy_roster import contracts as pay
from legacy_roster import layout as L
from legacy_roster import pipeline
from legacy_roster.roster import Roster


def find(R, name):
    return next(i for i in range(R.P.cur_rec) if R.name(i) == name and R.teams_of(i))


def deal_of(data, first, last):
    return next(d for d in data.contracts if d['first'] == first and d['last'] == last)


def test_dollars_become_the_save_s_units_on_either_scale():
    assert pay.units(17_000_000, pay.GAME) == 2334 and pay.units(17_000_000, pay.REAL) == 3400
    assert pay.units(1, pay.GAME) == 1 and pay.units(10 ** 9, pay.REAL) == (1 << 13) - 1     # clamped to the field
    assert pay.default_terms(True, pay.GAME) == (3, 134) and pay.default_terms(False, pay.GAME) == (1, 117)
    assert pay.default_terms(True, pay.REAL) == (3, 195) and pay.default_terms(False, pay.REAL) == (1, 170)
    assert pay.dollars(3400, pay.REAL) == 17_000_000 and abs(pay.dollars(2334, pay.GAME) - 17e6) < pay.UNIT


def test_a_deal_with_an_extension_fills_every_field():
    deal = {'cap': 12_500_000, 'years': 2, 'two_way': 0, 'ext': [8, 16_000_000, 0]}
    assert pay.terms(deal, pay.REAL) == {'dhKk': 2500, 'GDhI': 2, 'DVoL': 0, 'gHmt': 1, 'IrlK': 8, 'IzRv': 3200, 'xdoJ': 0}
    one = pay.terms({'cap': 850_000, 'years': 1, 'two_way': 1}, pay.GAME)
    assert one == {'dhKk': 117, 'GDhI': 1, 'DVoL': 1, 'gHmt': 0, 'IrlK': 0, 'IzRv': 0, 'xdoJ': 0}


def test_every_team_s_deals_are_its_own_players(pack):
    """The pack's deals per organisation are mostly players NHL.com lists for that team (Seattle and Vegas were
    swapped until 2026-10-20), and the check finds a swap."""
    from legacy_roster import datasource
    players = datasource.flatten_nhl(pack['nhl'])
    assert pay.misplaced(pack['contracts'], players) == {}
    swapped = [dict(d, org={'SEA': 'VGK', 'VGK': 'SEA'}.get(d['org'], d['org'])) for d in pack['contracts']]
    assert pay.misplaced(swapped, players) == {'SEA': 'VGK', 'VGK': 'SEA'}


def test_rescale_moves_every_cap_hit_once(base_bytes):
    R = Roster(base_bytes)
    paid = [i for i in range(R.P.cur_rec) if R.P.get(i, 'dhKk')]
    before = {i: R.P.get(i, 'dhKk') for i in paid}
    assert pay.rescale(R.P, pay.REAL / pay.GAME) >= len(paid)
    for i in paid[:200]:
        assert R.P.get(i, 'dhKk') == min(R.P.field('dhKk').mask, round(before[i] / pay.GAME))
    pay.rescale(R.P, pay.GAME / pay.REAL)
    assert all(abs(R.P.get(i, 'dhKk') - before[i]) <= 1 for i in paid)       # back, within the rounding


def test_a_normal_update_gives_nhl_players_their_real_deals_on_the_game_s_scale(built, data):
    assert data.contracts and built.problems == []
    R = Roster(built.data)
    mcd = find(R, 'Connor McDavid')
    deal = deal_of(data, 'Connor', 'McDavid')
    assert R.P.get(mcd, 'dhKk') == pay.units(deal['cap'], pay.GAME) and R.P.get(mcd, 'GDhI') == deal['years']
    given = {row[2]: row[3] for row in built.builder.log if row[1] == 'contracts'}
    assert int(given["2026-27: given their real contract"].split()[0]) > 1000
    for t in L.NHL_PRIMARY:                     # every payroll in reach of the cap the game shows (scaled back)
        assert 60e6 < pay.payroll(R, t, pay.GAME) < 125e6, L.SLOT_TO_API[t]
    held = dict(built.lines())['Contracts']     # the result says so, in the player's words
    assert held.endswith("(scaled to the game's cap)") and int(held.split()[0]) > 1000
    assert any(s.startswith("Contracts: ") and "$71.4M" in s for s in built.summary())


def test_a_game_patch_update_holds_real_dollars(base_bytes, data):
    res = pipeline.build(base_bytes, data, game_patch=True)
    assert res.problems == []
    R = Roster(res.data)
    mcd = find(R, 'Connor McDavid')
    assert R.P.get(mcd, 'dhKk') == pay.units(deal_of(data, 'Connor', 'McDavid')['cap'], pay.REAL)
    assert any(row[2] == "contracts moved to real dollars" for row in res.builder.log)
    assert dict(res.lines())['Contracts'].endswith("(real dollars)")


def test_verify_names_a_cap_hit_or_an_extension_that_cannot_be(built):
    R, source = Roster(built.data), Roster(built.data)
    team = L.API_TO_SLOT['EDM']
    rows = [prow for _, prow, *_ in R.team_roster(team) if prow is not None]
    assert pay.problems(R, source, pay.GAME) == []
    R.P.set(rows[0], 'dhKk', 1)
    R.P.set(rows[1], 'IrlK', 3)
    R.P.set(rows[1], 'IzRv', 0)
    R.P.set(rows[2], 'GDhI', 0)
    found = pay.problems(R, source, pay.GAME)
    assert len(found) == 3 and 'a cap hit of $0.007M' in found[0]
    assert any('an extension of 3 seasons' in p for p in found) and any('0 seasons' in p for p in found)


def test_every_player_with_a_contract_on_a_team_shows_it_in_team_rosters(built):
    """Team Rosters shows CONT / SAL only for contract status 1 (lab round 41: Eichel, Hanifin in Vegas showed N/A)."""
    R = Roster(built.data)
    on, free = pay._status_rows(R)
    assert len(on) > 1000 and free
    for prow in on:
        want = pay.status_of(R.P, prow)
        assert want is None or R.P.get(prow, pay.STATUS) == want, R.name(prow)
    assert all(R.P.get(prow, pay.STATUS) == 0 for prow in free)
    assert R.P.get(find(R, 'Jack Eichel'), pay.STATUS) == 1
    assert pay.status_problems(R) == []
    fitted = {row[2]: row[3] for row in built.builder.log if row[1] == 'summary'}
    assert fitted["contract status set to fit the contract (Team Rosters shows it)"] > 0   # the base had them at 0


def test_verify_names_a_contract_status_that_does_not_fit(built):
    R, source = Roster(built.data), Roster(built.data)
    eichel = find(R, 'Jack Eichel')
    assert pay.status_problems(R, source) == []
    R.P.set(eichel, pay.STATUS, 0)
    found = pay.status_problems(R, source)
    assert len(found) == 1 and 'Jack Eichel' in found[0]
    assert pay.status_problems(R, Roster(R.f.build())) == []    # what the source already had is not blamed
    assert pay.status_fit(R) == 1 and pay.status_problems(R, source) == []


def test_every_player_becomes_a_ufa_at_27(base_bytes, built):
    """Be a GM shows UFA / RFA after a deal's last season by the UFA year (lab round 41: the community's 121 made Eichel
    an RFA at 32); the game's own roster holds birth year + 27 for everyone."""
    R, src = Roster(built.data), Roster(base_bytes)
    eichel = find(R, 'Jack Eichel')
    assert R.P.get(eichel, pay.UFA_YEAR) == R.P.get(eichel, 'dnFq') + 27 != src.P.get(find(src, 'Jack Eichel'), pay.UFA_YEAR)
    assert pay.ufa_problems(R) == [] and pay.ufa_problems(R, src) == []
    fitted = {row[2]: row[3] for row in built.builder.log if row[1] == 'summary'}
    assert fitted["free-agent year set to age 27 (Be a GM shows UFA / RFA by it)"] > 0
    R.P.set(eichel, pay.UFA_YEAR, 121)
    found = pay.ufa_problems(R, Roster(built.data))
    assert len(found) == 1 and 'Jack Eichel' in found[0]
    assert pay.ufa_problems(R, Roster(R.f.build())) == []       # what the source already had is not blamed
    assert pay.ufa_fit(R) == 1


@pytest.mark.parametrize('scale', [pay.GAME, pay.REAL])
def test_no_real_deal_breaks_the_checks(data, scale):
    for d in data.contracts:
        v = pay.terms(d, scale)
        assert pay.units(pay.LOWEST, scale) <= v['dhKk'] <= pay.units(pay.MAXIMUM, scale) + 1, d
        assert 1 <= v['GDhI'] <= 15 and bool(v['IrlK']) == bool(v['IzRv'])


def test_players_under_contract_whom_nhl_com_leaves_out_stay_with_their_team(built, data):
    R, b = Roster(built.data), built.builder
    kept = {row[2]: row for row in b.log if row[1] == 'stays under contract'}
    assert 'Dylan Larkin' in kept and kept['Dylan Larkin'][0] == 'DET'           # NHL.com's copy leaves him out
    larkin = find(R, 'Dylan Larkin')
    assert L.API_TO_SLOT['DET'] in {t for _, t in R.teams_of(larkin)} and R.P.get(larkin, 'dhKk')   # with his deal
    on_nhl_com = {f"{p['first']} {p['last']}" for p in data.nhl_players}
    assert not set(kept) & on_nhl_com and len(b.contract_kept) >= len(kept)       # NHL.com wins when it lists him
    assert all(t in L.NHL_PRIMARY or t in L.AHL for t in b.contract_kept.values())     # or his farm club: below
    size = {t: len(b.entries_on(t)) for t in L.NHL_PRIMARY}
    assert max(size.values()) <= L.MAX_PER_TEAM and built.problems == []
    nhl = dict(built.lines())[pipeline.SECTION_NHL]
    assert f", {len(kept)} kept under contract" in nhl
    fa = {R.name(R.p_by_id[R.link_to_pid[l]]) for l in b.fa_links if R.link_to_pid.get(l) in R.p_by_id}
    assert 'Dylan Larkin' not in fa


def test_prospects_under_contract_on_no_club_join_their_organisations_farm_club(built):
    from legacy_roster.leagues.clubs import affiliates
    R, b = Roster(built.data), built.builder
    parents = affiliates(R)
    farm = {pid: t for pid, t in b.contract_kept.items() if t in L.AHL}
    logged = {row[2] for row in b.log if row[1] == 'farm under contract'}
    assert farm and len(logged) == len(farm)
    for pid, team in farm.items():
        prow = R.p_by_id[pid]
        assert team in {t for _, t in R.teams_of(prow)} and R.name(prow) in logged
        rights = parents[team] + 1 if pay.holds_rights(R.P, parents[team]) else 0   # Seattle's: nobody's (unpatched)
        assert R.P.get(prow, 'WBbd') == rights and R.P.get(prow, 'BSXd') == team + 1         # his rights, his club
        assert R.P.get(prow, 'DVoL') == 1 and R.P.get(prow, 'dhKk')                             # his two-way deal
    assert ' to their farm club (under contract)' in dict(built.lines())[pipeline.SECTION_NHL]


def test_seattle_and_vegas_hold_no_rights_on_a_roster_for_the_unpatched_game(built, data):
    """A tester's NA game crashed when a Season started (0.50.1): Coachella Valley's and other clubs' players held
    Seattle's rights (proteam 31), and the unpatched game's Season looks them up in a table of 30 NHL teams. The
    community's roster gives Seattle and Vegas nobody's rights; so does the update now (contracts.rights_teams), a roster
    0.50.1 made loses them on its next update, even the Roster editor's Save, and verify refuses them."""
    R = Roster(built.data)
    assert R.P.field('WBbd').bits == 5 and pay.rights_teams(R.P) == 30
    assert not any(R.P.get(prow, 'WBbd') > 30 for prow in range(R.P.cur_rec)) and pay.rights_problems(R) == []
    rows = [prow for _, prow, *_ in R.team_roster(234) if prow is not None][:3]
    for prow in rows:                   # as 0.50.1 left them: Seattle's prospects on Coachella Valley
        R.P.set(prow, 'WBbd', 31)
    assert pay.rights_problems(R)[0].startswith("3 players hold the NHL rights of slot 30 or later")
    saved = pipeline.build(R.f.build(), data, steps=[])
    out = Roster(saved.data)
    assert saved.problems == [] and all(out.P.get(find(out, R.name(prow)), 'WBbd') == 0 for prow in rows)
    assert any(row[3] == 3 and 'Seattle' in row[2] for row in saved.log if row[1] == 'summary')


def test_a_team_full_up_takes_no_more_players_under_contract(base_bytes, data, built, monkeypatch):
    from legacy_roster.builder import Builder
    joined = {row[2] for row in built.builder.log if row[1] in ('moved', 'added') and 'under contract' in row[3]}
    assert joined                                                    # from another NHL team or the free-agent list
    monkeypatch.setattr(Builder, 'NHL_KEEP_ROOM', 0)                 # every team full: only the ones there stay
    res = pipeline.build(base_bytes, data, steps=[pipeline.NHL])
    assert res.problems == [] and 'Dylan Larkin' in {row[2] for row in res.builder.log if row[1] == 'stays under contract'}
    left = {row[2]: row[3] for row in res.builder.log if row[1] == 'left NHL roster'}
    assert {left.get(name) for name in joined} <= {'free agent (under contract for 2026-27, no room)', None}
    assert any(left.get(name) for name in joined)
    assert not any(row[1] in ('moved', 'added') and 'under contract' in row[3] for row in res.builder.log)


def test_a_player_an_earlier_update_made_a_free_agent_goes_back_to_his_team(base_bytes, data):
    from legacy_roster.builder import Data
    older = pipeline.build(base_bytes, Data(**{**data.__dict__, 'contracts': None}))    # as before the contracts
    R = Roster(older.data)
    assert not any(R.teams_of(i) for i in range(R.P.cur_rec) if R.name(i) == 'Dylan Larkin')   # a free agent
    res = pipeline.build(older.data, data)
    assert res.problems == []
    added = {row[2]: row for row in res.builder.log if row[1] == 'added' and 'under contract' in row[3]}
    assert added['Dylan Larkin'][:2] == ['DET', 'added'] and added['Dylan Larkin'][3].startswith('from free agent')
    R = Roster(res.data)
    larkin = find(R, 'Dylan Larkin')
    entry = next(e for e, t in R.teams_of(larkin) if t == L.API_TO_SLOT['DET'])
    assert R.U.get(entry, 'jZSh') == 1                          # Detroit's lines were dealt again: he dresses
    assert R.P.get(larkin, 'dhKk') == pay.units(deal_of(data, 'Dylan', 'Larkin')['cap'], pay.GAME)
    assert max(len(res.builder.entries_on(t)) for t in L.NHL_PRIMARY) <= max(
        res.builder.NHL_KEEP_ROOM, max(sum(p['team'] == a for p in data.nhl_players) for a in L.API_TO_SLOT))
    assert pipeline.build(res.data, data).data == res.data      # a second run finds him there


def test_a_starter_deal_follows_the_club_s_league_and_the_player_s_overall():
    """Owner, 2026-10-22: a made-up starter deal for every club player without one (real dollars, then the scale)."""
    kladno = min(L.EXTRALIGA)
    assert pay.starter_league(kladno) == 'LIIGA' and pay.starter_league(234) == 'AHL'
    assert pay.starter_league(min(L.NL)) == 'NL' and pay.starter_league(min(L.DEL)) == 'SHL'
    assert pay.starter_league(min(L.CHL)) == 'CHL' and pay.starter_league(132) == 'OTHER'
    assert [pay.starter_pay(kladno, o) for o in (60, 70, 75, 85)] == [100_000, 150_000, 250_000, 350_000]
    young = pay.starter_terms(min(L.NL), 76, 24, pay.REAL)
    assert young == {'dhKk': 120, 'GDhI': 2, 'DVoL': 0, 'gHmt': 1, 'IrlK': 0, 'IzRv': 0, 'xdoJ': 0}
    old = pay.starter_terms(min(L.CHL), 50, 27, pay.GAME)
    assert old['GDhI'] == 1 and old['gHmt'] == 0 and old['dhKk'] == pay.units(10_000, pay.GAME) == 1


def test_verify_names_a_club_deal_that_cannot_be(built):
    R, source = Roster(built.data), Roster(built.data)
    on, _ = pay._status_rows(R)
    club = next(prow for prow in sorted(on) if all(t in L.OHL for _, t in R.teams_of(prow)))
    R.P.set(club, 'dhKk', pay.units(pay.MAXIMUM, pay.GAME) + 5)
    found = pay.problems(R, source, pay.GAME)
    assert len(found) == 1 and R.name(club) in found[0] and 'a cap hit of' in found[0]
