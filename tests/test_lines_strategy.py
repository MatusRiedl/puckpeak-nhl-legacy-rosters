"""The Roster editor's own lines and strategies (lines.check_lineup / set_lineup, strategy.py, edits.apply_teams)."""
from legacy_roster import edits, lines, pipeline, strategy, verify
from legacy_roster import layout as L
from legacy_roster.roster import Roster
from legacy_roster.schema import SLOT_TAG

TOR = L.API_TO_SLOT['TOR']


def lineup(R, team):
    """({slot: person key}, {person key: 'C' | 'A'}) of a team in a roster."""
    slots, letters = {}, {}
    for e, prow, _, _, _ in R.team_roster(team):
        who = edits.who_of(R.P, prow)
        for name, tag in SLOT_TAG.items():
            if R.U.get(e, tag):
                slots[name] = who
        if R.U.get(e, 'lcCm') in (1, 2):
            letters[who] = 'CA'[R.U.get(e, 'lcCm') - 1]
    return slots, letters


def view(R, team):
    pos, name = {}, {}
    for e, prow, n, _, _ in R.team_roster(team):
        who = edits.who_of(R.P, prow)
        pos[who], name[who] = 'CLRDG'[R.P.get(prow, 'aljv')], n
    return pos, name


def swapped(slots, a, b):
    out = dict(slots)
    out[a], out[b] = slots[b], slots[a]
    return out


def test_every_team_the_update_lines_up_keeps_the_rules(built):
    R = Roster(built.data)
    for t in range(32):
        slots, letters = lineup(R, t)
        pos, name = view(R, t)
        problems = lines.check_lineup(slots, letters, pos, name)
        if t in (30, 31):       # the community roster's All-Star slots play one forward on two lines: the editor says so
            assert all('twice in lines' in p for p in problems), problems
        else:
            assert problems == [], R.team_name(t)


def test_the_rules_name_what_is_wrong():
    pos = {f"f{k}": 'C' for k in range(12)} | {f"d{k}": 'D' for k in range(6)} | {'g0': 'G', 'g1': 'G', 'x': 'C'}
    name = {k: k.upper() for k in pos}
    slots = {'g1': 'g0', 'g2': 'g1'}
    for group, names in lines.GROUPS:          # inside each group every player once
        f = d = 0
        for s in names:
            if s in slots:
                continue
            if s.endswith(('ld', 'rd')):
                slots[s], d = f"d{d}", d + 1
            else:
                slots[s], f = f"f{f}", f + 1
    letters = {'f0': 'C', 'f1': 'A', 'f2': 'A'}
    assert lines.check_lineup(slots, letters, pos, name) == []
    assert any('goalie' in p for p in lines.check_lineup(dict(slots, l1c='g0'), letters, pos, name))
    assert any('twice' in p for p in lines.check_lineup(dict(slots, l2c='f0'), letters, pos, name))
    assert any('twice' in p for p in lines.check_lineup(dict(slots, l2c='f0'), letters, pos, name, repeats=True))
    assert lines.check_lineup(dict(slots, pp2c=slots['pp1c'], s2=slots['s1']), letters, pos, name, repeats=True) == []
    assert any('twice' in p for p in lines.check_lineup(dict(slots, pp2c=slots['pp1c']), letters, pos, name))
    assert any('special teams' in p for p in lines.check_lineup(dict(slots, s1='x'), letters, pos, name))
    assert any('captain' in p for p in lines.check_lineup(slots, {'f0': 'C', 'f1': 'C', 'f2': 'A'}, pos, name))
    assert any('three letters' in p for p in lines.check_lineup(slots, {'f0': 'C'}, pos, name))
    assert lines.check_lineup(slots, {'f0': 'C'}, pos, name, nhl=False) == []
    everyone = {w: 'C' for w in pos}                       # the player's own lines (0.81.0): any letters, even a goalie's
    assert lines.check_lineup(slots, everyone, pos, name, free_letters=True) == []
    assert lines.check_lineup(slots, {}, pos, name, free_letters=True) == []
    assert any('not on the team' in p for p in lines.check_lineup(slots, {'zz': 'C'}, pos, name, free_letters=True))
    assert lines.slot_label('pp4_2rd') == 'Power play, 4 skaters, unit 2 RD'


def test_own_lines_and_strategies_go_in_after_the_update_and_change_nothing_twice(base_bytes, data, built):
    R = Roster(built.data)
    slots, letters = lineup(R, TOR)
    slots = swapped(swapped(slots, 'l1lw', 'l3lw'), 'l1c', 'l4c')
    captain = next(w for w, l in letters.items() if l == 'C')
    other = next(w for s, w in slots.items() if s == 'l4rw' and w not in letters)
    letters = {(other if w == captain else w): l for w, l in letters.items()}
    plan = {'oz_forecheck': 3, 'forward1_bias1': 9, 'defense3_bias6': 0}
    teams = {str(TOR): {'lines': {'slots': slots, 'letters': letters}, 'strategy': plan}}
    first = pipeline.build(base_bytes, data, team_edits=teams)
    assert first.ok, first.problems[:5]
    R1 = Roster(first.data)
    assert lineup(R1, TOR) == (slots, letters)
    for mirror in L.MIRRORS.get(TOR, []):
        assert lineup(R1, mirror) == (slots, letters)
    got = strategy.read(R1, TOR)
    assert {f: got[f] for f in plan} == plan
    assert any(r[1] == 'own lines' for r in first.log)
    again = pipeline.build(first.data, data, team_edits=teams)
    assert again.ok and again.data == first.data


def test_lines_that_no_longer_fit_are_left_out_and_named(base_bytes, data, built):
    R = Roster(built.data)
    slots, letters = lineup(R, TOR)
    leaving = slots['l1c']
    prow = next(p for _, p, _, _, _ in R.team_roster(TOR) if edits.who_of(R.P, p) == leaving)
    mine = {leaving: {'label': R.name(prow), 'team': 'FA'}}
    res = pipeline.build(base_bytes, data, my_edits=mine, team_edits={str(TOR): {'lines': {'slots': slots,
                                                                                         'letters': letters}}})
    assert res.ok, res.problems[:5]
    assert any(r[1] == 'edit skipped' and 'no longer on the team' in r[3] for r in res.log)
    bad = dict(slots, l1lw=slots['g1'])
    res = pipeline.build(base_bytes, data, team_edits={str(TOR): {'lines': {'slots': bad, 'letters': letters}}})
    assert res.ok and any(r[1] == 'edit skipped' and 'goalie' in r[3] for r in res.log)
    assert lineup(Roster(res.data), TOR)[0]['l1lw'] != slots['g1']


def test_the_strategy_words_are_the_games_menu_in_value_order():
    # read in the game's Strategy menu (lab round 28): Vegas 3 / 3 / 4 / 2 / 1 / 2 / 0 / 2, a LAB Anaheim 1 / 1 / 1 / 0 / 2 / 1 / 2 / 0
    vegas = {'oz_forecheck': 3, 'nz_forecheck': 3, 'opressure': 4, 'dpressure': 2, 'defense': 1, 'pk': 2, 'pp': 0, 'offense1': 2}
    shown = {'oz_forecheck': '1-2-2 Aggressive', 'nz_forecheck': '1-2-2 Blue', 'opressure': 'Full Attack', 'dpressure': 'Normal',
             'defense': 'Staggered', 'pk': 'Diamond', 'pp': 'Shooting', 'offense1': 'Behind the Net'}
    assert {f: dict(strategy.options(f))[v] for f, v in vegas.items()} == shown
    anaheim = {'oz_forecheck': 1, 'nz_forecheck': 1, 'opressure': 1, 'dpressure': 0, 'defense': 2, 'pk': 1, 'pp': 2, 'offense1': 0}
    shown = {'oz_forecheck': '2-3', 'nz_forecheck': '1-4', 'opressure': 'Conservative', 'dpressure': 'Protect Net',
             'defense': 'Tight Point', 'pk': 'Large Box', 'pp': 'Umbrella', 'offense1': 'Overload'}
    assert {f: dict(strategy.options(f))[v] for f, v in anaheim.items()} == shown
    assert sum(strategy.hidden(f) for f in strategy.FIELDS) == 5 + 4 * 2 + 3 * 4
    assert strategy.top('trap_forecheck_bias') == 6 and strategy.top('team_bias1') == 10


def test_a_strategy_outside_the_games_choices_is_refused(base_bytes, built):
    ok, problems = strategy.clean({'oz_forecheck': 9, 'pp': 1, 'nothing': 2, 'team_bias1': True})
    assert ok == {'pp': 1} and len(problems) == 3
    R = Roster(built.data)
    strategy.write(R, TOR, {'oz_forecheck': 7})       # written past the check: verify refuses the save
    problems, _ = verify.verify(R.f.build(), Roster(built.data))
    assert any('Forecheck' in p for p in problems)


def test_verify_refuses_a_goalie_on_a_line(built):
    R = Roster(built.data)
    ents = {name: e for e, _, _, _, _ in R.team_roster(TOR) for name, tag in SLOT_TAG.items() if R.U.get(e, tag)}
    wing, goalie = ents['l1lw'], ents['g1']
    for e, on, off in ((wing, 'g1', 'l1lw'), (goalie, 'l1lw', 'g1')):      # the two swap places
        R.U.set(e, SLOT_TAG[off], 0)
        R.U.set(e, SLOT_TAG[on], 1)
    problems, _ = verify.verify(R.f.build(), Roster(built.data))
    assert any('goalie in a skater slot' in p for p in problems) and any('skater in goal' in p for p in problems)


def test_the_lines_window_offers_every_place_the_game_has():
    """Testers asked to choose who plays on which line, unit and shootout place: all 71 of the game's places are in
    the rules (lines.GROUPS) and in the window's tabs (app/lines.TABS), each once."""
    from legacy_roster.app import lines as window
    in_groups = sorted(slot for _, names in lines.GROUPS for slot in names)
    in_tabs = sorted(slot for _, _, rows in window.TABS for _, names in rows for slot in names)
    assert len(SLOT_TAG) == 71 and in_groups == in_tabs == sorted(SLOT_TAG)


def test_a_team_of_captains_and_a_team_without_letters_save_and_change_nothing_twice(base_bytes, data, built):
    R = Roster(built.data)
    slots, _ = lineup(R, TOR)
    pos, _ = view(R, TOR)
    everyone = {w: 'C' for w, p in pos.items() if p != 'G'}              # a fantasy roster: every skater the captain
    teams = {str(TOR): {'lines': {'slots': slots, 'letters': everyone}}}
    first = pipeline.build(base_bytes, data, team_edits=teams)
    assert first.ok, first.problems[:5]
    assert lineup(Roster(first.data), TOR)[1] == everyone
    assert pipeline.build(first.data, data, team_edits=teams).data == first.data
    teams = {str(TOR): {'lines': {'slots': slots, 'letters': {}}}}      # and no letters at all
    bare = pipeline.build(base_bytes, data, team_edits=teams)
    assert bare.ok, bare.problems[:5]
    assert lineup(Roster(bare.data), TOR)[1] == {}
