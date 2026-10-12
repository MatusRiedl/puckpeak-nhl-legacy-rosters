"""A skater's equipment: the choices the Roster editor offers and how they are written (table `ajmx`,
exhibitionskaterequipment, one row per skater keyed by the player's game id).

    stick  tape  helmet  visor  gloves  skates  jersey_tuck  sock_tuck

The numbers are the game's own model ids: the same ids name the game's menu pictures (`art/equipment.py`).
Tape is 0 / 1 (black / white, to be confirmed in the game); the tucks' meaning is learned in the game
(docs/notes/equipment.md).

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
TEAM_WIDE = ('tape', 'helmet', 'visor', 'jersey_tuck', 'sock_tuck')


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
# The picture of visor type 1 is visor2.big (visor1.big is the "none" sign).
MENU = {'stick': ('sticks', 'stick', 0), 'helmet': ('helmet', 'helmet', 0), 'gloves': ('gloves', 'gloves', 0),
        'skates': ('skates', 'skate', 0), 'visor': ('visor', 'visor', 1)}
MENU_ROOT = 'fe/ion/artassets/createplayer'


GOALIE_MENU = {'stick': ('goaliestick', 'goaliestick', 0), 'mask': ('mask', 'mask', 0), 'pads': ('pads', 'pads', 0),
               'blocker': ('blocker', 'blocker', 0), 'trapper': ('trapper', 'trapper', 0)}


def menu_path(choice, number, kind='skater'):
    folder, prefix, shift = (GOALIE_MENU if kind == 'goalie' else MENU)[choice]
    return f"{MENU_ROOT}/{folder}/{prefix}{number + shift}.big"


# The choices without a picture. The words are the game's own (Create a Player: Stick Tape black / white,
# Jersey Tuck front / back, Sock Tuck none / short / long / full); which number is which is a guess from them
# and from the roster (the owner confirms it in the game, docs/notes/equipment.md).
OPTIONS = {
    'tape': [(0, "Black"), (1, "White")],
    'jersey_tuck': [(0, "Front"), (1, "Back")],
    'sock_tuck': [(0, "None"), (1, "Short"), (2, "Long"), (3, "Full")],
    'visor': [(0, "No visor"), (1, "Clear visor"), (2, "Tinted visor")],
}

GOALIE_OPTIONS = {
    'tape': OPTIONS['tape'],
    'jersey_tuck': OPTIONS['jersey_tuck'],
    'neck': [(0, "No neck guard"), (1, "Neck guard")],
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
