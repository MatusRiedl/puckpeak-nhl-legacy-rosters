"""Hockey sticks in the colours of the player's NHL team.

A skater's stick is the model number `stick` of his equipment row (table `ajmx`, equipment.py). Its colours are baked
into the model's texture (`rendering/playerstick/texlib_<id>.rpsgl` in the disc's cacherender.big: one 1024 x 128 DXT1
picture, no tint mask), so a stick cannot be tinted like a helmet: a player of an NHL team whose stick shows a colour
the team does not wear gets another model instead, of the same brand: one in a team colour, else a plain one (black,
white, grey or wood). The Roster editor's own choice is applied after the update and wins (`keep` for other callers).

The tables between the markers are made by tools/stick_colours.py from the disc's stick textures (run it again rather
than editing them): CLUSTERS (id -> its colours as (hue in degrees, share of the texture), the biggest first), BRAND
(read off the textures by eye) and CURRENT (the models the game's own roster gives its players: this era's sticks).
Standard library only.
"""
import colorsys
from collections import namedtuple

from . import equipment

CLEAR = 0.06    # a colour covering this share of the texture or more is the stick's colour; less is an accent
NEAR = 25       # degrees of hue: a stick colour this close to one of the team's colours fits the team
DEFAULT = 105   # a brand without a fitting or plain stick gets this one: Bauer Vapor, white / grey, the most worn stick
NHL = range(32)
GOALIE = 4      # cPbu position (aljv) of a goalie: his stick is a goalie stick (table lVMf), not this one

Change = namedtuple('Change', 'slot prow old new')

# --- tables made by tools/stick_colours.py from the game disc's stick textures; run it again rather than editing ---
CLUSTERS = {
    18: ((1, 0.124),),
    24: ((83, 0.097),),
    25: (),
    26: (),
    30: ((354, 0.025),),
    31: ((358, 0.06),),
    32: (),
    33: ((199, 0.102), (47, 0.059)),
    34: ((212, 0.074),),
    35: ((359, 0.11),),
    36: (),
    37: ((0, 0.212),),
    39: ((359, 0.063),),
    40: (),
    41: (),
    45: ((191, 0.051),),
    46: ((50, 0.127),),
    47: ((204, 0.055),),
    48: ((105, 0.089),),
    49: ((13, 0.067),),
    50: (),
    51: ((359, 0.105),),
    52: ((1, 0.099),),
    53: ((356, 0.448),),
    54: ((49, 0.148),),
    55: ((2, 0.095),),
    56: ((359, 0.031),),
    60: (),
    63: (),
    64: (),
    65: ((357, 0.173),),
    67: ((357, 0.077),),
    68: (),
    70: ((14, 0.052),),
    71: ((14, 0.052),),
    72: ((351, 0.079),),
    73: ((351, 0.079),),
    74: (),
    75: (),
    77: ((44, 0.031),),
    78: ((359, 0.042),),
    79: ((5, 0.039),),
    81: (),
    82: ((26, 0.082),),
    83: (),
    84: ((194, 0.153), (13, 0.085)),
    85: (),
    86: ((356, 0.277),),
    87: ((52, 0.094),),
    88: ((87, 0.03),),
    89: (),
    90: ((42, 0.081),),
    91: (),
    92: ((65, 0.073),),
    93: ((15, 0.085),),
    94: (),
    95: ((3, 0.028),),
    96: ((58, 0.138),),
    97: (),
    98: ((359, 0.025),),
    99: ((55, 0.141),),
    100: ((202, 0.114),),
    101: ((202, 0.114),),
    102: ((2, 0.696),),
    103: ((75, 0.064),),
    104: ((47, 0.051),),
    105: ((357, 0.03),),
    106: ((76, 0.072),),
    107: ((196, 0.064),),
    108: ((203, 0.057),),
    109: ((13, 0.116),),
    110: ((354, 0.189),),
    111: ((35, 0.468),),
    112: ((87, 0.024),),
}
BRAND = {
    18: 'Easton', 24: 'TPS', 25: 'Reebok', 26: 'Reebok', 30: 'TPS', 31: 'Sher-Wood', 32: 'Bauer', 33: 'Warrior',
    34: 'Warrior', 35: 'Titan', 36: 'Sher-Wood', 37: 'Bauer', 39: 'Rebellion', 40: 'Sher-Wood', 41: 'Easton',
    45: 'CCM', 46: 'Bauer', 47: 'CCM', 48: 'Warrior', 49: 'Warrior', 50: 'Reebok', 51: 'CCM', 52: 'Easton',
    53: 'Rebellion', 54: 'Warrior', 55: 'Warrior', 56: 'Bauer', 60: 'Easton', 63: 'Warrior', 64: 'CCM', 65: 'CCM',
    67: 'CCM', 68: 'Reebok', 70: 'Bauer', 71: 'Bauer', 72: 'CCM', 73: 'CCM', 74: 'Easton', 75: 'Easton',
    77: 'Easton', 78: 'Bauer', 79: 'Sher-Wood', 81: 'Easton', 82: 'Easton', 83: 'Warrior', 84: 'Warrior',
    85: 'Easton', 86: 'CCM', 87: 'CCM', 88: 'Reebok', 89: 'Bauer', 90: 'Bauer', 91: 'Sher-Wood', 92: 'Winnwell',
    93: 'Winnwell', 94: 'Busch', 95: 'Sher-Wood', 96: 'STX', 97: 'STX', 98: 'Warrior', 99: 'CCM', 100: 'Warrior',
    101: 'Warrior', 102: 'CCM', 103: 'CCM', 104: 'Easton', 105: 'Bauer', 106: 'Graf', 107: 'STX', 108: 'Bauer',
    109: 'Sher-Wood', 110: 'STX', 111: 'Bauer', 112: 'CCM',
}
CURRENT = frozenset({35, 82, 84, 85, 86, 87, 95, 98, 99, 102, 103, 104, 105, 107, 108, 109, 110, 111, 112})
# --- end of the made tables ---

DRAWABLE = frozenset(CLUSTERS)   # the models the game has a texture for (others are drawn plain blue)


def hue_name(hue):
    """A word for a hue in degrees."""
    for name, top in (('red', 12), ('orange', 40), ('yellow', 70), ('green', 160), ('teal', 190), ('blue', 260),
                      ('purple', 290), ('pink', 340)):
        if hue < top:
            return name
    return 'red'


def colours(stick):
    """The stick's own colours: [(hue, share)] of the colours that cover CLEAR or more of its texture."""
    return [(hue, share) for hue, share in CLUSTERS.get(stick, ()) if share >= CLEAR]


COLOURS = {i: hue_name(colours(i)[0][0]) if colours(i) else 'neutral' for i in CLUSTERS}


def hue_of(rgb):
    """The hue (degrees) of a team colour, or None for black, white, grey and silver."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return round(h * 360) % 360 if s >= 0.40 and v >= 0.20 else None


def _apart(a, b):
    return min((a - b) % 360, (b - a) % 360)


def team_colours(R, slot):
    """The colours a team wears: Utah, Seattle and Vegas (slots 22, 30, 31) those of builder.NHL_LOOK (the roster's
    stock team colours there are still Arizona's / the All-Stars'), the others their two team colours (ttOk) and their
    stock colours (sozv, up to three)."""
    from .builder import NHL_LOOK
    if slot in NHL_LOOK:
        return [NHL_LOOK[slot][2], NHL_LOOK[slot][3]]
    T = R.T
    out = [tuple(T.get(slot, f"{kind}color_{c}") for c in 'rgb') for kind in ('primary', 'secondary')]
    S = R.f['sozv']
    rows = sorted((S.get(i, 'colorid'), i) for i in range(S.cur_rec) if S.get(i, 'team') == slot)
    out += [tuple(S.get(i, f"color_{c}") for c in 'rgb') for _cid, i in rows]
    return out


def fits(stick, hues):
    """Every colour of the stick is near one of the team's hues (a plain stick fits every team)."""
    return all(any(_apart(h, t) <= NEAR for t in hues) for h, _share in colours(stick))


def pick(stick, hues):
    """The stick a player of a team with these hues gets instead of `stick`: the same brand's in a team colour (this
    era's first, the closest hue first), else its plain one (this era's first), else DEFAULT."""
    brand = BRAND.get(stick)
    best = []
    for other in sorted(CLUSTERS):
        if other == stick or BRAND.get(other) != brand or not fits(other, hues):
            continue
        own = colours(other)
        near = max(min(_apart(h, t) for t in hues) for h, _share in own) if own else 0
        best.append((0 if own else 1, other not in CURRENT, near,
                     sum(share for _h, share in CLUSTERS[other]), other))
    return min(best)[-1] if best else DEFAULT


def team_sticks(R, colours_of_team=team_colours, keep=(), skip=()):
    """Give every skater of an NHL team (slots 0-31) whose stick shows a colour his team does not wear a stick that
    fits (`pick`). `colours_of_team(R, slot)` -> [(r, g, b)]; `keep`: player rows (cPbu) to leave alone (their own
    choice); `skip`: roster entries (table U) that are on their way out (the builder's `deleted`: a player's old place
    on another team). Writes table ajmx and returns [Change(slot, prow, old, new)] in roster order; a second run
    changes nothing."""
    A, P, U = R.f[equipment.TABLE], R.P, R.U
    stick_tag = equipment.tag('stick')
    rows = equipment.row_of(A)
    hues_of, seen, changes = {}, set(keep), []
    for slot, entry in sorted((U.get(i, 'BSXd'), i) for i in range(U.cur_rec) if U.get(i, 'BSXd') in NHL):
        if entry in skip:
            continue
        prow = R.p_by_id.get(R.link_to_pid.get(U.get(entry, 'TWSX')))
        if prow is None or prow in seen or P.get(prow, 'aljv') == GOALIE:
            continue
        seen.add(prow)
        row = rows.get(P.get(prow, 'zIBw'))
        if row is None:
            continue
        old = A.get(row, stick_tag)
        if slot not in hues_of:
            hues_of[slot] = [h for h in (hue_of(c) for c in colours_of_team(R, slot)) if h is not None]
        if old not in CLUSTERS or fits(old, hues_of[slot]):
            continue
        new = pick(old, hues_of[slot])
        A.set(row, stick_tag, new)
        changes.append(Change(slot, prow, old, new))
    return changes


def worn(R):
    """The stick models the roster's skaters carry."""
    A = R.f[equipment.TABLE]
    stick_tag = equipment.tag('stick')
    return {A.get(i, stick_tag) for i in range(A.cur_rec)}


def problems(R, also=()):
    """Sticks the game cannot draw (it draws them plain blue): one line per model. `also`: models to accept anyway
    (for example `worn(source)`: what the roster carried before the update)."""
    A = R.f[equipment.TABLE]
    stick_tag = equipment.tag('stick')
    count = {}
    for i in range(A.cur_rec):
        n = A.get(i, stick_tag)
        if n not in DRAWABLE and n not in also:
            count[n] = count.get(n, 0) + 1
    return [f"{c} player(s) carry stick model {n}, which the game cannot draw" for n, c in sorted(count.items())]
