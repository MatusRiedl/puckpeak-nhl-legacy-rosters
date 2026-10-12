"""The equipment test (cli `equipment-test`): one LAB roster in which the skaters of Anaheim and Winnipeg wear every number of
the choices without a picture, one choice per player in turn, for the owner to look at in the game (Roster Management >
Edit Players > the player > Customization, or the player on the ice).

What it answers: which number of `jerseytuck`, `skatesocktuck`, `sticktapecolor`, `visorcolor`, `shoulderpads` and
`pantstypecode` is which word of the game's menu (equipment.OPTIONS holds our guesses), and whether the game reads the
roster's value at all. A report (equipment_test.txt in the program's reports folder) lists who wears what.
"""
from . import datasource, equipment as E, layout as L, savedata
from .builder import Data
from .pipeline import build
from .roster import Roster

SLOTS = (0, 1)          # Anaheim, then Winnipeg: the test needs more skaters than one team has
CHOICES = ('jersey_tuck', 'sock_tuck', 'tape', 'visor_tint', 'shoulder_pads', 'pant_length')


def plan(options=E.OPTIONS, choices=CHOICES):
    """[(choice, number)] one per test player: every number of every choice."""
    return [(c, n) for c in choices for n, _label in options[c]]


def equipment_test(folder, slot, say=print):
    """Save the LAB roster next to `slot` (a roster save) in the save folder `folder`; returns the new save."""
    raw = savedata.read_roster(slot)
    L.check_base(Roster(raw))
    result = build(raw, Data(season_year=2026), [])
    R = Roster(result.data)
    U, P, table = R.U, R.P, R.f[E.TABLE]
    rows = E.row_of(table)
    people = []
    for e in range(U.cur_rec):
        if U.get(e, 'BSXd') not in SLOTS:
            continue
        prow = R.p_by_id.get(R.link_to_pid.get(U.get(e, 'TWSX')))
        if prow is not None and P.get(prow, 'aljv') != 4 and P.get(prow, 'zIBw') in rows:
            people.append(prow)
    wanted = plan()
    if len(people) < len(wanted):
        raise RuntimeError(f"the two teams have {len(people)} skaters, the test needs {len(wanted)}")
    lines = [f"Equipment test: the skaters of {R.team_name(SLOTS[0])} and {R.team_name(SLOTS[1])} wear one number each.",
             "In the game: Roster Management > Edit Players > the team > the player > Customization (or watch the ice).",
             "Compare the game's words with the 'we say' column; write down every line that differs.", ""]
    for prow, (choice, n) in zip(people, wanted):
        row = rows[P.get(prow, 'zIBw')]
        E.write(table, row, E.NEW_PLAYER)                   # plain everywhere else
        E.write(table, row, {'visor': 1})                   # a visor, so that its tint shows
        E.write(table, row, {choice: n})
        label = dict(E.OPTIONS[choice])[n]
        lines.append(f"{R.name(prow)}: {E.CHOICES[choice][1]} number {n}, we say \"{label}\"")
    new = savedata.install(folder, slot, R.f.build(), "EQUIPMENT TEST")
    with open(datasource.app_dir('reports', 'equipment_test.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    for line in lines:
        say(line)
    return new
