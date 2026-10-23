"""Draft classes (draftclass.py): the player's made-up prospects, kept through every league's update."""
import json

import pytest

from legacy_roster import draftclass, edits, faces, pipeline
from legacy_roster import layout as L
from legacy_roster.builder import Data
from legacy_roster.roster import Roster

OHL = sorted(L.OHL)
LIIGA = sorted(L.LIIGA)


def test_the_draft_year_follows_the_15_september_rule():
    assert draftclass.eligible_year((2009, 9, 15)) == 2027
    assert draftclass.eligible_year((2009, 9, 16)) == 2028
    assert draftclass.eligible_year((2009, 12, 31)) == 2028
    assert list(draftclass.class_years(2026)) == [2027, 2028, 2029, 2030]


def test_potential_is_fitted_into_the_band_of_its_growth_tier():
    assert draftclass.fitted({'tier': 1, 'potential': 40}) == (1, 59)
    assert draftclass.fitted({'tier': 4, 'potential': 46}) == (4, 46)
    assert draftclass.fitted({'tier': 4, 'potential': 70}) == (4, 49)
    assert draftclass.fitted({'tier': 7}) == (7, 35)                # no value: the band's top
    assert draftclass.fitted({'tier': 9, 'potential': 'x'}) == (7, 35)
    assert draftclass.fitted({}) == (3, 50)


def test_only_european_and_chl_clubs_are_drafted_from():
    assert all(draftclass.is_draft_club(t) for t in (62, 80, 130, 132, 154, 191, 213))
    assert not any(draftclass.is_draft_club(t) for t in (0, 31, 45, 234, 135, 214, 250))


def a_class(count=30):
    """`count` class players spread over the OHL and Liiga clubs (2027-2030, every tier), a goalie in every eight, one on
    an AHL club and one too old: those two are left out."""
    mine = {}
    for i in range(count):
        year = 2009 + i % 4
        birth = [year, 1 + i % 9, 1 + i % 28]          # before 15 September: drafts 2027-2030
        pos = 'G' if i % 8 == 7 else 'CLRD'[i % 4]
        team = (OHL + LIIGA)[i % (len(OHL) + len(LIIGA))]
        first, last = 'Class', f"Prospect{i:02}"
        mine[edits.person_key(first, last, birth)] = {
            'label': f"{first} {last}", 'new': True, 'team': team, 'ovr': 55,
            'set': {'first': first, 'last': last, 'pos': pos, 'shoots': 'L', 'birth': birth, 'country': 'CAN'},
            'prospect': {'class': draftclass.eligible_year(birth), 'tier': 1 + i % 7, 'potential': 99}}
    mine[edits.person_key('Class', 'Farmhand', [2009, 3, 1])] = {
        'label': 'Class Farmhand', 'new': True, 'team': 45, 'ovr': 55,
        'set': {'first': 'Class', 'last': 'Farmhand', 'pos': 'C', 'birth': [2009, 3, 1]}, 'prospect': {'tier': 2}}
    mine[edits.person_key('Class', 'Veteran', [2000, 3, 1])] = {
        'label': 'Class Veteran', 'new': True, 'team': OHL[0], 'ovr': 55,
        'set': {'first': 'Class', 'last': 'Veteran', 'pos': 'C', 'birth': [2000, 3, 1]}, 'prospect': {'tier': 2}}
    return mine


@pytest.fixture(scope='module')
def with_class(base_bytes, data, pack):
    full = Data(nhl_players=data.nhl_players, ratings_list=data.ratings_list, iihf=data.iihf,
                season_year=data.season_year, leagues=pack['leagues'], drafts=pack.get('drafts'), contracts=data.contracts)
    mine = a_class()
    return full, mine, pipeline.build(base_bytes, full, steps=pipeline.steps_for(pack), my_edits=mine)


def test_a_class_survives_a_full_update_with_every_league(with_class):
    full, mine, res = with_class
    assert res.ok, res.problems[:5]
    assert not [r for r in res.log if r[1] == 'edit skipped']      # records were held for them (records_needed)
    R = Roster(res.data)
    placed = res.builder.prospects['players']
    assert len(placed) == 30
    rows = draftclass.ai_rows(R)
    for pid, (label, year, tier, potential) in placed.items():
        prow = R.p_by_id[pid]
        assert R.name(prow) == label
        assert draftclass.eligible_year(edits.birth_of(R.P, prow)) == year
        assert tuple(R.P.get(prow, f) for f in draftclass.UNDRAFTED_FIELDS) == (year - 1900, 0, 0, 0)
        assert [draftclass.is_draft_club(t) for _, t in R.teams_of(prow) if t not in L.NATIONAL] == [True]
        tname, row = rows[pid]
        assert (R.f[tname].get(row, 'koEt'), R.f[tname].get(row, 'AMoQ')) == (potential, tier)
        assert potential == draftclass.TIER_BANDS[tier][1]          # 99 fitted to the band's top
    left_out = sorted(r[2] for r in res.log if r[1] == 'class player left out')
    assert left_out == ['Class Farmhand', 'Class Veteran']


def test_a_second_run_with_the_class_changes_nothing(with_class, pack):
    full, mine, res = with_class
    again = pipeline.build(res.data, full, steps=pipeline.steps_for(pack), my_edits=mine)
    assert again.problems == []
    assert again.data == res.data
    assert sum(1 for i in range(Roster(again.data).P.cur_rec) if Roster(again.data).name(i) == 'Class Prospect00') <= 1


def test_verify_refuses_a_class_player_who_lost_his_potential_or_got_a_draft(with_class):
    full, mine, res = with_class
    prospects = res.builder.prospects
    R = Roster(res.data)
    assert draftclass.problems(R, prospects) == []
    pid = min(prospects['players'])
    prow = R.p_by_id[pid]
    tname, row = draftclass.ai_rows(R)[pid]
    R.f[tname].set(row, 'koEt', 5)
    R.P.set(prow, 'Ujcc', 1)
    found = draftclass.problems(Roster(R.f.build()), prospects)
    label = prospects['players'][pid][0]
    assert f"draft class: {label} lost his potential" in found
    assert f"draft class: {label} has a draft" in found


# --- class files and the random maker --------------------------------------------------------------------------------
# made-up real players: ten of each country (letters only: a name with digits is never taken)
NAMES = [(f"First{country.title()}{x}", f"Last{country.title()}{x}", country)
         for country in ('CAN', 'USA', 'SWE', 'FIN', 'CZE') for x in 'abcdefghij']
CLUBS = {'CHL': OHL[:6], 'SHL': [62, 63], 'Liiga': LIIGA[:3], 'Extraliga': [105]}


def test_the_maker_makes_the_same_class_from_the_same_inputs():
    one = draftclass.make(2027, 32, NAMES, CLUBS, seed=7)
    assert one == draftclass.make(2027, 32, NAMES, CLUBS, seed=7)
    assert one != draftclass.make(2027, 32, NAMES, CLUBS, seed=8)
    assert one != draftclass.make(2027, 32, NAMES, CLUBS, seed=7, strength='strong')
    assert len(one) == 32
    tiers = [pl['prospect']['tier'] for pl in one]
    assert tiers == sorted(tiers) and tiers[0] <= 2                     # best first
    first, last = draftclass.birth_window(2027)
    for pl in one:
        card, (lo, hi) = pl['card'], draftclass.TIER_BANDS[pl['prospect']['tier']]
        assert lo <= pl['prospect']['potential'] <= hi
        born = tuple(int(x) for x in card['birth'].split('-'))
        assert draftclass.eligible_year(born) == 2027 and first.isoformat() <= card['birth'] <= last.isoformat()
        assert card['pos'] in ('C', 'LW', 'RW', 'D', 'G') and 42 <= int(card['ovr']) <= 70
        home = draftclass.HOME_LEAGUE.get(card['country'], 'CHL')
        assert pl['club'] in (CLUBS.get(home) or CLUBS['CHL'])
        assert faces.look_wrong(card['look']) is None and set(card['look']) == set(faces.DEFAULT_LOOK)
    assert len({json.dumps(pl['card']['look'], sort_keys=True) for pl in one}) > 24      # faces of their own


def test_made_names_are_mixed_never_a_real_players_full_name():
    real = {draftclass.plain(f"{f} {l}") for f, l, _ in NAMES}
    made = draftclass.make(2028, 64, NAMES, CLUBS, seed=3, taken=["FirstCana LastCanb"])
    names = [draftclass.plain(f"{pl['card']['first']} {pl['card']['last']}") for pl in made]
    assert len(set(names)) == len(names)
    assert not set(names) & real and "firstcana lastcanb" not in names
    by_country = {c: ({f for f, _, k in NAMES if k == c}, {l for _, l, k in NAMES if k == c}) for _, _, c in NAMES}
    for pl in made:                                     # first and last names of the same country
        firsts, lasts = by_country[pl['card']['country']]
        assert pl['card']['first'] in firsts and pl['card']['last'] in lasts


def test_made_players_spread_evenly_over_their_league():
    made = draftclass.make(2027, 64, [(f, l, 'CAN') for f, l, _ in NAMES], {'CHL': OHL[:4]}, seed=1)
    counts = sorted(sum(1 for pl in made if pl['club'] == t) for t in OHL[:4])
    assert counts == [16, 16, 16, 16]


def test_a_class_needs_names_and_clubs():
    with pytest.raises(ValueError):
        draftclass.make(2027, 4, [], CLUBS)
    with pytest.raises(ValueError):
        draftclass.make(2027, 4, NAMES, {})


def test_the_tier_split_follows_the_strength():
    assert draftclass.tiers_for(32, 'normal') == sorted(draftclass.tiers_for(32, 'normal'))
    for strength in draftclass.STRENGTHS:
        assert len(draftclass.tiers_for(64, strength)) == 64
    strong, weak = draftclass.tiers_for(64, 'strong'), draftclass.tiers_for(64, 'weak')
    assert sum(strong) < sum(weak)


def test_a_class_file_round_trips():
    made = draftclass.make(2027, 8, NAMES, CLUBS, seed=5)
    players = [{'card': dict(pl['card'], num='12', ratings={'Speed': '71', 'Puck Control': ''}),
                'prospect': pl['prospect'], 'club': {'league': 'OHL', 'name': 'Somewhere'}} for pl in made]
    text = draftclass.class_file("Test class", 2027, players)
    name, year, back = draftclass.read_class(text)
    assert (name, year, len(back)) == ("Test class", 2027, 8)
    for was, now in zip(players, back):
        assert now['card']['first'] == was['card']['first'] and now['card']['birth'] == was['card']['birth']
        assert now['card']['ratings'] == {'Speed': '71'}            # empty ratings are not kept
        assert now['prospect'] == was['prospect'] and now['club'] == {'league': 'OHL', 'name': 'Somewhere'}
    assert draftclass.read_class(draftclass.class_file("", 2029, players[:1]))[0] == "2029 draft class"


def test_a_class_file_keeps_a_created_look_and_leaves_out_a_wrong_one():
    import json
    from legacy_roster import faces
    look = dict(faces.DEFAULT_LOOK, shape=11, hair=0)
    players = [{'card': {'first': 'Ivo', 'last': 'Looksmith', 'pos': 'C', 'look': look}, 'prospect': {}, 'club': None},
               {'card': {'first': 'Ole', 'last': 'Plainface', 'pos': 'D', 'head': '60012'}, 'prospect': {}, 'club': None}]
    text = draftclass.class_file("Looks", 2027, players)
    back = draftclass.read_class(text)[2]
    assert back[0]['card']['look'] == look and 'look' not in back[1]['card'] and back[1]['card']['head'] == '60012'
    doc = json.loads(text)
    doc['players'][0]['card']['look']['hair'] = 99          # not one of the game's choices: the player stays, no look
    back = draftclass.read_class(json.dumps(doc))[2]
    assert back[0]['card']['first'] == 'Ivo' and 'look' not in back[0]['card']


@pytest.mark.parametrize('text, says', [
    ("not json", "not a draft class file"),
    ('{"format": "something else", "version": 1}', "not a draft class file"),
    ('{"format": "legacy-roster-draft-class", "version": 9, "year": 2027, "players": [{}]}', "newer version"),
    ('{"format": "legacy-roster-draft-class", "version": 1, "players": [{"card": {}}]}', "which draft"),
    ('{"format": "legacy-roster-draft-class", "version": 1, "year": 2027, "players": []}', "no players"),
    ('{"format": "legacy-roster-draft-class", "version": 1, "year": 2027, "players": [3]}', "damaged"),
])
def test_a_wrong_class_file_is_refused_in_plain_words(text, says):
    with pytest.raises(ValueError, match=says):
        draftclass.read_class(text)


def test_birth_dates_move_to_another_draft():
    assert draftclass.shift_birth('2009-05-04', 2) == '2011-05-04'
    assert draftclass.shift_birth('2008-02-29', 1) == '2009-02-28'
    assert draftclass.shift_birth('soon', 1) == 'soon'
