"""The equipment test (cli `equipment-test`): one LAB roster in which clearly named test players wear one number each of
the choices without a picture, everything else plain, for the owner (or the lab) to look at in the game (Roster
Management > Edit Players > the player > Customization, or the player on the ice).

What it answers: which number of `jerseytuck`, `skatesocktuck`, `sticktapecolor`, `visorcolor`, `visortype`,
`shoulderpads` and `pantstypecode` (and the goalies' tape, jersey tuck and neck guard) is which word of the game's menu
(equipment.OPTIONS holds our guesses), what each word looks like, and whether the game reads the roster's value at all.
The test players are named after what they wear ("Sock Zero", "Tape Seven", "Visor Two", "Goalie Neck One"); a report
(equipment_test.txt in the program's reports folder) lists who wears what and in which team.

`make(R)` changes a parsed roster in place (the lab driver private/lab/eqlab.py calls it on a patched lab roster);
`equipment_test` builds a copy of a roster save with it (the command line).
"""
from . import datasource, equipment as E, layout as L, savedata
from .builder import Data
from .pipeline import build
from .roster import Roster

SLOTS = (0, 1, 3, 4, 6, 7, 8, 9)     # Anaheim, Winnipeg, then more teams while the test needs more skaters / goalies
CHOICES = ('sock_tuck', 'jersey_tuck', 'tape', 'visor', 'visor_tint', 'shoulder_pads', 'pant_length')
FIRST = {'sock_tuck': 'Sock', 'jersey_tuck': 'Jersey', 'tape': 'Tape', 'visor': 'Visor', 'visor_tint': 'Tint',
         'shoulder_pads': 'Pads', 'pant_length': 'Pants'}
DIGITS = ['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine']
# the numbers each choice is tried with (the table's field can hold more: tint 0-15)
NUMBERS = {'sock_tuck': range(4), 'jersey_tuck': range(4), 'tape': range(10), 'visor': range(3), 'visor_tint': range(8),
           'shoulder_pads': range(2), 'pant_length': range(2)}
# goalies: (last name, {choice: number}); the first one is the plain goalie to compare with
GOALIE_TESTS = [('Plain', {}), ('Tape Zero', {'tape': 0}), ('Tape One', {'tape': 1}), ('Tape Two', {'tape': 2}),
                ('Tape Nine', {'tape': 9}), ('Tuck One', {'jersey_tuck': 1}), ('Tuck Two', {'jersey_tuck': 2}),
                ('Tuck Three', {'jersey_tuck': 3}), ('Neck One', {'neck': 1})]
GOALIE_PLAIN = {'tape': 1, 'jersey_tuck': 0, 'neck': 0}
SKATER_PLAIN = dict(E.NEW_PLAYER, visor=0, visor_tint=0)      # no visor, no tucks, small pads, short pants, white tape


def plan(choices=CHOICES):
    """[(choice, number)] one per skater: every number of every choice."""
    return [(c, n) for c in choices for n in NUMBERS[c]]


def name_of(choice, number):
    return FIRST[choice], DIGITS[number]


def _people(R, slots, goalies):
    """[(player row, team slot)] of the NHL entries of `slots`, in roster order, once per player."""
    U, P = R.U, R.P
    rows = E.row_of(R.f[E.GOALIE_TABLE] if goalies else R.f[E.TABLE], 'goalie' if goalies else 'skater')
    out, seen = [], set()
    for slot in slots:
        for e in range(U.cur_rec):
            if U.get(e, 'BSXd') != slot:
                continue
            prow = R.p_by_id.get(R.link_to_pid.get(U.get(e, 'TWSX')))
            if prow is None or prow in seen or (P.get(prow, 'aljv') == 4) != goalies:
                continue
            if P.get(prow, 'zIBw') in rows:
                seen.add(prow)
                out.append((prow, slot))
    return out


def make(R, slots=SLOTS):
    """Give the test players their names and their gear in the parsed roster `R`. Returns the report lines."""
    P = R.P
    skaters = plan()
    goalies = GOALIE_TESTS
    skater_pool = _people(R, slots, False)
    goalie_pool = _people(R, slots, True)
    if len(skater_pool) < len(skaters) or len(goalie_pool) < len(goalies):
        raise RuntimeError(f"the teams have {len(skater_pool)} skaters and {len(goalie_pool)} goalies, the test needs "
                           f"{len(skaters)} and {len(goalies)}")
    lines = ["Equipment test: players named after what they wear (everything else plain).",
             "In the game: Roster Management > Edit Players > the team > the player > Customization (or watch the ice).",
             "Compare the game's words with the 'we say' column; write down every line that differs.", ""]
    table, gtable = R.f[E.TABLE], R.f[E.GOALIE_TABLE]
    rows, grows = E.row_of(table), E.row_of(gtable, 'goalie')
    for (prow, slot), (choice, n) in zip(skater_pool, skaters):
        row = rows[P.get(prow, 'zIBw')]
        E.write(table, row, SKATER_PLAIN)
        E.write(table, row, {'visor': 1} if choice == 'visor_tint' else {})     # a visor, so that its tint shows
        E.write(table, row, {choice: n})
        first, last = name_of(choice, n)
        P.set(prow, 'PedH', first)
        P.set(prow, 'RMbQ', last)
        label = dict(E.OPTIONS[choice]).get(n, '(not offered)')
        lines.append(f"{R.team_name(slot)}: {first} {last}: {E.CHOICES[choice][1]} number {n}, we say \"{label}\"")
    for (prow, slot), (last, values) in zip(goalie_pool, goalies):
        row = grows[P.get(prow, 'zIBw')]
        E.write(gtable, row, E.clean(dict(GOALIE_PLAIN, **values), gtable, 'goalie')[0], 'goalie')
        P.set(prow, 'PedH', 'Goalie')
        P.set(prow, 'RMbQ', last)
        lines.append(f"{R.team_name(slot)}: Goalie {last}: {values or 'plain (tape 1, tuck 0, neck 0)'}")
    return lines


def equipment_test(folder, slot, say=print):
    """Save the LAB roster next to `slot` (a roster save) in the save folder `folder`; returns the new save."""
    raw = savedata.read_roster(slot)
    L.check_base(Roster(raw))
    result = build(raw, Data(season_year=2026), [])
    R = Roster(result.data)
    lines = make(R)
    new = savedata.install(folder, slot, R.f.build(), "EQUIPMENT TEST")
    with open(datasource.app_dir('reports', 'equipment_test.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    for line in lines:
        say(line)
    return new
