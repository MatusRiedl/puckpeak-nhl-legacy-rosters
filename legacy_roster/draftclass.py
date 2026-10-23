"""Draft classes: made-up prospects for the drafts of a new Be a GM / Season (the "Draft & Pro" tab).

A class player is an ordinary new player of edits.json (edits.py: "new": true and a "team") with a prospect block:

    "prospect": {"class": 2027,       the draft he is eligible for: eligible_year(his birth date)
                 "tier": 3,           growth tier 1-7, 1 the best
                 "potential": 50}     inside the tier's band (TIER_BANDS); missing: the band's top

What the game does with them (lab round 44, docs/notes/lab-round-44.md and draft-class.md): a new career imports as
prospects the players without NHL rights of the CHL clubs and the European clubs (DRAFT_SLOTS; prospect pools sit in
European slots) and gives each the draft year of his birth date; the NHL, the AHL and the free-agent list are no draft
source, and the roster's draft fields do not matter. Players over 20 are dropped from the pool. The potential is fitted into the band of
the growth tier when the career starts, so the tab offers a tier and a value inside its band. A career counts years from
the patched game's year: a class plays its part only on a roster for the patched game.

In pipeline.build: edits.records_needed holds records for new players before the leagues use them all, edits.apply
makes and places class players like any new player, apply() writes their potential and draft fields after the last
draft.apply, and verify checks them with problems().

A class can be shared as a class file (class_file / read_class: JSON, the players as the editor's card has them, their
prospect block and club by league and name; no pictures) and made at random (make: names mixed from real players of the
same country, never a real player's full name, each with a created look (faces.random_look) that puts him on one of the
game's Create Player records while they last, so a class fits a roster whose leagues used every other record; the same
inputs always make the same class).
"""
import datetime
import json
import random
import unicodedata

from . import faces, layout as L

# the team slots a new career takes prospects from: the European clubs (62-132, also the prospect pools there) and the
# CHL (154-213); the program's career set-up imports exactly these (EBOOT 0x2850c8 and 0x27c5f4, lab round 44)
DRAFT_SLOTS = frozenset(L.EUROPE | L.CHL)
# growth tier -> (lowest, highest) potential a new career keeps (every player born 2004 or later, lab round 44)
TIER_BANDS = {1: (59, 59), 2: (53, 56), 3: (48, 50), 4: (44, 49), 5: (41, 43), 6: (35, 42), 7: (30, 35)}
# the growth letter most players of a tier have in a new career (its meaning is not known)
GROWTH_LETTER = {1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 3, 7: 3}
CLASSES_AHEAD = 4               # the next four drafts
UNDRAFTED_FIELDS = ('WzKY', 'Ujcc', 'WfTt', 'uWgv')     # draft year - 1900, round, overall, team + 1 (draft.FIELDS)


def eligible_year(birth):
    """The first draft a player born on `birth` (year, month, day) may be picked in: he is 18 by 15 September."""
    y, m, d = birth
    return y + 18 + (1 if (m, d) > (9, 15) else 0)


def class_years(season_year):
    """The drafts a class can be made for, in the season `season_year`-(`season_year` + 1): the next four."""
    return range(season_year + 1, season_year + 1 + CLASSES_AHEAD)


def prospects_of(edits):
    """{person key: edit} of the class players among the player's edits."""
    return {who: e for who, e in (edits or {}).items() if isinstance(e.get('prospect'), dict)}


def stars(tier):
    """Growth tier `tier` as the game's Potential Range in stars ('5', '4½' ... '2'): Create Player sets the tier to
    9 - 2 x (stars - 1) (lab D)."""
    n = 11 - tier
    return f"{n // 2}{'½' if n % 2 else ''}"


def fitted(block):
    """(growth tier, potential) of a prospect block, fitted into the game's bands as a new career fits them."""
    try:
        tier = min(max(int(block.get('tier') or 3), 1), max(TIER_BANDS))
    except (TypeError, ValueError):
        tier = 3
    lo, hi = TIER_BANDS[tier]
    try:
        potential = hi if block.get('potential') is None else min(max(int(block['potential']), lo), hi)
    except (TypeError, ValueError):
        potential = hi
    return tier, potential


def is_draft_club(team):
    """Whether a new career drafts the players of team slot `team` (a European or CHL club)."""
    return team in DRAFT_SLOTS


def ai_rows(R):
    """{player id: (table name, row)} of the players' attributes (yvSd skaters, yuHm goalies)."""
    out = {}
    for tname in ('yvSd', 'yuHm'):
        table = R.f[tname]
        for row in range(table.cur_rec):
            out.setdefault(table.get(row, 'zIBw'), (tname, row))
    return out


def birth_of(P, prow, base=1910):
    """(year, month, day) of a player record; `base` 1911 on a patch roster (gamepatch.year_shift)."""
    return P.get(prow, 'dnFq') + base, P.get(prow, 'pLKJ') + 1, P.get(prow, 'iwsK') + 1


def apply(b, edits, say=None):
    """Write the class players' potential, growth and draft fields (after the last draft.apply). Returns {'season': the
    season's first year, 'players': {player id: (label, draft year, tier, potential)}} for verify, or None without class
    players. A class player who is not on a draft club, or whose birth date does not fit his class, is left as he is and
    named in the report."""
    from .edits import _teams_of, people
    say = say or (lambda msg: None)
    mine = prospects_of(edits)
    if not mine:
        return None
    R, P = b.R, b.P
    found = people(b)
    season = b.data.season_year
    rows = ai_rows(R)
    placed = {}
    for who in sorted(mine):
        e = mine[who]
        label = e.get('label') or who
        prow = found.get(who)
        if prow is None:
            continue                        # edits.apply named him in the report already
        birth = birth_of(P, prow)
        year = eligible_year(birth)
        clubs = [t for t in _teams_of(b, prow) if t not in L.NATIONAL]      # the builder's live places
        pid = P.get(prow, 'zIBw')
        why = None
        if year not in class_years(season):
            why = f"born {birth[0]}: not eligible for the drafts {season + 1}-{season + CLASSES_AHEAD}"
        elif e['prospect'].get('class') not in (None, year):
            why = f"his birth date makes him eligible in {year}, not {e['prospect']['class']}"
        elif not clubs or not all(is_draft_club(t) for t in clubs):
            why = "not on a junior or European club (the game drafts only from those)"
        elif pid not in rows:
            why = "his record has no ratings row"
        if why:
            b.log.append(['edits', 'class player left out', label, why, ''])
            continue
        tier, potential = fitted(e['prospect'])
        tname, row = rows[pid]
        table = R.f[tname]
        table.set(row, 'koEt', potential)
        table.set(row, 'AMoQ', tier)
        table.set(row, 'feBm', GROWTH_LETTER[tier])
        for f, v in zip(UNDRAFTED_FIELDS, (year - 1900, 0, 0, 0)):
            P.set(prow, f, v)
        placed[pid] = (label, year, tier, potential)
    if not placed:
        return None
    b.log.append(['ALL', 'summary', 'draft class players', len(placed), ''])
    say(f"Draft classes: {len(placed)} player" + ("s" if len(placed) != 1 else ""))
    return {'season': season, 'players': placed}


def problems(R, prospects, base=1910):
    """What is wrong with the class players `prospects` (apply's result) in the built roster `R` (texts; empty when
    right). `base`: 1911 on a patch roster."""
    if not prospects:
        return []
    out = []
    P, season = R.P, prospects['season']
    rows = ai_rows(R)
    for pid, (label, year, tier, potential) in sorted(prospects['players'].items()):
        prow = R.p_by_id.get(pid)
        if prow is None:
            out.append(f"draft class: {label} is missing")
            continue
        if eligible_year(birth_of(P, prow, base)) != year or year not in class_years(season):
            out.append(f"draft class: {label} is not eligible for the {year} draft")
        if tuple(P.get(prow, f) for f in UNDRAFTED_FIELDS) != (year - 1900, 0, 0, 0):
            out.append(f"draft class: {label} has a draft")
        clubs = [t for _, t in R.teams_of(prow) if t not in L.NATIONAL]
        if not clubs or not all(is_draft_club(t) for t in clubs):
            out.append(f"draft class: {label} is not on a junior or European club")
        lo, hi = TIER_BANDS.get(tier, (1, 0))
        found = rows.get(pid)
        if found is None or not lo <= potential <= hi:
            out.append(f"draft class: {label} has a potential outside growth tier {tier}")
        elif (R.f[found[0]].get(found[1], 'koEt'), R.f[found[0]].get(found[1], 'AMoQ')) != (potential, tier):
            out.append(f"draft class: {label} lost his potential")
    return out


# --- class files ------------------------------------------------------------------------------------------------------
FILE_FORMAT, FILE_VERSION = 'legacy-roster-draft-class', 1
# what a class file keeps of a player: the card's values as typed (texts; height in cm, weight in kg), his ratings
# and his created look (faces.LOOK numbers) when he has one
CARD_FIELDS = ('first', 'last', 'num', 'pos', 'shoots', 'birth', 'country', 'height', 'weight', 'ovr', 'style', 'head',
               'skin', 'eyes')
MAX_FILE_PLAYERS = 400


def class_file(name, year, players):
    """The text of a class file. `players`: [{'card': {CARD_FIELDS..., 'ratings': {label: text}, 'look': {...}}, 'prospect':
    {'tier', 'potential'}, 'club': {'league', 'name'} or None}]."""
    out = {'format': FILE_FORMAT, 'version': FILE_VERSION, 'name': str(name or f"{year} draft class"), 'year': int(year),
           'players': []}
    for pl in players:
        card = {k: str(v) for k, v in (pl.get('card') or {}).items() if k in CARD_FIELDS and v not in (None, '')}
        rated = {str(a): str(v) for a, v in ((pl.get('card') or {}).get('ratings') or {}).items() if str(v).strip()}
        look = (pl.get('card') or {}).get('look')
        if isinstance(look, dict):
            card['look'] = faces.clean_look(look)[0]
        tier, potential = fitted(pl.get('prospect') or {})
        out['players'].append({'card': dict(card, **({'ratings': rated} if rated else {})),
                               'prospect': {'tier': tier, 'potential': potential},
                               'club': pl.get('club') or None})
    return json.dumps(out, ensure_ascii=False, indent=1) + '\n'


def read_class(text):
    """(name, year, players) of a class file's text, players as class_file takes them. ValueError with a plain
    sentence when it is not one."""
    try:
        doc = json.loads(text)
    except ValueError:
        raise ValueError("This is not a draft class file.") from None
    if not isinstance(doc, dict) or doc.get('format') != FILE_FORMAT:
        raise ValueError("This is not a draft class file.")
    if not isinstance(doc.get('version'), int) or doc['version'] > FILE_VERSION:
        raise ValueError("This class file is from a newer version of the program: update the program first.")
    try:
        year = int(doc.get('year'))
    except (TypeError, ValueError):
        raise ValueError("The class file does not say which draft it is for.") from None
    players = doc.get('players')
    if not isinstance(players, list) or not players:
        raise ValueError("The class file has no players.")
    if len(players) > MAX_FILE_PLAYERS:
        raise ValueError(f"The class file has {len(players)} players; at most {MAX_FILE_PLAYERS} fit.")
    out = []
    for pl in players:
        if not isinstance(pl, dict) or not isinstance(pl.get('card'), dict):
            raise ValueError("The class file is damaged (a player without his card).")
        card = {k: str(v) for k, v in pl['card'].items() if k in CARD_FIELDS}
        rated = pl['card'].get('ratings')
        card['ratings'] = {str(a): str(v) for a, v in rated.items()} if isinstance(rated, dict) else {}
        if isinstance(pl['card'].get('look'), dict):       # a look the game does not offer is left out, not the player
            look, wrong = faces.clean_look(pl['card']['look'])
            if not wrong:
                card['look'] = look
        club = pl.get('club') if isinstance(pl.get('club'), dict) else None
        block = pl.get('prospect') if isinstance(pl.get('prospect'), dict) else {}
        out.append({'card': card, 'prospect': dict(zip(('tier', 'potential'), fitted(block))),
                    'club': {'league': str(club.get('league') or ''), 'name': str(club.get('name') or '')} if club else None})
    return str(doc.get('name') or f"{year} draft class"), year, out


def shift_birth(text, years):
    """A card's birth date ('YYYY-MM-DD') `years` later (29 February becomes the 28th); the text as it is when it is no
    date."""
    try:
        y, m, d = (int(x) for x in str(text).split('-'))
        if (m, d) == (2, 29):
            d = 28
        return datetime.date(y + years, m, d).isoformat()
    except ValueError:
        return text


# --- the random class maker ---------------------------------------------------------------------------------------------
# where made-up prospects come from (about the share of recent drafts) and the league a country's player plays in;
# the others play in the CHL
COUNTRY_MIX = (('CAN', 34), ('USA', 24), ('SWE', 11), ('FIN', 7), ('RUS', 7), ('CZE', 5), ('SVK', 3), ('CHE', 3),
               ('DEU', 3), ('LVA', 1), ('NOR', 1), ('DNK', 1))
HOME_LEAGUE = {'SWE': 'SHL', 'FIN': 'Liiga', 'CZE': 'Extraliga', 'CHE': 'NL', 'DEU': 'DEL', 'NOR': 'Norway'}
POSITION_MIX = (('C', 25), ('LW', 15), ('RW', 15), ('D', 33), ('G', 12))
# growth tier shares (tiers 1-7, per cent) by the class's strength; the best-ranked players get the best tiers
STRENGTHS = {'weak': (1, 5, 15, 24, 28, 19, 8), 'normal': (2, 8, 20, 25, 25, 15, 5), 'strong': (4, 12, 24, 25, 20, 11, 4)}
# (height cm, weight kg) of an average prospect by position
BUILD = {'C': (183, 84), 'LW': (183, 84), 'RW': (183, 84), 'D': (187, 88), 'G': (188, 85)}
MIN_NAMES = 6                   # a country needs this many real players to mix names from (else Canada's)


def plain(text):
    return unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().lower().strip()


def birth_window(year):
    """(first, last) birth date of the players eligible for draft `year` (eligible_year)."""
    return datetime.date(year - 19, 9, 16), datetime.date(year - 18, 9, 15)


def _pick(rng, mix):
    total = sum(w for _, w in mix)
    at = rng.uniform(0, total)
    for value, weight in mix:
        at -= weight
        if at <= 0:
            return value
    return mix[-1][0]


def tiers_for(count, strength):
    """Growth tiers for `count` players ranked best first."""
    shares = STRENGTHS.get(strength, STRENGTHS['normal'])
    out, total = [], sum(shares)
    for tier in range(1, len(shares) + 1):
        out += [tier] * max(0, round(count * sum(shares[:tier]) / total) - len(out))
    return (out + [len(shares)] * count)[:count]


def make(year, count, names, clubs, seed=0, strength='normal', taken=()):
    """A random class for draft `year`: [{'card': card values as typed, 'prospect': {'tier', 'potential'}, 'club': slot}],
    best first. `names`: [(first, last, country)] of real players (the roster's); `clubs`: {league: [club slots]}
    (leagues 'CHL', 'SHL', 'Liiga', 'Extraliga', 'NL', 'DEL', 'Norway'; prospect pools left out by the caller);
    `taken`: full names never to make (the roster's are never made either). Players spread evenly over the clubs of
    their league; each card has a random created look (the caller drops those the roster has no record for). The same
    inputs make the same class."""
    rng = random.Random(f"draftclass|{year}|{count}|{strength}|{seed}")
    looks = random.Random(f"draftclass-look|{year}|{count}|{strength}|{seed}")     # its own: the names stay as before
    by_country = {}
    for first, last, country in sorted(set(names)):
        if first and last and not any(ch.isdigit() for ch in first + last):
            firsts, lasts = by_country.setdefault(country, ([], []))
            firsts.append(first)
            lasts.append(last)
    used = {plain(f"{f} {l}") for f, l, _ in names} | {plain(t) for t in taken}
    first_day, last_day = birth_window(year)
    days = (last_day - first_day).days
    out, added = [], {}
    for tier in tiers_for(count, strength):
        country = _pick(rng, COUNTRY_MIX)
        if len(by_country.get(country, ((), ()))[0]) < MIN_NAMES:
            country = 'CAN'
        firsts, lasts = by_country.get(country) or ([], [])
        if not firsts:
            raise ValueError("The roster has too few players to take names from.")
        for _ in range(200):
            first, last = rng.choice(firsts), rng.choice(lasts)
            if plain(f"{first} {last}") not in used:
                break
        else:
            continue
        used.add(plain(f"{first} {last}"))
        home = clubs.get(HOME_LEAGUE.get(country, 'CHL')) or clubs.get('CHL') or []
        if not home:
            raise ValueError("The roster has no junior or European club to put the class on.")
        pos = _pick(rng, POSITION_MIX)
        lo, hi = TIER_BANDS[tier]
        potential = rng.randint(lo, hi)
        ovr = max(42, min(70, round(40 + (potential - 30) * 0.8) + rng.randint(-3, 3)))
        height, weight = BUILD[pos]
        cm = max(170, min(203, round(rng.gauss(height, 5))))
        kg = max(66, min(110, round(weight + (cm - height) * 0.9 + rng.gauss(0, 4))))
        born = first_day + datetime.timedelta(days=rng.randint(0, days))
        out.append({'card': {'first': first, 'last': last, 'pos': pos, 'shoots': 'L' if rng.random() < 0.62 else 'R',
                             'birth': born.isoformat(), 'country': country, 'height': str(cm), 'weight': str(kg),
                             'ovr': str(ovr), 'ratings': {}, 'look': faces.random_look(looks)},
                    'prospect': {'tier': tier, 'potential': potential},
                    'club': spread(rng, home, added)})
    return out


def spread(rng, clubs, added):
    """A club for the next made player: one of those with the fewest made so far."""
    least = min(added.get(c, 0) for c in clubs)
    club = rng.choice(sorted(c for c in clubs if added.get(c, 0) == least))
    added[club] = added.get(club, 0) + 1
    return club
