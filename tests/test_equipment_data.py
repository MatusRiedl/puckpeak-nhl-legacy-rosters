"""the data pack part `equipment` (raw sock tuck, pants, tape class and neck guard of the NHL's and the AHL's players with
curated gear; `datasource.equipment_part`, made by private/equipment_db.py, notes docs/notes/equipment-accuracy.md)."""
import pytest

from legacy_roster import datasource, ratings
from legacy_roster.matching import norm
from legacy_roster.roster import Roster

KEYS = {'first', 'last', 'birth', 'pos', 'sock', 'pants', 'neck', 'tape', 'goalie'}


@pytest.fixture(scope='module')
def part(pack):
    found = datasource.equipment_part(pack)
    if found is None:
        pytest.skip("the data pack has no equipment part (python tools/build_datapack.py --refresh equipment)")
    return found


def find(part, first, last, birth):
    return [p for p in part['players'] if (p['first'], p['last'], tuple(p['birth'])) == (first, last, birth)]


def test_the_part_is_small_and_says_its_numbers_are_raw(part):
    assert part['format'] == datasource.EQUIPMENT_FORMAT and part['values'] == 'raw'
    assert 700 <= len(part['players']) <= 1500
    assert part['count'] == len(part['players'])


def test_an_entry_holds_a_key_and_small_numbers_only(part):
    for p in part['players']:
        assert set(p) <= KEYS, p
        assert {'first', 'last', 'birth', 'pos'} <= set(p)
        assert p['pos'] in ('C', 'LW', 'RW', 'D', 'G') and len(p['birth']) == 3
        # no model number, no colour: only the tucks, the pants, a tape class and the neck guard
        for field in ('sock', 'pants', 'neck'):
            assert p.get(field, 0) in range(8), p
        assert p.get('tape', 'black') in ('black', 'white'), p
        assert ('goalie' in p) == (p['pos'] == 'G')
        if p['pos'] == 'G':
            assert not {'sock', 'pants', 'tape'} & set(p)
        else:
            assert 'neck' not in p


def test_fields_at_the_default_are_left_out(part):
    for p in part['players']:
        assert p.get('sock', 1) != 0 and p.get('pants', 1) != 0 and p.get('neck', 1) != 0
    shares = [sum(1 for p in part['players'] if f in p) / len(part['players']) for f in ('sock', 'pants', 'tape')]
    assert all(0 < s < 1 for s in shares)


def test_keys_are_unique(part):
    keys = [(norm(p['first']), norm(p['last']), tuple(p['birth']), p['pos'] == 'G') for p in part['players']]
    assert len(keys) == len(set(keys))


def test_arvidsson_is_in_it_with_his_sock_tuck(part):
    (arvidsson,) = find(part, 'Viktor', 'Arvidsson', (1993, 4, 8))
    assert arvidsson['sock'] == 1 and arvidsson['pos'] == 'RW'          # the roster still has him at 0


def test_players_on_the_default_row_are_not_in_it(part):
    assert not find(part, 'Dillon', 'Boucher', (1997, 4, 16))           # an AHL player: every model on the default
    assert not find(part, 'Cameron', 'Hebig', (1997, 1, 21))
    assert not [p for p in part['players'] if p['last'] == 'Arvidsson' and p['first'] == 'Kevin']


def test_goalies_carry_a_neck_guard_flag_and_skaters_a_tape_class(part):
    goalies = [p for p in part['players'] if p.get('goalie')]
    assert 50 < len(goalies) < 400 and any(p.get('neck') == 1 for p in goalies)
    assert {p.get('tape') for p in part['players'] if not p.get('goalie')} == {None, 'black', 'white'}


def test_it_is_found_the_way_the_ratings_part_is_found(part):
    """ratings.match_full finds an entry by full name and birthdate, a short first name too, and a goalie only as a goalie."""
    index = ratings.full_index({'fields': {'skater': [], 'goalie': []},
                                'players': [dict(p, v=[]) for p in part['players']]})
    found = ratings.match_full(index, 'Viktor', 'Arvidsson', (1993, 4, 8), False)
    assert found and found[1] == 'full' and found[0]['sock'] == 1
    goalie = next(p for p in part['players'] if p.get('goalie'))
    again = ratings.match_full(index, goalie['first'], goalie['last'], tuple(goalie['birth']), True)
    assert again and again[0]['last'] == goalie['last'] and again[0].get('goalie')
    assert ratings.match_full(index, goalie['first'], goalie['last'], tuple(goalie['birth']), False) is None


def test_nearly_every_nhl_player_of_the_base_roster_is_in_it(part, base_bytes):
    R = Roster(base_bytes)
    P = R.P
    on_roster = {(norm(P.get(i, 'PedH')), norm(P.get(i, 'RMbQ'))) for i in range(P.cur_rec)}      # one pass over the rows
    assert ('viktor', 'arvidsson') in on_roster
    names = {(norm(p['first']), norm(p['last'])) for p in part['players']}
    assert len(names & on_roster) > 0.7 * len(names)
