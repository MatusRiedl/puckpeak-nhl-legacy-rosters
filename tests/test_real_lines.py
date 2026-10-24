"""Real lines from real games (0.50.4): the provider works lines out of shift charts, the builder lays them over the
dealt lines, and a team whose real lines do not fit keeps what it had."""
import copy
import sys
from collections import Counter
from pathlib import Path

import pytest

from legacy_roster import lines, pipeline, schema
from legacy_roster import layout as L
from legacy_roster.builder import Data
from legacy_roster.roster import Roster

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
from providers import nhl_lines as N  # noqa: E402


# --- the provider -----------------------------------------------------------------------------------------------
def fake_game(trios, d_pairs, pp, pk, goalies=(1, 2)):
    """A read_game result for one team: ids 1-2 goalies, 10-21 forwards (C / L / R in turn), 30-35 defence."""
    pos = {1: 'G', 2: 'G'}
    for i in range(12):
        pos[10 + i] = 'CLR'[i % 3]
    for i in range(6):
        pos[30 + i] = 'D'
    game = {'players': pos, 'toi': {1: 3500, 2: 100}, 'ev': Counter(), 'pp': Counter(), 'pk': Counter(),
            'trios': Counter(), 'pairs': Counter()}
    for trio, secs in trios:
        game['trios'][frozenset(trio)] += secs
        for p in trio:
            game['ev'][p] += secs
    for pair, secs in d_pairs:
        game['pairs'][frozenset(pair)] += secs
        for p in pair:
            game['ev'][p] += secs
    for p, secs in pp:
        game['pp'][p] += secs
    for p, secs in pk:
        game['pk'][p] += secs
    return game


def test_the_most_used_trios_and_pairs_become_the_lines_best_first():
    game = fake_game(
        trios=[((10, 11, 12), 900), ((13, 14, 15), 700), ((16, 17, 18), 500), ((19, 20, 21), 300), ((10, 14, 18), 50)],
        d_pairs=[((30, 31), 800), ((32, 33), 600), ((34, 35), 400)],
        pp=[(10, 60), (11, 60), (12, 50), (30, 60), (31, 55), (13, 40), (14, 35), (15, 30), (32, 30), (33, 25)],
        pk=[(19, 50), (20, 45), (32, 50), (33, 45), (16, 30), (17, 25), (34, 30), (35, 20)])
    slots = N.team_lines([game])
    assert (slots['l1lw'], slots['l1c'], slots['l1rw']) == (11, 10, 12)         # C in the middle, L left, R right
    assert (slots['l2lw'], slots['l2c'], slots['l2rw']) == (14, 13, 15)
    assert (slots['l4lw'], slots['l4c'], slots['l4rw']) == (20, 19, 21)
    assert {slots['l1ld'], slots['l1rd']} == {30, 31} and {slots['l3ld'], slots['l3rd']} == {34, 35}
    assert (slots['g1'], slots['g2']) == (1, 2)                                   # most ice time starts
    assert (slots['pp1c'], slots['pp1lw'], slots['pp1rw']) == (10, 11, 12)
    assert {slots['pp1ld'], slots['pp1rd']} == {30, 31} and {slots['pp2ld'], slots['pp2rd']} == {32, 33}
    assert slots['pp4_1c'] == slots['pp1c'] and slots['pp4_2ld'] == slots['pp2ld']
    assert slots['pk4_1c'] == 19 and slots['pk4_1lw'] == 20 and slots['pk3_1c'] == 19
    assert {slots['pk4_1ld'], slots['pk4_1rd']} == {32, 33}
    # nobody twice inside a group
    for _title, names in lines.GROUPS:
        held = [slots[n] for n in names if n in slots]
        assert len(held) == len(set(held))


def test_a_team_that_dressed_eleven_forwards_gets_no_even_strength_lines():
    game = fake_game(trios=[((10, 11, 12), 900)], d_pairs=[((30, 31), 800)], pp=[], pk=[])
    del game['players'][21]
    slots = N.team_lines([game])
    assert not any(n.startswith('l') for n in slots) and (slots['g1'], slots['g2']) == (1, 2)


def test_a_game_is_read_from_the_box_score_and_the_shift_chart(monkeypatch):
    def player(pid, pos, toi='20:00'):
        return {'playerId': pid, 'position': pos, 'toi': toi}
    box = {'homeTeam': {'abbrev': 'AAA', 'id': 1}, 'awayTeam': {'abbrev': 'BBB', 'id': 2},
           'playerByGameStats': {
               'homeTeam': {'forwards': [player(i, 'CLR'[i % 3]) for i in range(3)],
                            'defense': [player(10, 'D'), player(11, 'D')], 'goalies': [player(20, 'G', '60:00')]},
               'awayTeam': {'forwards': [player(100 + i, 'CLR'[i % 3]) for i in range(3)],
                            'defense': [player(110, 'D'), player(111, 'D')], 'goalies': [player(120, 'G', '60:00')]}}}
    shifts = {'data': []}
    for team_id, ids in ((1, [0, 1, 2, 10, 11, 20]), (2, [100, 101, 102, 110, 111, 120])):
        for pid in ids:
            shifts['data'].append({'typeCode': 517, 'teamId': team_id, 'playerId': pid, 'period': 1,
                                   'startTime': '00:00', 'endTime': '01:00'})
    shifts['data'].append({'typeCode': 505, 'teamId': 1, 'playerId': 0, 'period': 1, 'startTime': '00:30',
                           'endTime': '00:30'})
    # a penalty: team 2 loses a skater for the second minute
    for pid in (100, 101, 102, 110, 111):
        shifts['data'].append({'typeCode': 517, 'teamId': 2, 'playerId': pid, 'period': 1, 'startTime': '01:00',
                               'endTime': '02:00'} if pid != 111 else
                              {'typeCode': 517, 'teamId': 2, 'playerId': 120, 'period': 1, 'startTime': '01:00',
                               'endTime': '02:00'})
    for pid in (0, 1, 2, 10, 11, 20):
        shifts['data'].append({'typeCode': 517, 'teamId': 1, 'playerId': pid, 'period': 1, 'startTime': '01:00',
                               'endTime': '02:00'})
    monkeypatch.setattr(N.datasource, 'http_json', lambda url: box if 'boxscore' in url else shifts)
    monkeypatch.setattr(N, 'game_letters', lambda game_id: ({}, {}))
    game = N.read_game(1)
    assert game['AAA']['ev'][0] == 60 and game['AAA']['pp'][0] == 60 and game['BBB']['pk'][100] == 60
    assert game['AAA']['trios'][frozenset({0, 1, 2})] == 60 and game['AAA']['pairs'][frozenset({10, 11})] == 60
    assert game['BBB']['ev'][100] == 60 and 120 not in game['BBB']['ev']


# --- the builder ------------------------------------------------------------------------------------------------
@pytest.fixture(scope='module')
def lined(base_bytes, data, pack):
    if not pack.get('lines'):
        pytest.skip("the data pack has no lines")
    with_lines = copy.copy(data)
    with_lines.real_lines = pack['lines']
    return with_lines, pipeline.build(base_bytes, with_lines)


def test_the_real_lines_are_played_by_the_teams_they_name(lined, pack):
    with_lines, result = lined
    assert result.ok, result.problems
    b = result.builder
    assert len(b.real_lined) + len(b.real_refused) == len(pack['lines'])
    assert len(b.real_lined) >= 25, b.real_refused
    R = Roster(result.data)
    nhl_id = {p['row']: p['nhl_id'] for p in b.api if p.get('nhl_id') and p['row'] is not None}
    checked = 0
    for code in b.real_lined:
        team = L.API_TO_SLOT[code]
        got, present = {}, set()
        for e in range(R.U.cur_rec):
            if R.U.get(e, 'BSXd') == team:
                who = nhl_id.get(R.p_by_id.get(R.link_to_pid.get(R.U.get(e, 'TWSX'))))
                present.add(who)
                for name, tag in schema.SLOT_TAG.items():
                    if R.U.get(e, tag):
                        got[name] = who
        wanted = pack['lines'][code]['slots']
        for names in (schema.EVEN_STRENGTH, schema.GOALIE_SLOTS):      # a group is played when all its players are there
            ids = [wanted.get(n) for n in names]
            if None in ids or len(set(ids)) != len(ids) or not set(ids) <= present:
                continue
            for n in names:
                if not n.endswith(('ld', 'rd')):                 # a pair may swap sides: the right shot on the right
                    assert got.get(n) == wanted[n], (code, n)
                    checked += 1
            pairs = [n for n in names if n.endswith(('ld', 'rd'))]
            assert sorted(got[n] for n in pairs) == sorted(wanted[n] for n in pairs), code
    assert checked > 300


def test_a_second_build_on_the_real_lines_changes_nothing(lined, data, pack):
    with_lines, result = lined
    again = pipeline.build(result.data, with_lines)
    assert again.ok and again.data == result.data


def test_a_team_whose_real_lines_name_nobody_it_has_keeps_its_lines(base_bytes, data, pack):
    if not pack.get('lines'):
        pytest.skip("the data pack has no lines")
    ghosts = copy.deepcopy(pack['lines'])
    for entry in ghosts.values():
        entry['slots'] = {slot: 999000 + k for k, slot in enumerate(entry['slots'])}
        entry['letters'] = {}
    broken = copy.copy(data)
    broken.real_lines = ghosts
    plain = pipeline.build(base_bytes, data)
    result = pipeline.build(base_bytes, broken)
    assert result.ok and result.builder.real_lined == []
    assert result.data == plain.data
