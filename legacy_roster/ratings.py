"""Write the current ratings into the save's skater / goalie attribute tables.

The field for every attribute is known exactly from the game's schema (see schema.py); the
stored value is the rating minus 36 (6 bits: ratings 36..99).
"""
from . import matching
from .matching import norm, same_first_name
from .schema import ASIS_RANGE, LIST_GOALIE, LIST_SKATER, FULL_ASIS, FULL_RATED, FULL_TAG, RATING_BASE
from .schema_names import FIELDS

SKATER_TABLE, GOALIE_TABLE = 'yvSd', 'yuHm'


def is_goalie(p):
    return (p.get('position') or '').startswith('G')


def match_players(R, players):
    """[(rated player, cPbu row)] matched by last name + birthdate (or full name). A match by last name and birth year
    alone (matching.match's 'last+year') also needs a first name that fits: the game's own roster's Liiga defenceman Jiri
    Pärssinen (2002) is not the list's Juuso (2001), and the Liiga step creates him without that rating (list_rating_for),
    so the next run's ratings step must not give it to him."""
    lst = []
    for p in players:
        if not p.get('birth'):
            continue
        first, _, last = p['name'].partition(' ')
        lst.append({'first': first, 'last': last, 'birth': tuple(p['birth']), 'src': p})
    matching.match(R, lst)
    fits = lambda q: q['how'] != 'last+year' or matching.same_first_name(matching.norm(R.P.get(q['row'], 'PedH')),
                                                                         matching.norm(q['first']))
    return [(q['src'], q['row']) for q in lst if q['row'] is not None and fits(q)]


def clamp(v):
    return max(0, min(63, v))


def attribute_fields(table):
    """The attribute fields (c_*) of a rating table the ratings list has."""
    amap = LIST_GOALIE if table.name == GOALIE_TABLE else LIST_SKATER
    return sorted(set(amap.values()))


def level(table, row, fields=None):
    """A player's level on the rating scale: mean of his attributes (stored value + 36)."""
    fields = fields or attribute_fields(table)
    return sum(table.get(row, f) for f in fields) / len(fields) + RATING_BASE


def overall_offset(players):
    """Median of (the list's overall - mean attribute rating), per position group, from fully rated players.

    Lets a player who only has an overall be placed at the right level."""
    out = {}
    for goalie, amap in ((False, LIST_SKATER), (True, LIST_GOALIE)):
        diffs = []
        for p in players:
            if is_goalie(p) != goalie or not p.get('ovr'):
                continue
            vals = [v for a, v in p.get('attrs', {}).items() if a in amap and v is not None]
            if len(vals) >= 10:
                diffs.append(p['ovr'] - sum(vals) / len(vals))
        diffs.sort()
        out[goalie] = diffs[len(diffs) // 2] if diffs else 0.0
    return out


def write_attributes(table, row, p, ovr_offset):
    """Write one rated player. Returns the number of attributes written.

    Published attributes are stored exactly. A player with fewer than three published attributes
    but an overall has all his attributes shifted so his level matches that overall. Fields the list
    does not publish (potential, traits, growth) are left alone."""
    amap = LIST_GOALIE if table.name == GOALIE_TABLE else LIST_SKATER
    known = {amap[a]: v for a, v in p.get('attrs', {}).items() if a in amap and v is not None}
    if len(known) >= 3:
        for field, v in known.items():
            table.set(row, field, clamp(v - RATING_BASE))
        return len(known)
    if not p.get('ovr'):
        return 0
    fields = attribute_fields(table)
    for _ in range(6):   # values pinned at the bottom or top of the scale absorb part of a shift
        delta = round(p['ovr'] - ovr_offset - level(table, row, fields))
        if not delta:
            break
        for f in fields:
            table.set(row, f, clamp(table.get(row, f) + delta))
    return len(fields)


# --- The full ratings (data pack part `ratings_full`, docs/notes/full-ratings.md) ------------------------------
def full_kind(goalie):
    return 'goalie' if goalie else 'skater'


def full_index(part):
    """the full ratings' players (the data pack part) ready for match_full: per kind ('skater', 'goalie') the players by normalised
    full name and by (last name, birthdate), the order of their values (`fields`), and the straight line that puts an
    overall onto the level scale (`scale`, see overall_level)."""
    out = {kind: {'name': {}, 'last': {}, 'fields': list(part['fields'][kind])} for kind in ('skater', 'goalie')}
    for p in part['players']:
        ix = out[full_kind(p['pos'] == 'G')]
        q = (norm(p['first']), tuple(p['birth']), p)
        ix['name'].setdefault((q[0], norm(p['last'])), []).append(q)
        ix['last'].setdefault((norm(p['last']), q[1]), []).append(q)
    for kind, ix in out.items():
        table = GOALIE_TABLE if kind == 'goalie' else SKATER_TABLE
        at = {n: k for k, n in enumerate(ix['fields'])}
        names = sorted({FIELDS[table][tag] for tag in (LIST_GOALIE if kind == 'goalie' else LIST_SKATER).values()} & set(at))
        pairs = [(p['v'][at['c_overall']], sum(p['v'][at[n]] for n in names) / len(names))
                 for qs in ix['name'].values() for _, _, p in qs] if names and 'c_overall' in at else []
        ix['scale'] = _line(sorted(pairs))      # (sorted: the same line whatever order the part lists players in)
    return out


def _line(pairs):
    """(a, b) of the least-squares line y = a + b x through `pairs` [(x, y)]; (0, 1) without enough of them."""
    if len(pairs) < 2:
        return 0.0, 1.0
    mx = sum(x for x, _ in pairs) / len(pairs)
    my = sum(y for _, y in pairs) / len(pairs)
    var = sum((x - mx) ** 2 for x, _ in pairs)
    if not var:
        return 0.0, 1.0
    b = sum((x - mx) * (y - my) for x, y in pairs) / var
    return my - b * mx, b


def overall_level(index, kind, overall):
    """the full ratings' overall on the level scale (the mean of a player's attributes, as `level`): the full ratings stretch their overall
    below the NHL (an NHL player's overall is about his level, an OHL player's about 13 lower), and every other player's
    quality is his level, so a team's line-up compares them on one scale. the full ratings' own players set the line."""
    a, b = index[kind]['scale']
    return a + b * overall


def match_full(index, first, last, birth, goalie, years=None, near_years=None):
    """The full ratings' player of a record (`first`, `last`, `birth` (y, m, d), goalie or skater), as (player, how) or None.
    In order: (1) the full name and the birthdate ('full'); (2) the last name and the birthdate with a first name that
    can be his (matching.same_first_name: Matt / Matthew; 'last+birth'); (3) the full name with a birth year within one
    ('name': the DEL gives only an age), the closest birthdate among namesakes. `years`: the birth years tried for (1)
    and (2), `near_years` for (3) (default: the record's; a record still in the game's year - 1900 also ten years earlier).
    Goalies only match goalies, skaters skaters."""
    ix = index[full_kind(goalie)]
    fn, ln = norm(first), norm(last)
    y, m, d = birth
    named = ix['name'].get((fn, ln), ())
    for yy in years or (y,):
        b = (yy, m, d)
        for f2, b2, p in named:
            if b2 == b:
                return p, 'full'
        for f2, b2, p in ix['last'].get((ln, b), ()):
            if same_first_name(f2, fn):
                return p, 'last+birth'
    for yy in near_years or (y,):
        near = [(abs((b2[0] - yy) * 372 + (b2[1] - m) * 31 + b2[2] - d), p) for f2, b2, p in named if abs(b2[0] - yy) <= 1]
        near.sort(key=lambda dp: dp[0])
        if len(near) == 1 or (len(near) > 1 and near[0][0] < near[1][0]):
            return near[0][1], 'name'
    return None


def full_values(index, kind, p):
    """{field name: raw value} of one player of the full ratings."""
    return dict(zip(index[kind]['fields'], p['v']))


def write_full(table, row, values, kind):
    """Write the full ratings (`values`: full_values) into one skater or goalie row: the 0-99 ratings (schema.FULL_RATED)
    as value - RATING_BASE, clamped 0-63; the small numbers (FULL_ASIS: fighting, consistency, paddle down, the three
    biases) as they are, within the range the game's players hold. The player type is the caller's (Builder.set_style,
    within the record's class); potential, growth and traits are left alone. Returns the number of fields written."""
    tags = FULL_TAG[kind]
    n = 0
    for name in FULL_RATED[kind]:
        if name in values:
            table.set(row, tags[name], clamp(values[name] - RATING_BASE))
            n += 1
    for name in FULL_ASIS[kind]:
        if name in values and name in ASIS_RANGE:
            lo, hi = ASIS_RANGE[name]
            table.set(row, tags[name], max(lo, min(hi, values[name])))
            n += 1
    return n


# The player type the game shows next to a player's rating (Edit Lines: PLY 90; Team Rosters: "STD • G • 85 Overall");
# table field `sFgQ`. Every number was put on a player of a lab roster and read in the game (2026-10-16,
# docs/notes/faces.md): defencemen 1-4 and forwards 5-10 do not share a number, goalies 0-2 do with defencemen.
# Create Player's "Player Type" names the forward types in full; the defence and goalie words are their letters'.
STYLES = {1: 'DFD', 2: 'OFD', 3: 'ENF', 4: 'TWD', 5: 'GRN', 6: 'PLY', 7: 'SNP', 8: 'PWF', 9: 'TWF', 10: 'ENF'}
GOALIE_STYLES = {0: 'STD', 1: 'HYB', 2: 'BUT'}
STYLE_WORDS = {'GRN': 'Grinder', 'PLY': 'Playmaker', 'SNP': 'Sniper', 'PWF': 'Power forward', 'TWF': 'Two-way',
               'ENF': 'Enforcer', 'DFD': 'Defensive', 'OFD': 'Offensive', 'TWD': 'Two-way', 'STD': 'Stand-up',
               'HYB': 'Hybrid', 'BUT': 'Butterfly'}


def style_name(number, goalie=False):
    """The type's letters as the game shows them (PLY, DFD, BUT ...) or None for a number no player holds."""
    return (GOALIE_STYLES if goalie else STYLES).get(number)


# The types each kind of player holds, on the community roster and on the disc's (docs/notes/faces.md): forwards
# 5-10, defencemen 1-4, goalies 0-2. A type outside his kind's is never written (verify.style_problems).
STYLE_CHOICES = {'F': (5, 6, 7, 8, 9, 10), 'D': (1, 2, 3, 4), 'G': (0, 1, 2)}


def style_class(pos):
    """'F', 'D' or 'G' for a position number (0 C, 1 LW, 2 RW, 3 D, 4 G)."""
    return 'G' if pos == 4 else 'D' if pos == 3 else 'F'


def style_label(number, goalie=False):
    """The type as the Roster editor's table names it: the game's letters, else its number."""
    return style_name(number, goalie) or f"Type {number}"


def style_choice(number, goalie=False):
    """The type as the card's list offers it: 'PLY · Playmaker'."""
    name = style_name(number, goalie)
    return f"{name} · {STYLE_WORDS[name]}" if name else f"Type {number}"
