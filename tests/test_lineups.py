"""Every team that must dress a legal 20 does, by its players' real positions: NHL.com's positions change a
defenceman into a winger (kept lines are dealt again), and a team left short gets the players it misses."""
import copy
from collections import Counter

from legacy_roster import gamepatch, pipeline, schedule
from legacy_roster import layout as L
from legacy_roster.leagues.clubs import affiliates
from legacy_roster.roster import Roster
from legacy_roster.verify import structure

FILL = ('stays to fill the line-up', 'called up to fill the line-up', 'signed to fill the line-up')


def _at_wing(data, names):
    """`data` with NHL.com listing the players `names` {(first, last)} at left wing."""
    made = copy.copy(data)
    made.nhl_players = [dict(p, pos='L') if (p['first'], p['last']) in names else p for p in data.nhl_players]
    return made


def _dressed(raw, team):
    """Team `team`'s dressed players of a save by position letter (C L R D G), as verify counts them."""
    _, teams = structure(Roster(raw))
    return teams[team]['dressed'], teams[team]['positions']


def _defencemen(built, raw):
    """{NHL slot: [(first, last, dressed)]} of the NHL.com defencemen the build placed, in NHL.com's order."""
    R = Roster(raw)
    U, P = R.U, R.P
    dressed = {}
    for i in range(U.cur_rec):
        dressed[R.link_to_pid[U.get(i, 'TWSX')], U.get(i, 'BSXd')] = bool(U.get(i, 'jZSh'))
    out = {}
    for p in built.builder.api:
        if p['pos'] == 'D' and p['row'] is not None:
            slot = L.API_TO_SLOT[p['team']]
            out.setdefault(slot, []).append((p['first'], p['last'], dressed.get((P.get(p['row'], 'zIBw'), slot), False)))
    return out


def test_a_defenceman_now_a_winger_on_a_team_whose_lines_are_kept_leaves_six_defencemen(built, data):
    # a roster this tool made keeps the lines of a team nobody joined or left; NHL.com now lists one of its
    # dressed defencemen at left wing (Ottawa's Zub, 2026-10-18: "dresses 20 players (... 5 D, 2 G)")
    team, d = next((t, ds) for t, ds in sorted(_defencemen(built, built.data).items()) if len(ds) >= 7)
    first, last, _ = next(x for x in d if x[2])
    moved = _at_wing(data, {(first, last)})
    res = pipeline.build(built.data, moved)
    assert res.ok, res.problems[:5]
    assert [r[1:4] for r in res.log if r[2] == f"{first} {last}" and r[1] == 'position changed'] \
        == [['position changed', f"{first} {last}", 'D to LW']]
    count, pos = _dressed(res.data, team)
    assert count == 20 and pos['G'] == 2 and pos['D'] >= 6
    assert pipeline.build(res.data, moved).data == res.data            # a second run: the same bytes


def _farm_room(raw):
    """{NHL slot: (defencemen, skaters)} of each NHL team's farm club in a save."""
    R = Roster(raw)
    room = {}
    for ahl, nhl in affiliates(R).items():
        on = Counter('G' if R.P.get(prow, 'aljv') == 4 else 'D' if R.P.get(prow, 'aljv') == 3 else 'F'
                     for _i, prow, *_ in R.team_roster(ahl) if prow is not None)
        room[nhl] = (on['D'], on['D'] + on['F'])
    return room


def test_a_team_left_with_too_few_defencemen_gets_them_and_a_second_run_keeps_them(base_bytes, built, data):
    # a farm club with defencemen to spare: it gives one (it keeps a dressable 20), then free agents come
    room = _farm_room(built.data)
    team, d = next((t, ds) for t, ds in sorted(_defencemen(built, built.data).items())
                   if len(ds) >= 7 and room.get(t, (0, 0))[0] >= 7 and room[t][1] >= 19)
    moved = _at_wing(data, {(first, last) for first, last, _ in d[4:]})     # four defencemen left on NHL.com
    res = pipeline.build(base_bytes, moved)
    assert res.ok, res.problems[:5]
    came = [r for r in res.log if r[0] == L.SLOT_TO_API[team] and r[1] in FILL]
    assert came and all('so the team can dress 20' in r[3] for r in came)
    assert any(r[1] == 'called up to fill the line-up' for r in came), came
    count, pos = _dressed(res.data, team)
    assert count == 20 and pos['G'] == 2 and pos['D'] >= 6
    again = pipeline.build(res.data, moved)
    assert again.ok and again.data == res.data                          # the same players stay, byte for byte
    stay = {r[2] for r in again.log if r[0] == L.SLOT_TO_API[team] and r[1] in ('stays to fill the line-up',
                                                                              'stays under contract')}
    assert stay >= {r[2] for r in came}


def test_a_patch_roster_turned_back_with_a_defenceman_now_a_winger_stays_valid(base_bytes, built, data, pack):
    # the owner's case (2026-10-18): a patch roster, Unpatch, update; NHL.com moved a dressed defenceman up front
    steps = list(pipeline.CORE_STEPS) + [pipeline.SCHEDULE, 'ahl']
    patch = copy.copy(data)
    patch.schedule, patch.leagues = pack['schedule'], {'ahl': pack['leagues']['ahl']}
    patch.calendar = schedule.ALL_PATCH
    res = pipeline.build(base_bytes, patch, steps, game_patch=True)
    assert res.ok, res.problems[:5]
    out, problems, _ = pipeline.patch_roster(res, base_bytes, pack, patch.season_year)
    assert problems == [] and gamepatch.is_patch_roster(Roster(out))

    team, d = next((t, ds) for t, ds in sorted(_defencemen(res, out).items()) if len(ds) >= 7)
    first, last, _ = next(x for x in d if x[2])
    back_data = _at_wing(copy.copy(patch), {(first, last)})
    back_data.calendar = schedule.THIRTY
    own = Roster(base_bytes)
    back = pipeline.build(out, back_data, steps, normal_from=own)
    assert back.ok and back.turned_back, back.problems[:5]
    count, pos = _dressed(back.data, team)
    assert count == 20 and pos['G'] == 2 and pos['D'] >= 6
    assert pipeline.build(back.data, back_data, steps, normal_from=own).data == back.data
