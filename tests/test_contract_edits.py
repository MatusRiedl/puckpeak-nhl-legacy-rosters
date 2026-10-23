"""Contracts the player sets by hand (edits.json "contract", the Front office): verify checks them, they are written after
the real deals, and a second run writes the same."""
import pytest

from legacy_roster import contracts as pay
from legacy_roster import edits, pipeline
from legacy_roster import layout as L
from legacy_roster.editor import model
from legacy_roster.roster import Roster
from legacy_roster.verify import verify

DEAL = {'cap': 15_000_000, 'years': 3, 'two_way': 0, 'ext': [5, 16_500_000, 0]}


def find(R, name):
    return next(i for i in range(R.P.cur_rec) if R.name(i) == name and R.teams_of(i))


def fields(R, prow):
    return {f: R.P.get(prow, f) for f in pay.FIELDS}


def mine(R, prow, deal=DEAL):
    return {edits.who_of(R.P, prow): {'label': R.name(prow), 'contract': dict(deal)}}


def no_organisation(R):
    """A club player with nobody's rights on no NHL roster (a junior club: the base's European clubs are empty until the
    club-league steps run)."""
    return next(i for i in range(R.P.cur_rec) if not R.P.get(i, 'WBbd') and R.teams_of(i)
                and all(t in L.OHL for _, t in R.teams_of(i)))


def no_club(R):
    """A player on a national team only, with nobody's rights: no club to hold a contract."""
    return next(i for i in range(R.P.cur_rec) if not R.P.get(i, 'WBbd') and R.teams_of(i)
                and all(t in L.NATIONAL for _, t in R.teams_of(i)))


CLUB_DEAL = {'cap': 40_000, 'years': 2, 'two_way': 0, 'ext': None}     # free amounts outside the NHL organisations


def test_a_contract_outside_an_nhl_organisation_may_pay_any_amount():
    assert pay.edit_problems(CLUB_DEAL, nhl=False) == [] and pay.edit_problems(CLUB_DEAL)       # NHL: from $850k
    assert pay.edit_problems(dict(CLUB_DEAL, cap=5_000), nhl=False) == []
    assert pay.edit_problems(dict(CLUB_DEAL, cap=4_999), nhl=False)
    assert pay.edit_problems(dict(CLUB_DEAL, cap=20_805_000), nhl=False)
    assert pay.edit_problems(dict(CLUB_DEAL, years=9), nhl=False)
    assert pay.edit_problems(dict(CLUB_DEAL, ext=[2, 10_000, 0]), nhl=False) == []


def test_a_contract_the_game_cannot_hold_is_named():
    assert pay.edit_problems(DEAL) == [] and pay.edit_problems(dict(DEAL, ext=None)) == []
    assert pay.edit_problems(dict(DEAL, cap=845_000)) and pay.edit_problems(dict(DEAL, cap=20_805_000))
    assert pay.edit_problems(dict(DEAL, years=0)) and pay.edit_problems(dict(DEAL, years=9))
    assert pay.edit_problems(dict(DEAL, ext=[9, 2_000_000, 0])) and pay.edit_problems(dict(DEAL, ext=[2, 21_000_000, 0]))
    late = pay.edit_problems(dict(DEAL, ext=[2, 950_000, 0]))       # starts in 2029-30: its lowest salary is $1M
    assert len(late) == 1 and 'from $1M' in late[0]


def test_verify_checks_a_contract_set_by_hand(built):
    R = Roster(built.data)
    mcd = find(R, 'Connor McDavid')
    pay.write(R.P, mcd, DEAL, pay.GAME)
    out = R.f.build()
    assert verify(out, Roster(built.data), money=pay.GAME, contract_edits={mcd: DEAL})[0] == []
    found = verify(out, Roster(built.data), money=pay.GAME, contract_edits={mcd: dict(DEAL, cap=16_000_000)})[0]
    assert len(found) == 1 and 'Connor McDavid' in found[0] and 'not the contract set' in found[0]
    wild = dict(DEAL, years=12)
    R2 = Roster(built.data)
    pay.write(R2.P, mcd, wild, pay.GAME)
    found = verify(R2.f.build(), Roster(built.data), money=pay.GAME, contract_edits={mcd: wild})[0]
    assert any('12 seasons' in p for p in found)
    club = no_organisation(R)                       # a club's own deal: free amounts
    R3 = Roster(built.data)
    pay.write(R3.P, club, CLUB_DEAL, pay.GAME)
    assert verify(R3.f.build(), Roster(built.data), money=pay.GAME, contract_edits={club: CLUB_DEAL})[0] == []
    R4 = Roster(built.data)
    pay.write(R4.P, mcd, CLUB_DEAL, pay.GAME)       # an NHL player: NHL amounts
    found = verify(R4.f.build(), Roster(built.data), money=pay.GAME, contract_edits={mcd: CLUB_DEAL})[0]
    assert any('Connor McDavid' in p and 'cap hit of $40k' in p for p in found)
    nobody = no_club(R)
    R5 = Roster(built.data)
    pay.write(R5.P, nobody, CLUB_DEAL, pay.GAME)
    found = verify(R5.f.build(), Roster(built.data), money=pay.GAME, contract_edits={nobody: CLUB_DEAL})[0]
    assert any('on no club' in p for p in found)


def test_a_contract_set_by_hand_beats_the_real_deal_and_holds_on_a_second_run(built, base_bytes, data):
    R = Roster(built.data)
    mcd = find(R, 'Connor McDavid')
    assert fields(R, mcd) != pay.terms(DEAL, pay.GAME)            # the real deal
    edit = mine(R, mcd)
    res = pipeline.build(base_bytes, data, my_edits=edit)
    assert res.problems == []
    out = Roster(res.data)
    assert fields(out, find(out, 'Connor McDavid')) == pay.terms(DEAL, pay.GAME)
    rows = [r for r in res.builder.log if r[2] == 'Connor McDavid' and r[0] == 'edits']
    assert [r[1] for r in rows] == ['edited'] and rows[0][3].startswith('contract: $15M x 3 seasons, then 5 x $16.5M')
    assert pipeline.section_of(rows[0]) == pipeline.SECTION_EDITS
    assert pipeline.build(res.data, data, my_edits=edit).data == res.data      # byte-identical second run


def test_a_contract_for_someone_on_no_club_or_out_of_range_is_left_out(built, base_bytes, data):
    R = Roster(built.data)
    nobody, mcd = no_club(R), find(R, 'Connor McDavid')
    edit = {**mine(R, nobody, CLUB_DEAL), **mine(R, mcd, dict(DEAL, cap=30_000_000))}
    res = pipeline.build(built.data, data, my_edits=edit)
    assert res.problems == [] and res.data == pipeline.build(built.data, data).data      # nothing written
    skipped = {r[2]: r[3] for r in res.builder.log if r[1] == 'edit skipped'}
    assert 'on no club' in skipped[R.name(nobody)] and '$30M' in skipped['Connor McDavid']


def test_a_contract_with_a_junior_club_is_written_and_holds_on_a_second_run(built, data):
    """Owner, 2026-10-22: contracts for every league, free amounts outside the NHL organisations; his rights stay."""
    R = Roster(built.data)
    club = no_organisation(R)
    assert pay.deal_of(R.P, club, pay.GAME)['cap']                  # the update gave him a starter deal
    edit = mine(R, club, CLUB_DEAL)
    res = pipeline.build(built.data, data, my_edits=edit)
    assert res.problems == []
    out = Roster(res.data)
    assert fields(out, club) == pay.terms(CLUB_DEAL, pay.GAME) and out.P.get(club, 'WBbd') == 0
    assert out.P.get(club, pay.STATUS) == 1 and out.P.get(club, 'BSXd') - 1 in {t for _, t in out.teams_of(club)}
    assert pipeline.build(res.data, data, my_edits=edit).data == res.data      # byte-identical second run


def test_the_roster_editor_s_save_writes_a_contract(built):
    R = Roster(built.data)
    nobody_rights = next(i for i in range(R.P.cur_rec) if R.P.get(i, 'WBbd') and not R.P.get(i, 'dhKk')
                         and R.teams_of(i) and not any(t in L.NHL_PRIMARY for _, t in R.teams_of(i)))
    edit = {**mine(R, find(R, 'Connor McDavid')), **mine(R, nobody_rights, dict(DEAL, ext=None, two_way=1))}
    res = model.apply_edits(built.data, edit, {}, 2026)              # steps=[]: no real deals, the edits only
    assert res.problems == []
    out = Roster(res.data)
    assert fields(out, find(out, 'Connor McDavid')) == pay.terms(DEAL, pay.GAME)
    assert fields(out, nobody_rights) == pay.terms(dict(DEAL, ext=None, two_way=1), pay.GAME)   # a prospect signed


def test_a_contract_set_in_the_roster_editor_shows_in_team_rosters(built):
    """The game shows CONT / SAL only for contract status 1 (contracts.status_fit): the editor's Save sets it for the
    players whose contract it wrote and for nobody else."""
    R = Roster(built.data)
    farm = next(i for i in range(R.P.cur_rec) if R.P.get(i, 'WBbd') and R.P.get(i, 'dhKk') and R.teams_of(i)
                and all(t in L.AHL for _, t in R.teams_of(i)))
    for f in pay.FIELDS + (pay.STATUS,):                             # an AHL player of an organisation, no contract
        R.P.set(farm, f, 0)
    src = R.f.build()
    res = model.apply_edits(src, mine(R, farm, dict(DEAL, ext=None, two_way=1)), {}, 2026)
    assert res.problems == []
    out = Roster(res.data)
    assert out.P.get(farm, pay.STATUS) == 1
    assert [i for i in range(R.P.cur_rec) if out.P.get(i, pay.STATUS) != R.P.get(i, pay.STATUS)] == [farm]


@pytest.mark.parametrize('scale', [pay.GAME, pay.REAL])
def test_a_contract_reads_back_in_real_dollars(built, scale):
    R = Roster(built.data)
    mcd = find(R, 'Connor McDavid')
    pay.write(R.P, mcd, DEAL, scale)
    assert pay.deal_of(R.P, mcd, scale) == DEAL
    assert [pay.cap_in(DEAL, k) for k in range(9)] == [15_000_000] * 3 + [16_500_000] * 5 + [0]
