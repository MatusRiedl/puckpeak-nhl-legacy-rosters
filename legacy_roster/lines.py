"""Deal a team's 71 line slots from scratch, by rating and position.

Used for teams that have no line structure of their own to copy (rebuilt clubs, teams the base
left empty). The rules follow what every team in the stock EA roster satisfies:
  * 20 players dress: 12 forwards on four lines, 6 defencemen in three pairs, 2 goalies;
  * every slot has exactly one holder, and only dressed players hold special-team slots;
  * nobody appears twice inside the same group of units.
"""
from . import schema

S = schema.SLOT_TAG  # 'l1c' -> field tag

# skater attributes used to rank players for special teams
OFFENCE = ('VlLd', 'oRUd', 'YqXz', 'iCvN', 'ObeE')      # off. awareness, passing, puck control, deking, wrist accuracy
DEFENCE = ('OTvp', 'TUty', 'zRrS')                      # def. awareness, stick checking, shot blocking
SHOOTOUT = ('iCvN', 'ObeE', 'YqXz')                     # deking, wrist accuracy, puck control


class NotEnoughPlayers(Exception):
    pass


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
    by_q = lambda group: sorted(group, key=lambda e: (-b.q(e), e))

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
    for k in range(4):
        lw, rw = _sides(P, b, wings[2 * k], wings[2 * k + 1])
        lines.append((lw, centres[k], rw))
        slots[f"l{k + 1}lw"], slots[f"l{k + 1}c"], slots[f"l{k + 1}rw"] = lw, centres[k], rw
    pairs = [_pair(P, b, d6[2 * k], d6[2 * k + 1]) for k in range(3)]
    for k, (ld, rd) in enumerate(pairs):
        slots[f"l{k + 1}ld"], slots[f"l{k + 1}rd"] = ld, rd
    slots['g1'], slots['g2'] = goalies[0], goalies[1]

    best = lambda group, key: sorted(group, key=lambda e: (-key(e), -b.q(e), e))
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
