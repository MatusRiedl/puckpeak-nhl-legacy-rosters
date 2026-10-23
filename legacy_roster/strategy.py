"""A team's strategies: table `oYeE` (exhibitionteamstrategies), one row per team slot (key `index`).

The fields are the game's "Build Your AI" choices (docs/notes/strategies.md): the team's forecheck, pressure and
special-team plays (3-bit numbers, one per menu entry) and sliders between two words for the team, each forward line and
each defence pair (5-bit numbers, 5 in the middle). The Roster editor keeps the player's choices in edits.json
(`teams[slot]["strategy"] = {field: value}`), applied after every update (edits.apply_teams); verify.py refuses a value
outside the field's range.

The game's own menu (Season Mode Central > COACHING OPTIONS > STRATEGY, lab round 28, 2026-10-16) shows every choice
and slider below in the order of SECTIONS, with the words of CHOICES for values 0, 1, 2 ... (right on a choice adds 1 and
wraps round; a slider stops at its end). Read for Vegas and for a LAB Anaheim with a distinct value in each field
(docs/notes/strategies.md). 25 5-bit tendencies (HIDDEN) are in the table but not in the menu.
"""
TABLE = 'oYeE'
KEY = 'index'

# choice fields: real name -> (the game's label, its words for the values 0, 1, 2 ...)
_OFFENCE = ("Overload", "Crash the Net", "Behind the Net")
CHOICES = {
    'oz_forecheck': ("Forecheck", ("1-2-2 Passive", "2-3", "Weak Side Lock", "1-2-2 Aggressive")),
    'nz_forecheck': ("Neutral Zone", ("1-3-1", "1-4", "1-2-2 Red", "1-2-2 Blue")),
    'opressure': ("Off Pressure", ("Defend Lead", "Conservative", "Standard", "Aggressive", "Full Attack")),
    'dpressure': ("Defensive Pressure", ("Protect Net", "Contain Puck", "Normal", "Puck Side Attack", "High Pressure")),
    'defense': ("Defensive Strategy", ("Collapsing", "Staggered", "Tight Point")),
    'pk': ("Penalty Kill", ("Passive Box", "Large Box", "Diamond")),
    'pp': ("Powerplay", ("Shooting", "Overload", "Umbrella")),
    **{f"offense{n}": (f"Line {n}", _OFFENCE) for n in range(1, 5)},
}

# slider fields: bias number -> (left word, right word) per kind; None: the game's menu does not show it
_FORWARD = {1: ("Carry", "Dump"), 2: None, 3: ("Cycle", "Shoot"), 4: ("Efficiency", "Energy"), 5: ("Don't block", "Block"),
            6: None}
_DEFENCE = {1: ("Hold Line", "Pinch"), 2: ("Cycle", "Shoot"), 3: None, 4: None, 5: None, 6: None}
_TEAM = {1: ("PP Carry", "PP Dump"), 2: None, 3: None, 4: None, 5: None, 6: None}
SLIDER_TOP = 10         # sliders 0 .. 10, 5 in the middle (the menu's bar moves a tenth per press)
TRAP_TOP = 6            # the 3-bit slider NZ ... FC: 0 .. 6 (a sixth per press)

# the window's sections, in the menu's order: (title, [(field, kind)]), kind 'choice' or 'slider'; the tendencies the
# menu does not show come last in their section
_SHOWN = {'forward': (1, 3, 4, 5), 'defense': (1, 2), 'team': (1,)}


def _biases(head, kind):
    shown = _SHOWN[kind]
    return [(f"{head}_bias{k}", 'slider') for k in shown] + [(f"{head}_bias{k}", 'slider') for k in range(1, 7)
                                                              if k not in shown]


SECTIONS = ([("Team Strategies", [('oz_forecheck', 'choice'), ('nz_forecheck', 'choice'), ('trap_forecheck_bias', 'slider')]
              + [(f, 'choice') for f in ('opressure', 'dpressure', 'defense', 'pk', 'pp')] + _biases('team', 'team'))]
            + [(f"Forward Line {n}", [(f"offense{n}", 'choice')] + _biases(f"forward{n}", 'forward')) for n in range(1, 5)]
            + [(f"Defensive Pairing {n}", _biases(f"defense{n}", 'defense')) for n in range(1, 4)])
FIELDS = [f for _, rows in SECTIONS for f, _ in rows]
assert len(FIELDS) == 60 and len(set(FIELDS)) == 60


def slider_words(field):
    """(left, right) words of a slider field, or None when the game's menu does not show it."""
    if field == 'trap_forecheck_bias':
        return ("NZ", "FC")
    head, k = field.rsplit('_bias', 1)
    table = _TEAM if head == 'team' else _DEFENCE if head.startswith('defense') else _FORWARD
    return table[int(k)]


def label(field):
    if field in CHOICES:
        return CHOICES[field][0]
    if field == 'trap_forecheck_bias':
        return "Neutral zone or forecheck"
    words = slider_words(field)
    return f"{words[0]} or {words[1]}" if words else f"Tendency {field.rsplit('_bias', 1)[1]}"


def hidden(field):
    """True for a tendency the game's menu does not show."""
    return field not in CHOICES and slider_words(field) is None


def options(field):
    """[(value, word)] a choice field offers."""
    return list(enumerate(CHOICES[field][1]))


def top(field):
    """The largest value the field may hold."""
    if field == 'trap_forecheck_bias':
        return TRAP_TOP
    return SLIDER_TOP if field not in CHOICES else len(options(field)) - 1


_TAGS = {}


def tag_of(T, field):
    """The table's tag of a real field name."""
    if not _TAGS:
        from .schema import FIELDS as NAMES
        _TAGS.update({real: tag for tag, real in NAMES[TABLE].items()})
    return _TAGS[field]


def row_of(R, slot):
    T = R.f[TABLE]
    key = tag_of(T, KEY)
    return next((i for i in range(T.cur_rec) if T.get(i, key) == slot), None)


def read(R, slot):
    """{field: value} of a team's strategies, or None when the table has no row for it."""
    T = R.f[TABLE]
    row = row_of(R, slot)
    return None if row is None else {f: T.get(row, tag_of(T, f)) for f in FIELDS}


def clean(values):
    """(the values that may be written, plain sentences for those that may not)."""
    ok, problems = {}, []
    for field, value in sorted(values.items()):
        if field not in FIELDS:
            problems.append(f"the game has no strategy called {field}")
        elif not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= top(field):
            problems.append(f"{label(field)}: {value} is not one of the game's choices (0 to {top(field)})")
        else:
            ok[field] = value
    return ok, problems


def write(R, slot, values):
    """Write checked values (clean) into the team's row. Returns how many fields were written."""
    T = R.f[TABLE]
    row = row_of(R, slot)
    if row is None:
        return 0
    for field, value in values.items():
        T.set(row, tag_of(T, field), value)
    return len(values)


def out_of_range(R, source=None):
    """{(slot, field): sentence} for values outside the fields' ranges that `source` (the roster built from) did not
    already have."""
    T = R.f[TABLE]
    key = tag_of(T, KEY)
    was = {}
    if source is not None:
        S = source.f[TABLE]
        for i in range(S.cur_rec):
            was[S.get(i, key)] = {f: S.get(i, tag_of(S, f)) for f in FIELDS}
    out = {}
    for i in range(T.cur_rec):
        slot = T.get(i, key)
        for field in FIELDS:
            value = T.get(i, tag_of(T, field))
            if value > top(field) and was.get(slot, {}).get(field) != value:
                out[(slot, field)] = (f"{R.team_name(slot) if slot < R.T.cur_rec else f'team {slot}'}: strategy "
                                      f"{label(field)} is {value}, the game's choices go to {top(field)}")
    return out
