"""A skater's equipment: the choices the Roster editor offers and how they are written (table `ajmx`,
exhibitionskaterequipment, one row per skater keyed by the player's game id).

    stick  tape  helmet  visor  gloves  skates  jersey_tuck  sock_tuck

The numbers are the game's own model ids: the same ids name the game's menu pictures (`art/equipment.py`).
The words of the tape colours, the tucks, the pads and the pants are the game's own menu words; the numbers behind
them are checked in the game (docs/notes/equipment.md).

A goalie's equipment is table `lVMf` (exhibitiongoalieequipment): stick, tape, jersey tuck, mask, pads, blocker, trapper,
neck guard. His mask can also wear the player's own picture: the goalie gets a mask number nobody uses and the picture
goes into that number's 3D texture (art/masks.py).
"""
import re

from .schema_names import FIELDS

TABLE = 'ajmx'
CODE = {name: tag for tag, name in FIELDS[TABLE].items()}

# choice -> (field name in the table, what the choice is called for players)
CHOICES = {
    'stick': ('stick', 'Stick'),
    'tape': ('sticktapecolor', 'Tape'),
    'helmet': ('helmetbrand', 'Helmet'),
    'visor': ('visortype', 'Visor'),
    'gloves': ('gloves', 'Gloves'),
    'skates': ('skatebrand', 'Skates'),
    'jersey_tuck': ('jerseytuck', 'Jersey tuck'),
    'sock_tuck': ('skatesocktuck', 'Sock tuck'),
    'visor_tint': ('visorcolor', 'Visor tint'),
    'shoulder_pads': ('shoulderpads', 'Shoulder pads'),
    'pant_length': ('pantstypecode', 'Pant length'),
}
GOALIE_TABLE = 'lVMf'
GOALIE_CODE = {name: tag for tag, name in FIELDS[GOALIE_TABLE].items()}
GOALIE_CHOICES = {
    'stick': ('stick', 'Stick'),
    'tape': ('sticktapecolor', 'Tape'),
    'jersey_tuck': ('jerseytuck', 'Jersey tuck'),
    'mask': ('maskid', 'Mask'),
    'pads': ('pads', 'Pads'),
    'blocker': ('blocker', 'Blocker'),
    'trapper': ('trapper', 'Trapper'),
    'neck': ('neckprotector', 'Neck guard'),
}
MASK_TYPE = 'masktype'
KINDS = {'skater': (TABLE, CODE, CHOICES), 'goalie': (GOALIE_TABLE, GOALIE_CODE, GOALIE_CHOICES)}
# the choices that are the same for a whole team's look (the editor offers "same for the whole team")
TEAM_WIDE = ('tape', 'helmet', 'visor', 'visor_tint', 'jersey_tuck', 'sock_tuck', 'shoulder_pads', 'pant_length')
# what a new player gets: Edit Pro's plain choices (a straight visor, small shoulder pads, short pants, socks tucked in
# (Full), no jersey tuck, white tape). The words of every number: docs/notes/equipment-labels.md (lab round 51)
NEW_PLAYER = {'visor': 0, 'visor_tint': 0, 'shoulder_pads': 0, 'pant_length': 0, 'jersey_tuck': 0, 'sock_tuck': 0, 'tape': 1}

# Real equipment (data pack part `equipment`, Builder.real_equipment): the part's raw number -> this game's number, per
# choice. Only what the lab named (docs/notes/equipment-labels.md); the part's model numbers are never used (the numbering
# differs). A choice with no table here is not written.
REAL = {
    'sock_tuck': {0: 0, 1: 1, 2: 2, 3: 3},
    'pant_length': {0: 0, 1: 1},
    'neck': {0: 0, 1: 1},
    'tape': {'black': 0, 'white': 1},
}


def real_values(entry, goalie=False):
    """{choice: this game's number} for one entry of the data pack's `equipment` part: a skater's sock tuck, pant length and tape,
    a goalie's neck guard and tape. A number the part leaves out is at the default (0); an unknown tape class
    (neither black nor white) is left alone."""
    out = {}
    if goalie:
        out['neck'] = REAL['neck'].get(entry.get('neck', 0))
    else:
        out['sock_tuck'] = REAL['sock_tuck'].get(entry.get('sock', 0))
        out['pant_length'] = REAL['pant_length'].get(entry.get('pants', 0))
    if entry.get('tape') in REAL['tape']:
        out['tape'] = REAL['tape'][entry['tape']]
    return {c: n for c, n in out.items() if n is not None}


def tag(choice, kind='skater'):
    _t, code, choices = KINDS[kind]
    return code[choices[choice][0]]


def largest(table, choice, kind='skater'):
    """The biggest number the game's table can hold for a choice."""
    return table.field(tag(choice, kind)).mask


def row_of(table, kind='skater'):
    """game id -> row of the equipment table."""
    code = KINDS[kind][1]
    return {table.get(i, code['game_id']): i for i in range(table.cur_rec)}


def read(table, row, kind='skater'):
    """{choice: number} of one row."""
    return {c: table.get(row, tag(c, kind)) for c in KINDS[kind][2]}


def clean(values, table=None, kind='skater'):
    """(the choices that can be written, problems): whole numbers the table's fields can hold."""
    ok, problems = {}, []
    choices = KINDS[kind][2]
    for choice, v in (values or {}).items():
        if choice not in choices:
            problems.append(f"unknown equipment choice {choice}")
            continue
        try:
            n = int(v)
        except (TypeError, ValueError):
            problems.append(f"{choices[choice][1]}: {v!r} is not a number")
            continue
        if n < 0 or (table is not None and n > largest(table, choice, kind)):
            problems.append(f"{choices[choice][1]}: {n} is outside what the game can hold")
            continue
        ok[choice] = n
    return ok, problems


def write(table, row, values, kind='skater'):
    """Write the (cleaned) choices to a row; returns how many values changed."""
    changed = 0
    for choice, n in values.items():
        if table.get(row, tag(choice, kind)) != n:
            table.set(row, tag(choice, kind), n)
            changed += 1
    return changed


# --- what the window shows ----------------------------------------------------------------------------------------
# The choices with a menu picture on the game's disc (cache.big): choice -> (folder, file prefix, shift of the id).
# The pictures of the visor types are not in order: VISOR_FILE.
MENU = {'stick': ('sticks', 'stick', 0), 'helmet': ('helmet', 'helmet', 0), 'gloves': ('gloves', 'gloves', 0),
        'skates': ('skates', 'skate', 0), 'visor': ('visor', 'visor', 0)}
# visor type -> number of its picture file: visor2.big shows the straight visor, visor3.big the curved one, visor1.big
# is the "none" sign (lab round 51)
VISOR_FILE = {0: 2, 1: 3, 2: 1}
MENU_ROOT = 'fe/ion/artassets/createplayer'


GOALIE_MENU = {'stick': ('goaliestick', 'goaliestick', 0), 'mask': ('mask', 'mask', 0), 'pads': ('pads', 'pads', 0),
               'blocker': ('blocker', 'blocker', 0), 'trapper': ('trapper', 'trapper', 0)}


def menu_path(choice, number, kind='skater'):
    folder, prefix, shift = (GOALIE_MENU if kind == 'goalie' else MENU)[choice]
    if choice == 'visor' and kind == 'skater':
        number = VISOR_FILE[number]
    return f"{MENU_ROOT}/{folder}/{prefix}{number + shift}.big"


# The choices without a picture. The words are the game's own, from Edit Player > Customization, read in the lab (round 51,
# docs/notes/equipment-labels.md): the sock tuck is 0 Full (the sock goes into the skate), 1 None, 2 Front, 3 Back; the
# visor is 0 Straight, 1 Curved, 2 None, and its tint has no meaning without a visor.
TAPE_COLOURS = ["Black", "White", "Blue", "Red", "Yellow", "Green", "Orange", "Light Blue", "Pink", "Purple"]
TINTS = ["Clear", "Grey", "Yellow", "Orange", "Green", "Light Blue", "Blue", "Red"]
OPTIONS = {
    'tape': list(enumerate(TAPE_COLOURS)),
    'jersey_tuck': [(0, "None"), (1, "Left"), (2, "Right"), (3, "Full")],
    'sock_tuck': [(0, "Full"), (1, "None"), (2, "Front"), (3, "Back")],
    'visor': [(0, "Straight visor"), (1, "Curved visor"), (2, "No visor")],
    'visor_tint': list(enumerate(TINTS)),
    'shoulder_pads': [(0, "Small"), (1, "Big")],
    'pant_length': [(0, "Short"), (1, "Long")],
}

GOALIE_OPTIONS = {
    'tape': OPTIONS['tape'],
    'jersey_tuck': OPTIONS['jersey_tuck'],
    'neck': [(0, "Off"), (1, "On")],
}

# Mask numbers (masktype 0) with a 3D texture file on the game disc: 0-291 except these (EU disc)
MASK_FILES_MISSING = frozenset(range(234, 246))
MASK_LARGEST = 291


def free_mask_ids(table, taken=()):
    """Mask numbers (type 0) no goalie of the roster wears and the disc has a texture for, highest first."""
    used = {table.get(i, GOALIE_CODE['maskid']) for i in range(table.cur_rec)
            if table.get(i, GOALIE_CODE[MASK_TYPE]) == 0} | set(taken)
    return [n for n in range(MASK_LARGEST, 0, -1) if n not in used and n not in MASK_FILES_MISSING]


# --- which models the game can draw -------------------------------------------------------------------------------
# The game's table holds model numbers of older NHL games too (skates up to 109, sticks, gloves ...). NHL Legacy has
# the 3D picture (texture) of only some of them; a model without one is drawn plain blue. The textures sit in the
# disc's cacherender.big: choice -> (folder, the file name's pattern with the model number as group 1).
RENDERING = {
    'skater': {
        'stick': ('playerstick', r'texlib_(\d+)\.'),
        'gloves': ('glove', r'feglove_(\d+)_'),
        'skates': ('skate', r'texlib_(\d+)\.'),
        'helmet': ('helmet', r'(?:helmet|chinstrap|jawprotector|padding|texlib)_(?:0_)?(\d+)[_.]'),
    },
    'goalie': {
        'stick': ('goaliestick', r'goaliestick_(\d+)_'),
        'pads': ('goaliepad', r'fegoaliepad_(\d+)_'),
        'blocker': ('blocker', r'blocker_0_(\d+)_'),
        'trapper': ('trapper', r'fetrapper_0_(\d+)_'),
        'mask': ('goaliehelmet', r'goaliehelmet_0_(\d+)_cm\.'),
    },
}


def available(names, kind='skater'):
    """{choice: set of model numbers the game can draw} from the file names inside cacherender.big. Choices
    that are not models (tape, tucks, visor ...) are not in it: every number of theirs works."""
    out = {}
    for choice, (folder, pattern) in RENDERING[kind].items():
        rx = re.compile(pattern)
        prefix = f"rendering/{folder}/"
        out[choice] = {int(m.group(1)) for n in names if n.startswith(prefix)
                       for m in [rx.match(n[len(prefix):])] if m}
    return out


def _ranges(*pairs):
    return frozenset(n for a, b in pairs for n in range(a, b + 1))


# What available() gives on the EU and the NA disc (the same on both, measured 2026-10-18). The community roster gives
# 44 goalies pads, blockers or gloves 85-88 (newer models): the game draws them plain blue (Gibson's blocker, lab rounds
# 33 / 34). Sticks: sticks.DRAWABLE; masks can wear a picture of the player's own (art/masks.py), so they are not here.
DRAWABLE = {
    'skater': {
        'gloves': _ranges((15, 15), (18, 18), (20, 21), (23, 25), (27, 30), (33, 33), (38, 46), (48, 49), (51, 59),
                          (61, 62), (65, 77), (80, 83), (100, 101)),
        'skates': _ranges((7, 8), (15, 17), (23, 24), (26, 26), (28, 28), (30, 32), (35, 48), (70, 75)),
        'helmet': _ranges((1, 1), (6, 8), (11, 21), (23, 25), (110, 110)),
    },
    'goalie': {
        'stick': _ranges((6, 43)),
        'pads': _ranges((1, 1), (11, 12), (14, 15), (17, 36), (38, 40), (42, 46), (48, 51), (53, 56), (58, 72), (74, 84)),
        'blocker': _ranges((1, 1), (11, 12), (14, 15), (17, 36), (38, 40), (42, 46), (48, 56), (58, 72), (74, 84)),
        'trapper': _ranges((1, 1), (11, 12), (14, 15), (17, 36), (38, 40), (42, 45), (48, 51), (53, 56), (58, 72),
                           (74, 84)),
    },
}
GOALIE_SET = ('pads', 'blocker', 'trapper')     # one model number usually names the goalie's whole set


def drawable(kind, choice, n, mates=()):
    """A model the game can draw for `n`: n itself, else the first of `mates` (the goalie's other parts) it can draw,
    else the closest lower number it can draw, else its lowest."""
    ok = DRAWABLE[kind][choice]
    if n in ok:
        return n
    for m in mates:
        if m in ok:
            return m
    lower = [m for m in ok if m < n]
    return max(lower) if lower else min(ok)


def _model_tables(R):
    """(kind, table, its game-id field) of every table that names models: skaters (ajmx), goalies (lVMf) and the
    goalies' team gear (nAUy)."""
    return [('skater', R.f[TABLE], 'game_id'), ('goalie', R.f[GOALIE_TABLE], 'game_id'), ('goalie', R.f['nAUy'], 'game_id')]


def _field(kind, choice):
    return (CHOICES if kind == 'skater' else GOALIE_CHOICES)[choice][0]


def fix_models(R):
    """Every model the game cannot draw (DRAWABLE) becomes one it can (`drawable`). Returns [(kind, game id, choice,
    old, new)]; a second run changes nothing."""
    out = []
    for kind, t, gid in _model_tables(R):
        for row in range(t.cur_rec):
            now = {c: t.get(row, _field(kind, c)) for c in DRAWABLE[kind]}
            for choice, n in now.items():
                mates = [now[c] for c in GOALIE_SET if c != choice] if choice in GOALIE_SET else ()
                new = drawable(kind, choice, n, mates)
                if new != n:
                    t.set(row, _field(kind, choice), new)
                    out.append((kind, t.get(row, gid), choice, n, new))
    return out


def model_problems(R, also=None):
    """Models the game cannot draw (it draws them plain blue): one line per model. `also`: {(kind, choice): models} to
    accept anyway (`worn(source)`: what the roster carried before)."""
    count = {}
    for kind, t, _gid in _model_tables(R):
        for choice, ok in DRAWABLE[kind].items():
            accept = (also or {}).get((kind, choice), ())
            for row in range(t.cur_rec):
                n = t.get(row, _field(kind, choice))
                if n not in ok and n not in accept:
                    count[(kind, choice, n)] = count.get((kind, choice, n), 0) + 1
    return [f"{c} {'goalie' if kind == 'goalie' else 'player'} row(s) have {CHOICES.get(choice, GOALIE_CHOICES.get(choice))[1].lower()} "
            f"model {n}, which the game cannot draw" for (kind, choice, n), c in sorted(count.items())]


def worn(R):
    """{(kind, choice): models} the roster's rows carry."""
    out = {}
    for kind, t, _gid in _model_tables(R):
        for choice in DRAWABLE[kind]:
            out.setdefault((kind, choice), set()).update(t.get(row, _field(kind, choice)) for row in range(t.cur_rec))
    return out
