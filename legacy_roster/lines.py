"""Deal a team's 71 line slots from scratch, by rating and position.

Used for teams that have no line structure of their own to copy (rebuilt clubs, teams the base
left empty). The rules follow what every team in the game's own roster satisfies:
  * 20 players dress: 12 forwards on four lines, 6 defencemen in three pairs, 2 goalies;
  * every slot has exactly one holder, and only dressed players hold special-team slots;
  * nobody appears twice inside the same group of units.
"""
from . import schema

S = schema.SLOT_TAG  # 'l1c' -> field tag
# the wing slots of the four even-strength lines, then every other wing slot: tag -> position code
_LINE_WINGS = {S[f"l{k}{w}"]: 1 if w == 'lw' else 2 for k in range(1, 5) for w in ('lw', 'rw')}
_OTHER_WINGS = {tag: 1 if name.endswith('lw') else 2 for name, tag in S.items() if name.endswith(('lw', 'rw'))}
# a winger plays his own side unless a winger of the other side is this much better (overall points)
SIDE_MARGIN = 5

# skater attributes used to rank players for special teams
OFFENCE = ('VlLd', 'oRUd', 'YqXz', 'iCvN', 'ObeE')      # off. awareness, passing, puck control, deking, wrist accuracy
DEFENCE = ('OTvp', 'TUty', 'zRrS')                      # def. awareness, stick checking, shot blocking
SHOOTOUT = ('iCvN', 'ObeE', 'YqXz')                     # deking, wrist accuracy, puck control


class NotEnoughPlayers(Exception):
    pass


_LINE_ROLE = {S[f"l{k}{s}"]: role for k in range(1, 5) for s, role in
              (('lw', 'W'), ('rw', 'W'), ('c', 'C'), ('ld', 'D'), ('rd', 'D')) if f"l{k}{s}" in S}
_LINE_ROLE.update({S['g1']: 'G', S['g2']: 'G'})


def slot_role(slots):
    """The position class (G, D, C, W) a set of line slots is for, from its even-strength line or
    goalie slot; None when it holds none (only special-team or extra slots)."""
    roles = {_LINE_ROLE[f] for f in slots if f in _LINE_ROLE}
    return roles.pop() if len(roles) == 1 else None


def wing_side(slots):
    """The position code (1 LW, 2 RW) of the side a set of line slots plays on: its even-strength
    line slot decides, then any other wing slot. None when the set holds no wing slot."""
    for table in (_LINE_WINGS, _OTHER_WINGS):
        sides = {table[f] for f in slots if f in table}
        if len(sides) == 1:
            return sides.pop()
    return None


def _wing_pairs(P, b, wings, by_q):
    """Four (left, right) pairs from eight wingers, best line first: the k-th best left wing with the
    k-th best right wing; when one side runs short, the best of the others fills in."""
    left = by_q(e for e in wings if P.get(b.prow_of_entry(e), 'aljv') == 1)
    right = by_q(e for e in wings if P.get(b.prow_of_entry(e), 'aljv') == 2)
    rest = by_q(e for e in wings if e not in left and e not in right)
    pairs = []
    for _ in range(len(wings) // 2):
        lw = (left or rest or right).pop(0)
        rw = (right or rest or left).pop(0)
        pairs.append((lw, rw))
    return pairs


def _sides(P, b, x, y):
    """(left wing, right wing) for two wingers, each on his natural side where possible."""
    px, py = P.get(b.prow_of_entry(x), 'aljv'), P.get(b.prow_of_entry(y), 'aljv')
    if px == 2 and py != 2 or py == 1 and px != 1:
        return y, x
    return x, y


def _pair(P, b, x, y):
    """(left defence, right defence): a right shot goes on the right when the pair has one of each."""
    if P.get(b.prow_of_entry(x), 'pkRG') == 1 and P.get(b.prow_of_entry(y), 'pkRG') == 0:
        return y, x
    return x, y


def build_lines(b, team):
    """Clear and re-deal every line slot and the dressed flag of `team` (b is the Builder)."""
    U, P = b.U, b.P
    ents = b.entries_on(team)
    pos = {e: P.get(b.prow_of_entry(e), 'aljv') for e in ents}
    skater_row = b.ai_row['yvSd']

    def score(fields):
        def f(e):
            row = skater_row.get(b.pid_of_entry(e))
            if row is None:
                return b.q(e)
            return sum(b.R.f['yvSd'].get(row, n) for n in fields) / len(fields)
        return f
    off, dfn, sho = score(OFFENCE), score(DEFENCE), score(SHOOTOUT)
    # ties go by the player's id, which never changes (an entry's row does, between runs)
    by_q = lambda group: sorted(group, key=lambda e: (-b.q(e), b.pid_of_entry(e), e))

    goalies = by_q(e for e in ents if pos[e] == 4)
    defence = by_q(e for e in ents if pos[e] == 3)
    forwards = by_q(e for e in ents if pos[e] in (0, 1, 2))
    if len(goalies) < 2 or len(defence) + len(forwards) < 18:
        raise NotEnoughPlayers(f"{b.R.team_name(team)}: {len(goalies)} goalies, {len(defence)} defencemen, "
                               f"{len(forwards)} forwards -- cannot dress 20")
    # short at one position: the spare players of the other fill in
    while len(defence) < 6:
        defence.append(forwards.pop())
    while len(forwards) < 12:
        forwards.append(defence.pop())
    d6, f12 = defence[:6], forwards[:12]

    centres = [e for e in f12 if pos[e] == 0][:4]
    wings = [e for e in f12 if e not in centres]
    while len(centres) < 4:          # too few natural centres: the best remaining forward plays centre
        centres.append(wings.pop(0))
    centres = by_q(centres)

    slots = {}
    lines = []
    for k, (lw, rw) in enumerate(_wing_pairs(P, b, wings, by_q)):
        lines.append((lw, centres[k], rw))
        slots[f"l{k + 1}lw"], slots[f"l{k + 1}c"], slots[f"l{k + 1}rw"] = lw, centres[k], rw
    pairs = [_pair(P, b, d6[2 * k], d6[2 * k + 1]) for k in range(3)]
    for k, (ld, rd) in enumerate(pairs):
        slots[f"l{k + 1}ld"], slots[f"l{k + 1}rd"] = ld, rd
    slots['g1'], slots['g2'] = goalies[0], goalies[1]

    best = lambda group, key: sorted(group, key=lambda e: (-key(e), -b.q(e), b.pid_of_entry(e), e))
    # power play: the two most dangerous centres, the four most dangerous other forwards
    pp_c = best(centres, off)[:2]
    pp_w = best([e for e in f12 if e not in pp_c], off)[:4]
    pp_d = best(d6, off)[:4]
    for k in range(2):
        lw, rw = _sides(P, b, pp_w[2 * k], pp_w[2 * k + 1])
        ld, rd = _pair(P, b, pp_d[2 * k], pp_d[2 * k + 1])
        slots[f"pp{k + 1}lw"], slots[f"pp{k + 1}c"], slots[f"pp{k + 1}rw"] = lw, pp_c[k], rw
        slots[f"pp{k + 1}ld"], slots[f"pp{k + 1}rd"] = ld, rd
        slots[f"pp4_{k + 1}lw"], slots[f"pp4_{k + 1}c"] = pp_w[2 * k], pp_c[k]
        slots[f"pp4_{k + 1}ld"], slots[f"pp4_{k + 1}rd"] = ld, rd
    # penalty kill: the best defensive centres and forwards, the best defensive pairs
    pk_c = best(centres, dfn)[:2]
    pk_w = best([e for e in f12 if e not in pk_c], dfn)[:2]
    pk_d = best(d6, dfn)[:4]
    for k in range(2):
        ld, rd = _pair(P, b, pk_d[2 * k], pk_d[2 * k + 1])
        slots[f"pk4_{k + 1}lw"], slots[f"pk4_{k + 1}c"] = pk_w[k], pk_c[k]
        slots[f"pk4_{k + 1}ld"], slots[f"pk4_{k + 1}rd"] = ld, rd
        slots[f"pk3_{k + 1}c"], slots[f"pk3_{k + 1}ld"], slots[f"pk3_{k + 1}rd"] = pk_c[k], ld, rd
    # overtime: three units of a centre, the best remaining forward and a pair
    ot_w = best([e for e in f12 if e not in centres[:3]], off)[:3]
    for k in range(3):
        slots[f"ot_{k + 1}lw"], slots[f"ot_{k + 1}c"] = ot_w[k], centres[k]
        slots[f"ot_{k + 1}ld"], slots[f"ot_{k + 1}rd"] = pairs[k]
    for k, e in enumerate(best(f12, sho)[:5]):
        slots[f"s{k + 1}"] = e
    slots['x1'], slots['x2'] = by_q(f12)[:2]

    assert set(slots) == set(S), "line builder must fill every slot"
    for e in ents:
        for f in b.flags + ['jZSh']:
            U.set(e, f, 0)
    for name, e in slots.items():
        U.set(e, S[name], 1)
    for e in set(slots.values()):
        U.set(e, 'jZSh', 1)
    return slots


def lineup_flaws(b, team, ents=None):
    """What verify.structure would hold against `team`'s lines now, by the players' real positions ([] when
    nothing): a slot held twice or by nobody, a dressed flag that disagrees with the slots, a goalie out of goal
    or a skater in it, not 20 dressed with 2 goalies and at least 6 defencemen. Kept lines whose players changed
    position (NHL.com) can break the last rule without anybody moving; such a team is dealt again. `ents`: the
    team's entries when the caller has them."""
    U = b.U
    ents = b.entries_on(team) if ents is None else ents
    if not ents:
        return []
    goal = {S['g1'], S['g2']}
    pos = {e: b.P.get(b.prow_of_entry(e), 'aljv') for e in ents}
    held = {}
    for e in ents:
        for f in b.flags:
            if U.get(e, f):
                held[f] = held.get(f, 0) + 1
    flaws = []
    if any(n > 1 for n in held.values()):
        flaws.append('a slot held twice')
    if len(held) != len(b.flags):
        flaws.append(f"{len(held)} of {len(b.flags)} slots held")
    if any(bool(U.get(e, 'jZSh')) != any(U.get(e, f) for f in b.flags) for e in ents):
        flaws.append('dressed flag and slots disagree')
    if any(U.get(e, f) and (f in goal) != (pos[e] == 4) for e in ents for f in b.flags):
        flaws.append('a goalie out of goal or a skater in goal')
    dressed = [e for e in ents if U.get(e, 'jZSh')]
    g, d = sum(1 for e in dressed if pos[e] == 4), sum(1 for e in dressed if pos[e] == 3)
    if len(dressed) != 20 or g != 2 or d < 6:
        flaws.append(f"{len(dressed)} dressed, {g} G, {d} D")
    return flaws


# --- lines the player sets (Roster editor) -----------------------------------------------------------
# the groups of units; inside one group a player holds one slot at most (as every team of the game's own roster)
GROUPS = (('Lines', schema.EVEN_STRENGTH), ('Goalies', schema.GOALIE_SLOTS), ('Power play', schema.POWER_PLAY),
          ('Power play, 4 skaters', schema.POWER_PLAY_4), ('Penalty kill, 4 skaters', schema.PENALTY_KILL_4),
          ('Penalty kill, 3 skaters', schema.PENALTY_KILL_3), ('Overtime', schema.OVERTIME),
          ('Shootout', schema.SHOOTOUT), ('Extra attackers', schema.EXTRA_ATTACKER))
LETTERS = {1: 'C', 2: 'A'}
_SPOT = {'lw': 'LW', 'c': 'C', 'rw': 'RW', 'ld': 'LD', 'rd': 'RD'}


def slot_label(name):
    """'l1lw' -> 'Line 1 LW', 'l2ld' -> 'Pair 2 LD', 'pp4_1c' -> 'Power play, 4 skaters, unit 1 C', 's3' ->
    'Shooter 3', 'g1' -> 'Starting goalie'."""
    if name in ('g1', 'g2'):
        return 'Starting goalie' if name == 'g1' else 'Backup goalie'
    if name[0] == 's':
        return f"Shooter {name[1]}"
    if name[0] == 'x':
        return f"Extra attacker {name[1]}"
    spot = _SPOT[name[-2:] if name[-2:] in _SPOT else name[-1:]]
    head = name[:-len(spot)]
    if head[0] == 'l':
        return f"{'Pair' if spot in ('LD', 'RD') else 'Line'} {head[1]} {spot}"
    group = {'pp': 'Power play', 'pp4_': 'Power play, 4 skaters', 'pk4_': 'Penalty kill, 4 skaters',
             'pk3_': 'Penalty kill, 3 skaters', 'ot_': 'Overtime'}[head[:-1]]
    return f"{group}, unit {head[-1]} {spot}"


def lineup(b, team):
    """The team's lines as they are: ({slot name: entry}, {entry: 'C' | 'A'})."""
    U = b.U
    slots, letters = {}, {}
    for e in b.entries_on(team):
        for name, tag in S.items():
            if U.get(e, tag):
                slots.setdefault(name, e)
        if U.get(e, 'lcCm') in LETTERS:
            letters[e] = LETTERS[U.get(e, 'lcCm')]
    return slots, letters


def check_lineup(slots, letters, pos, name, nhl=True, repeats=False):
    """What is wrong with a team's lines as plain sentences ([] when the game can play them).

    `slots` {slot name: player}, `letters` {player: 'C' | 'A'}, `pos` {player on the team: 'C' 'L' 'R' 'D' 'G'},
    `name` {player: his name}. The rules are verify.py's and those every team of the game's own roster keeps: every
    slot has a player of the team, goalies only in goal and only goalies there, nobody twice in one group, the 20 of
    the four lines, three pairs and two goalies dress (with at least 6 defencemen) and only they play on special teams,
    letters only on skaters of the team: one captain at most, and on an NHL team (`nhl`) three letters in all.
    `repeats`: the player's own lines may use one player in several places of a special-team group (power play,
    penalty kill, overtime, shootout, extra attackers); the four lines, three pairs and two goalies still need 20
    different players, the game dresses 20."""
    problems = []
    for group, names in GROUPS:
        seen = {}
        for slot in names:
            who = slots.get(slot)
            if who is None:
                problems.append(f"{slot_label(slot)} has no player.")
            elif who not in pos:
                problems.append(f"{slot_label(slot)}: {name.get(who, 'this player')} is not on the team.")
            elif (pos[who] == 'G') != (slot in ('g1', 'g2')):
                problems.append(f"{name[who]} is a goalie: he can only play in goal." if pos[who] == 'G' else
                                f"{slot_label(slot)}: only a goalie can play in goal.")
            elif who in seen and not (repeats and group not in ('Lines', 'Goalies')):
                problems.append(f"{name[who]} is twice in {group.lower()} ({slot_label(seen[who])}, {slot_label(slot)}).")
            else:
                seen[who] = slot
    if problems:
        return problems
    dressed = {slots[s] for s in schema.EVEN_STRENGTH + schema.GOALIE_SLOTS}
    for slot in sorted(set(S) - set(schema.EVEN_STRENGTH + schema.GOALIE_SLOTS), key=list(S).index):
        if slots[slot] not in dressed:
            problems.append(f"{slot_label(slot)}: {name[slots[slot]]} is not in the four lines and three pairs "
                            "(only they play on special teams).")
    d = sum(1 for who in dressed if pos[who] == 'D')
    if d < 6:
        problems.append(f"The lineup has {d} defencemen: the game needs at least 6.")
    for who, letter in sorted(letters.items(), key=lambda kv: (kv[1], name.get(kv[0], ''))):
        if who not in pos:
            problems.append(f"{name.get(who, 'A player')} wears a letter but is not on the team.")
        elif pos[who] == 'G':
            problems.append(f"{name[who]} is a goalie: a goalie cannot wear a letter.")
    c, a = list(letters.values()).count('C'), list(letters.values()).count('A')
    if c > 1:
        problems.append(f"A team has one captain at most (now {c}).")
    elif nhl and c + a != 3:
        problems.append(f"An NHL team has three letters: a captain and two alternates, or three alternates "
                        f"(now {c + a}).")
    elif not nhl and a > 3 - c:
        problems.append(f"A team has three letters at most (now {c + a}).")
    return problems


def set_lineup(b, team, slots, letters):
    """Write lines the player set: `slots` {slot name: entry}, `letters` {entry: 'C' | 'A'} (checked with
    check_lineup first). Every slot flag, the dressed flag and the letters of the team's entries are written anew;
    the team's mirror copies follow (sync_mirrors)."""
    U = b.U
    code = {v: k for k, v in LETTERS.items()}
    for e in b.entries_on(team):
        for f in b.flags + ['jZSh']:
            U.set(e, f, 0)
        U.set(e, 'lcCm', code.get(letters.get(e), 0))
    for slot, e in slots.items():
        U.set(e, S[slot], 1)
        U.set(e, 'jZSh', 1)
    if team in b.mirrors:
        b.sync_mirrors()
