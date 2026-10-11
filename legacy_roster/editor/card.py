"""The Roster editor's player card without a window: what a typed card means and what edit it makes.

    read(values, labels, new, choices)    the typed card checked: (values, None) or (None, what is wrong)
    new_player(values, photo)             (person key, edit) for a player who is not in the roster yet
    player_edit(p, values, edit, photo)   the edit of player `p` with the card's changes, and whether any is real
    renamed(my_edits, only)               new key -> original key of every player an edit renamed
    change_note(old, new, fields)         'OVR 83 → 86, #10 → 12' for the table's Change column

The card's `values` are what the page sends: texts as typed ('first', 'last', 'num', 'pos', 'shoots', 'birth',
'country', 'height', 'weight', 'ovr'), 'team' (a slot number or 'FA') and 'ratings' (label -> text).
"""
import datetime

from .. import layout as L
from ..art.portraits import person_key
from . import model

POSITIONS = ('C', 'LW', 'RW', 'D', 'G')


def cm(inches):
    return round(inches * 2.54)


def kg(pounds):
    return round(pounds * 0.4536)


def change_note(old, new, fields):
    """'OVR 83 → 86, #10 → 12' rather than field names."""
    if old is None:
        return "changed"
    words = {'ovr': lambda: f"OVR {old.ovr} → {new.ovr}", 'num': lambda: f"#{old.num} → {new.num}",
             'pos': lambda: f"{old.pos} → {new.pos}", 'first': lambda: "name", 'last': lambda: "name",
             'birth': lambda: "birthdate", 'country': lambda: f"{old.country} → {new.country}",
             'shoots': lambda: "shoots", 'height_in': lambda: "height", 'weight_lb': lambda: "weight",
             'ratings': lambda: "ratings"}
    out = []
    for f in fields:
        text = words.get(f, lambda: f)()
        if text not in out:
            out.append(text)
    return ", ".join(out)


def _text(values, key):
    v = values.get(key)
    return '' if v is None else str(v)


def team_value(value):
    """A team as the page sends it ('FA', 12 or '12') -> 'FA' or the slot number; None when it is neither."""
    if value == model.FREE_AGENTS:
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read(values, labels, new, choices, current=None):
    """The card's values, checked: (values, None) or (None, what is wrong). `labels`: the rating names the card
    shows; `new`: a player not in the roster yet (he needs an overall); `choices`: the teams that can be picked;
    `current`: the player's ratings now. A rating left as the game has it is not checked (the game's own go
    below 40, a defenseman's faceoffs for one); a typed one must be 40-99."""
    current = current or {}
    out = {'first': _text(values, 'first').strip(), 'last': _text(values, 'last').strip(),
           'pos': _text(values, 'pos'), 'shoots': _text(values, 'shoots') or 'L',
           'country': _text(values, 'country').strip().upper()}
    if not out['first'] or not out['last']:
        return None, "A player needs a first and a last name."
    if out['pos'] not in POSITIONS:
        return None, "Pick the position from the list."
    try:
        out['num'] = int(_text(values, 'num'))
        if not 1 <= out['num'] <= 99:
            raise ValueError
    except ValueError:
        return None, "The number must be between 1 and 99."
    try:
        out['birth'] = list(datetime.date.fromisoformat(_text(values, 'birth').strip()).timetuple()[:3])
    except ValueError:
        return None, "Write the birthdate as YYYY-MM-DD, for example 2004-11-16."
    if L.country_code(out['country']) is None:
        return None, f"The game has no country {out['country'] or '(empty)'}; pick one from the list."
    height, weight = _text(values, 'height').strip(), _text(values, 'weight').strip()
    try:
        out['height_in'] = round(int(height) / 2.54) if height else None
        out['weight_lb'] = round(int(weight) / 0.4536) if weight else None
    except ValueError:
        return None, "Height and weight are whole numbers (cm, kg)."
    team = team_value(values.get('team'))
    if team is None or team not in choices:
        return None, "Pick the team from the list."
    out['team'] = team
    rated = {}
    typed = values.get('ratings') or {}
    for label in labels:
        v = _text(typed, label).strip()
        if not v:
            continue
        try:
            rated[label] = int(v)
            if rated[label] != current.get(label) and not 40 <= rated[label] <= 99:
                raise ValueError
        except ValueError:
            return None, f"{label}: ratings go from 40 to 99."
    out['ratings'] = rated
    if new:
        try:
            out['ovr'] = int(_text(values, 'ovr'))
            if not 40 <= out['ovr'] <= 99:
                raise ValueError
        except ValueError:
            return None, "Give the new player an overall (40-99)."
    return out, None


def new_player(values, photo=None):
    """(person key, edit) of a new player from a checked card."""
    who = person_key(values['first'], values['last'], values['birth'])
    fields = {k: values[k] for k in ('first', 'last', 'num', 'pos', 'shoots', 'birth', 'country',
                                     'height_in', 'weight_lb') if values.get(k) is not None}
    fields['pos'] = model.POS_KEY[values['pos']]
    edit = {'label': f"{values['first']} {values['last']}", 'new': True, 'set': fields,
            'team': values['team'], 'ovr': values['ovr'],
            **({'ratings': values['ratings']} if values['ratings'] else {}),
            **({'photo': photo} if photo else {})}
    return who, edit


def player_edit(p, values, edit=None, photo=None):
    """(edit, real): the edit of player `p` (model.Player) with what the checked card changes, on top of his
    earlier `edit`; `real` says whether the card changes anything."""
    e = dict(edit or {'label': p.name})
    current = {'first': p.first, 'last': p.last, 'num': p.num, 'pos': model.POS_KEY.get(p.pos, p.pos),
               'shoots': p.shoots, 'birth': list(p.birth), 'country': p.country,
               'height_in': p.height_in, 'weight_lb': p.weight_lb}
    wanted = dict(values, pos=model.POS_KEY[values['pos']])
    changes = {k: wanted[k] for k in current if wanted.get(k) is not None and wanted[k] != current[k]
               and not (k == 'height_in' and cm(current[k]) == cm(wanted[k]))
               and not (k == 'weight_lb' and kg(current[k]) == kg(wanted[k]))}
    if any(k in changes for k in ('first', 'last', 'birth')) and 'was' not in e:
        e['was'] = {'first': p.first, 'last': p.last, 'birth': list(p.birth)}
    e['set'] = dict(e.get('set') or {}, **changes)
    rated = {a: v for a, v in values['ratings'].items() if p.ratings.get(a) != v}
    if rated:
        e['ratings'] = dict(e.get('ratings') or {}, **rated)
    teams = model.club(p.teams)
    team_changed = values['team'] != (teams[0] if teams else model.FREE_AGENTS)
    if team_changed:
        e['team'] = values['team']
    if photo:
        e['photo'] = photo
    return e, bool(changes or rated or team_changed or photo)


def renamed(my_edits, only=None):
    """New key -> original key of every player an edit renamed (or gave another birthdate); with `only`, just
    the edits whose keys are in it (this visit's: the earlier ones are in the roster under the new name)."""
    out = {}
    for who, e in my_edits.items():
        if only is not None and who not in only:
            continue
        s, was = e.get('set') or {}, e.get('was')
        if was and any(s.get(k) for k in ('first', 'last', 'birth')):
            out[person_key(s.get('first') or was['first'], s.get('last') or was['last'],
                           s.get('birth') or was['birth'])] = who
    return out


def what_changed(edit):
    """The parts of one player's edit, for the My edits list."""
    what = ['new player'] if edit.get('new') else []
    return what + list(edit.get('set') or {}) + (['ratings'] if edit.get('ratings') else []) + \
        (['team'] if 'team' in edit else []) + (['photo'] if edit.get('photo') else []) + \
        (['equipment'] if edit.get('equipment') else [])
