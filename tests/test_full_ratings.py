"""the current ratings, player types and tendencies (data pack part `ratings_full`; ratings.full_index / match_full /
write_full, Builder.rate_full, docs/notes/full-ratings.md)."""
import copy

import pytest

from legacy_roster import pipeline, ratings, schema
from legacy_roster.builder import Data
from legacy_roster.roster import Roster
from legacy_roster.verify import rating_problems, verify

SKATER = list(schema.FULL_RATED['skater']) + list(schema.FULL_ASIS['skater']) + ['c_potential', 'growthtier']
GOALIE = list(schema.FULL_RATED['goalie']) + list(schema.FULL_ASIS['goalie']) + ['c_potential', 'growthtier']


def player(first, last, birth, pos='C', overall=80, **values):
    """A player of the pack part: every rating `overall`, the small numbers 1, the type 6 (5 for a goalie: none of his)."""
    names = GOALIE if pos == 'G' else SKATER
    v = {n: overall for n in names}
    v.update({n: 1 for n in schema.ASIS_RANGE}, playerstyle=1 if pos == 'G' else 3 if pos == 'D' else 6,
             c_potential=66, growthtier=7)
    v.update(values)
    return {'first': first, 'last': last, 'birth': list(birth), 'pos': pos, 'hand': 'L', 'height': 73, 'weight': 190,
            'team': None, 'league': None, 'v': [v[n] for n in names]}


def part(*players):
    return {'fields': {'skater': SKATER, 'goalie': GOALIE}, 'players': list(players)}


class Table:
    """A rating row as write_full sees it."""
    def __init__(self):
        self.row = {}

    def set(self, row, tag, value):
        self.row[tag] = value


# --- the rules, without a roster ----------------------------------------------------------------------------------
def test_ratings_are_stored_minus_36_and_the_small_numbers_as_they_are():
    ix = ratings.full_index(part(player('Ann', 'Example', (2000, 5, 6), c_speed=99, c_faceoffs=30, c_fighting=3,
                                         off_defbias=14, playerstyle=7)))
    p = ix['skater']['name'][('ann', 'example')][0][2]
    values = ratings.full_values(ix, 'skater', p)
    t = Table()
    assert ratings.write_full(t, 0, values, 'skater') == len(schema.FULL_RATED['skater']) + 4
    tag = schema.FULL_TAG['skater']
    assert t.row[tag['c_speed']] == 63 and t.row[tag['c_faceoffs']] == 0 and t.row[tag['c_overall']] == 80 - 36
    assert t.row[tag['c_fighting']] == 3 and t.row[tag['off_defbias']] == 14
    # the type is the builder's (within his class); potential, growth and traits stay the game's
    assert tag['playerstyle'] not in t.row and tag['c_potential'] not in t.row and tag['growthtier'] not in t.row
    g = ratings.full_index(part(player('Bo', 'Keeper', (1995, 1, 2), 'G', c_consistency=5, c_paddledown=1)))
    t = Table()
    ratings.write_full(t, 0, ratings.full_values(g, 'goalie', g['goalie']['name'][('bo', 'keeper')][0][2]), 'goalie')
    tag = schema.FULL_TAG['goalie']
    assert t.row[tag['c_consistency']] == 2 and t.row[tag['c_paddledown']] == 1      # held to what the game's have


def test_matching_goes_by_full_name_then_last_name_then_a_unique_name():
    ix = ratings.full_index(part(
        player('Matthew', 'Tkachuk', (1997, 12, 11)),
        player('Sam', 'Twin', (2001, 3, 4)), player('Tom', 'Twin', (2001, 3, 4)),
        player('Jonas', 'Muller', (1995, 3, 12), 'D'),
        player('Elias', 'Same', (2000, 1, 1)), player('Elias', 'Same', (2002, 1, 1)),
        player('Juho', 'Even', (1999, 1, 10)), player('Juho', 'Even', (1999, 1, 20)),
        player('Pekka', 'Rinne', (1982, 11, 3), 'G')))
    find = lambda first, last, birth, goalie=False, **kw: ratings.match_full(ix, first, last, birth, goalie, **kw)
    assert find('Matthew', 'Tkachuk', (1997, 12, 11))[1] == 'full'
    assert find('Matt', 'Tkachuk', (1997, 12, 11))[1] == 'last+birth'               # Matt / Matthew
    assert find('Tom', 'Twin', (2001, 3, 4))[0]['first'] == 'Tom'                     # twins by their own first name
    assert find('Jonas', 'Müller', (1995, 7, 1))[1] == 'name'                        # the DEL: an age only
    assert find('Jonas', 'Muller', (1997, 7, 1)) is None                             # two years off
    assert find('Elias', 'Same', (2001, 6, 1))[0]['birth'] == [2002, 1, 1]           # namesakes: the closest
    assert find('Juho', 'Even', (1999, 1, 15)) is None                               # as close: neither
    assert find('Pekka', 'Rinne', (1982, 11, 3)) is None                             # goalies only for goalies
    assert find('Pekka', 'Rinne', (1982, 11, 3), True)[1] == 'full'
    assert find('Matthew', 'Tkachuk', (2007, 12, 11)) is None
    assert find('Matthew', 'Tkachuk', (2007, 12, 11), years=(2007, 1997))[1] == 'full'   # a record in the game's year - 1900


def test_the_overall_goes_onto_the_level_scale_on_a_straight_line():
    ix = ratings.full_index(part(player('A', 'One', (2000, 1, 1), c_overall=60, overall=70),
                                  player('B', 'Two', (2000, 1, 2), c_overall=90, overall=85)))
    assert ratings.overall_level(ix, 'skater', 60) == pytest.approx(70)
    assert ratings.overall_level(ix, 'skater', 75) == pytest.approx(77.5)
    assert ix['goalie']['scale'] == (0.0, 1.0)                                       # no goalies: the overall itself


# --- on the community roster --------------------------------------------------------------------------------------
@pytest.fixture(scope='module')
def data27(data, pack):
    made = copy.copy(data)
    made.ratings_full = pack['ratings_full']
    made.leagues = pack['leagues']
    made.schedule = pack.get('schedule')
    return made


@pytest.fixture(scope='module')
def steps(pack):
    return pipeline.default_steps(pack)


@pytest.fixture(scope='module')
def built27(base_bytes, data27, steps):
    res = pipeline.build(base_bytes, data27, steps)
    assert res.ok, res.problems[:5]
    return res


def full_of(pack, first, last):
    return next(p for p in pack['ratings_full']['players'] if (p['first'], p['last']) == (first, last))


def record(R, first, last):
    found = R.find_player(first, last)
    assert found, (first, last)
    return found[0]


@pytest.mark.parametrize('first, last', [('Connor', 'McDavid'), ('Sidney', 'Crosby'), ('Cale', 'Makar'),
                                         ('Andrei', 'Vasilevskiy')])
def test_stars_carry_the_full_ratings(built27, pack, first, last):
    R, b = Roster(built27.data), built27.builder
    p = full_of(pack, first, last)
    kind = 'goalie' if p['pos'] == 'G' else 'skater'
    values = dict(zip(pack['ratings_full']['fields'][kind], p['v']))
    prow = record(R, first, last)
    pid = R.P.get(prow, 'game_id')
    t = R.f[schema.FULL_TABLE[kind]]
    row = next(i for i in range(t.cur_rec) if t.get(i, 'game_id') == pid)
    for name in schema.FULL_RATED[kind]:
        assert t.get(row, name) == values[name] - schema.RATING_BASE, (last, name)
    for name in schema.FULL_ASIS[kind]:
        if name != 'playerstyle':
            assert t.get(row, name) == values[name], (last, name)
    cls = ratings.style_class(R.P.get(prow, 'position'))
    assert t.get(row, 'playerstyle') in ratings.STYLE_CHOICES[cls]
    if values['playerstyle'] in ratings.STYLE_CHOICES[cls]:
        assert t.get(row, 'playerstyle') == values['playerstyle']
    assert b.rated_by[pid] == 'full'
    want = ratings.overall_level(b.full_ratings, kind, values['c_overall']) + b.ovr_offset[kind == 'goalie']
    assert b.quality[pid] == pytest.approx(want)


def test_a_del_player_known_by_his_age_takes_the_full_ratings_and_birthdate(built27, pack):
    R, b = Roster(built27.data), built27.builder
    assert b.full_dates > 100
    slots = {t['slot'] for t in pack['leagues']['del']['teams']}
    checked = 0
    for t in pack['leagues']['del']['teams']:
        for fed in t['players']:
            prows = [r for r in R.find_player(fed['first'], fed['last'])
                     if any(slot in slots for _, slot in R.teams_of(r))]
            if len(prows) != 1:
                continue
            prow = prows[0]
            birth = (R.P.get(prow, 'year') + 1910, R.P.get(prow, 'month') + 1, R.P.get(prow, 'day') + 1)
            found = ratings.match_full(b.full_ratings, fed['first'], fed['last'], fed['birth'], fed['pos'] == 'G')
            if not fed.get('birth_approx') or not found or found[1] != 'name' or birth == tuple(fed['birth']):
                continue
            assert birth == tuple(found[0]['birth']), fed['last']     # the full ratings' date, in the year the DEL's age allows
            assert b.rated_by[R.P.get(prow, 'game_id')] == 'full'
            checked += 1
    assert checked > 100


def test_a_player_the_full_ratings_lack_keeps_the_list_or_the_estimate(base_bytes, data27, built27, pack):
    b = built27.builder
    by = set(b.rated_by.values())
    assert by == {'full', 'list', 'estimate'}
    for pid, how in b.rated_by.items():
        if how == 'estimate':
            assert b.full_match(b.R.p_by_id[pid]) is None
    # without McDavid in the full ratings, the ratings list rates him
    lacking = copy.copy(data27)
    lacking.ratings_full = dict(pack['ratings_full'], players=[p for p in pack['ratings_full']['players']
                                                         if (p['first'], p['last']) != ('Connor', 'McDavid')])
    res = pipeline.build(base_bytes, lacking, [pipeline.NHL, pipeline.RATINGS])
    R = Roster(res.data)
    pid = R.P.get(record(R, 'Connor', 'McDavid'), 'game_id')
    assert res.builder.rated_by[pid] == 'list'
    listed = next(p for p in pack['ratings_list'] if p['name'] == 'Connor McDavid')
    t = R.f['yvSd']
    row = next(i for i in range(t.cur_rec) if t.get(i, 'game_id') == pid)
    for label, value in listed['attrs'].items():
        if label in schema.LIST_SKATER and value is not None:
            assert t.get(row, schema.LIST_SKATER[label]) == max(0, min(63, value - schema.RATING_BASE))


def test_the_result_names_where_the_ratings_came_from(built27):
    full, listed, estimated = built27.rating_sources()
    assert full > 4000 and listed and estimated
    line = dict(built27.lines())[pipeline.SECTION_RATINGS]
    assert line == f"{full + listed} current, {estimated} estimated"
    assert f"Ratings: {line}." in built27.summary()
    assert 'current ratings' in pipeline.EXPERIMENTAL


def test_verify_refuses_a_value_the_games_players_never_have(built27, base_bytes):
    R = Roster(built27.data)
    G = R.f['yuHm']
    G.set(0, 'c_consistency', 5)
    source = Roster(base_bytes)
    problems = rating_problems(R, source)
    assert len(problems) == 1 and "consistency 5 is outside 0-2" in problems[0]
    problems = verify(R.f.build(), source, calendar=built27.builder.calendar)[0]
    assert any("consistency 5 is outside 0-2" in p for p in problems), problems[:5]
    assert rating_problems(Roster(built27.data), source) == []


def test_a_second_run_changes_nothing(built27, data27, steps):
    again = pipeline.build(built27.data, data27, steps)
    assert again.ok and again.data == built27.data


def test_a_patch_roster_second_run_changes_nothing(base_bytes, data27, pack):
    from legacy_roster import schedule
    made = copy.copy(data27)
    made.calendar = schedule.ALL_PATCH
    made.leagues = {'ahl': pack['leagues']['ahl']}
    steps = list(pipeline.CORE_STEPS) + [pipeline.SCHEDULE, 'ahl']

    def patch_build(raw):
        res = pipeline.build(raw, made, steps, game_patch=True)
        assert res.ok, res.problems[:5]
        out, problems, _ = pipeline.patch_roster(res, raw, pack, made.season_year)
        assert problems == []
        return out, res

    out, res = patch_build(base_bytes)
    assert res.rating_sources()[0] > 1500
    assert patch_build(out)[0] == out
