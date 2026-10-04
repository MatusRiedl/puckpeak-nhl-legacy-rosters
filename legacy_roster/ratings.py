"""Write EA NHL ratings into the save's skater / goalie attribute tables.

The field for every attribute is known exactly from the game's schema (see schema.py); the
stored value is the rating minus 36 (6 bits: ratings 36..99).
"""
from . import matching
from .schema import EA_GOALIE, EA_SKATER, RATING_BASE

SKATER_TABLE, GOALIE_TABLE = 'yvSd', 'yuHm'


def is_goalie(p):
    return (p.get('position') or '').startswith('G')


def match_players(R, players):
    """[(rated player, cPbu row)] matched by last name + birthdate (or full name)."""
    lst = []
    for p in players:
        if not p.get('birth'):
            continue
        first, _, last = p['name'].partition(' ')
        lst.append({'first': first, 'last': last, 'birth': tuple(p['birth']), 'src': p})
    matching.match(R, lst)
    return [(q['src'], q['row']) for q in lst if q['row'] is not None]


def clamp(v):
    return max(0, min(63, v))


def attribute_fields(table):
    """The attribute fields (c_*) of a rating table that EA publishes ratings for."""
    amap = EA_GOALIE if table.name == GOALIE_TABLE else EA_SKATER
    return sorted(set(amap.values()))


def level(table, row, fields=None):
    """A player's level on the rating scale: mean of his attributes (stored value + 36)."""
    fields = fields or attribute_fields(table)
    return sum(table.get(row, f) for f in fields) / len(fields) + RATING_BASE


def overall_offset(players):
    """Median of (EA overall - mean attribute rating), per position group, from fully rated players.

    Lets a player who only has an overall be placed at the right level."""
    out = {}
    for goalie, amap in ((False, EA_SKATER), (True, EA_GOALIE)):
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
    but an overall has all his attributes shifted so his level matches that overall. Fields EA
    does not publish (potential, traits, growth) are left alone."""
    amap = EA_GOALIE if table.name == GOALIE_TABLE else EA_SKATER
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
