"""The Roster editor's "Lines" window without a window toolkit: one team's four lines, three pairs and two goalies,
the power play, the penalty kill, overtime, the shootout, the extra attackers, and who wears the C and the A.

The player clicks a place, then a player of the team: he goes there (swapping with the one who had it when he already
plays in that group of units; a scratched player who comes into the lineup also takes over the special-team places of
the one he replaces). The game's rules are checked as he goes (lines.check_lineup); Apply keeps the lines in edits.json
(`teams[slot]["lines"]`), and they go in after every update (edits.apply_teams) while they still fit the team.
"""
import threading

from .. import layout as L
from .. import lines as LN
from .. import schema
from .editor import NO_ROSTER, RAIL

SLICE = 'lines'
_LINE = lambda k: [f"l{k}lw", f"l{k}c", f"l{k}rw"]
_PAIR = lambda k: [f"l{k}ld", f"l{k}rd"]
TABS = (
    ('even', "Lines", [(f"Line {k}", _LINE(k)) for k in range(1, 5)] + [(f"Pair {k}", _PAIR(k)) for k in range(1, 4)]
     + [("Goalies", ['g1', 'g2'])]),
    ('pp', "Power play", [(f"Unit {k}", [f"pp{k}{p}" for p in ('lw', 'c', 'rw', 'ld', 'rd')]) for k in (1, 2)]
     + [(f"4 skaters, unit {k}", [f"pp4_{k}{p}" for p in ('lw', 'c', 'ld', 'rd')]) for k in (1, 2)]),
    ('pk', "Penalty kill", [(f"4 skaters, unit {k}", [f"pk4_{k}{p}" for p in ('lw', 'c', 'ld', 'rd')]) for k in (1, 2)]
     + [(f"3 skaters, unit {k}", [f"pk3_{k}{p}" for p in ('c', 'ld', 'rd')]) for k in (1, 2)]),
    ('ot', "Overtime", [(f"Unit {k}", [f"ot_{k}{p}" for p in ('lw', 'c', 'ld', 'rd')]) for k in (1, 2, 3)]),
    ('so', "Shootout, extra attackers", [("Shooters", schema.SHOOTOUT), ("Extra attackers", schema.EXTRA_ATTACKER)]),
    ('letters', "Captains", []),
)
assert sorted(s for _, _, rows in TABS for _, names in rows for s in names) == sorted(LN.S)
DRESSED = schema.EVEN_STRENGTH + schema.GOALIE_SLOTS
NOTE = ("Click a place, then a player. The game plays these lines in Play Now. A new Season or Be a GM picks its own "
        "lines at the start: change them there in Coaching Options. An update keeps them while all these players are on "
        "the team.")


def _short(slot):
    """The place's own name inside its unit: 'LW', 'C', 'Shooter 2', 'Starting'."""
    if slot in ('g1', 'g2'):
        return 'Starting' if slot == 'g1' else 'Backup'
    if slot[0] in 'sx':
        return LN.slot_label(slot).replace('Extra attacker', 'Attacker')
    return LN.slot_label(slot).rsplit(' ', 1)[1]


def _group_of(slot):
    return next(names for _, names in LN.GROUPS if slot in names)


class LinesController:
    def __init__(self, host, editor):
        self.host, self.editor = host, editor
        editor.lines = self
        self.lock = threading.RLock()
        self.team = None                # the team shown (None: the window is closed)
        self.tab = 'even'
        self.slots, self.letters = {}, {}       # {slot: person key}, {person key: 'C' | 'A'}
        self.players = {}               # person key -> {'name', 'pos', 'ovr', 'num'}
        self.picked = None              # the place clicked, waiting for a player
        self.touched = False
        self.note = ''
        # the Lines tab (it follows the team picked in the team list; the old window is opened by hand)
        self.tabbed = False             # True once the tab has shown a team
        self.visible = False
        self.shown = None               # the team the tab follows (its lines may not be shown: self.why says why)
        self.why = ''
        self.stale = False              # the roster was read again: read the team again too
        self.roster = None              # editor.roster_key() the drafts belong to
        self.kept = {}                  # team -> (slots, letters) changed but not applied
        editor.follow_with('lines', self)

    def changed(self):
        self.host.changed(SLICE)

    # --- open and close ------------------------------------------------------------------------------
    def open(self):
        ed = self.editor
        with ed.lock:
            team, snap = ed.team, ed.snap
            if not isinstance(team, int) or snap is None:
                ed.set_status("Pick a team first.", 'warn')
                return
            if team in L.MIRROR_OF:
                ed.set_status("This team is a copy of another one: change the lines of the team itself.", 'warn')
                return
            read = self._read(snap, team)
            if read is None:
                ed.set_status("This team has too few players for lines: a team needs 2 goalies and 18 skaters.", 'warn')
                return
            mine = ((ed.teams.get(str(team)) or {}).get('lines'))
        with self.lock:
            self.team, self.tab, self.picked, self.touched, self.note = team, 'even', None, False, ''
            self.slots, self.letters, self.players = read
            if mine and all(w in self.players for w in list(mine['slots'].values()) + list(mine.get('letters', {}))):
                self.slots, self.letters = dict(mine['slots']), dict(mine.get('letters', {}))
            self.changed()

    @staticmethod
    def _read(snap, team):
        """(slots, letters, players) of a team in the shown roster, or None when it cannot dress 20."""
        R = snap.R
        U = R.U
        slots, letters, players = {}, {}, {}
        for e in range(U.cur_rec):
            if U.get(e, 'BSXd') != team:
                continue
            p = snap.players.get(R.link_to_pid.get(U.get(e, 'TWSX')))
            if p is None:
                continue
            players[p.who] = {'name': p.name, 'pos': p.pos, 'ovr': p.ovr, 'num': U.get(e, 'tRVs')}
            for name, tag in LN.S.items():
                if U.get(e, tag):
                    slots.setdefault(name, p.who)
            if U.get(e, 'lcCm') in LN.LETTERS:
                letters[p.who] = LN.LETTERS[U.get(e, 'lcCm')]
        goalies = sum(1 for p in players.values() if p['pos'] == 'G')
        if goalies < 2 or len(players) - goalies < 18:
            return None
        return slots, letters, players

    def close(self):
        with self.lock:
            self.team, self.picked = None, None
            self.changed()

    # --- the Lines tab ---------------------------------------------------------------------------------
    def follow(self, team):
        """The tab shows `team` (None: no roster yet). Lines changed but not applied stay with their team."""
        ed = self.editor
        with ed.lock, self.lock:
            self.tabbed, self.visible = True, True
            key = ed.roster_key()
            if key != self.roster:
                self.roster, self.kept, self.stale = key, {}, True
                self.team, self.touched = None, False
            if team == self.shown and not self.stale:
                return
            self._keep()
            same = team == self.shown
            self.shown, self.stale, self.picked = team, False, None
            self.team, self.touched, self.why = None, False, ''
            if not same:
                self.note = ''
            snap = ed.snap
            if snap is None or team is None:
                self.why = "Reading the roster..." if ed.busy else NO_ROSTER
            elif not isinstance(team, int):
                self.why = "Free agents have no lines. Pick a team in the list."
            elif team in L.MIRROR_OF:
                self.why = "This team is a copy of another one: change the lines of the team itself."
            else:
                read = self._read(snap, team)
                if read is None:
                    self.why = "This team has too few players for lines: a team needs 2 goalies and 18 skaters."
                else:
                    self.team = team
                    self.slots, self.letters, self.players = read
                    draft = self.kept.pop(team, None)
                    mine = (ed.teams.get(str(team)) or {}).get('lines')
                    if draft and self._fits(*draft):
                        self.slots, self.letters = dict(draft[0]), dict(draft[1])
                        self.touched = True
                    elif mine and self._fits(mine['slots'], mine.get('letters', {})):
                        self.slots, self.letters = dict(mine['slots']), dict(mine.get('letters', {}))
            self.changed()

    def _fits(self, slots, letters):
        return all(w in self.players for w in list(slots.values()) + list(letters))

    def _keep(self):
        """Keep the shown team's unapplied lines for when it comes back."""
        if self.team is not None and self.touched:
            self.kept[self.team] = (dict(self.slots), dict(self.letters))
        elif self.team is not None:
            self.kept.pop(self.team, None)

    def hide(self):
        with self.lock:
            self.visible = False

    def roster_changed(self):
        with self.lock:
            self.stale = True

    def drafts(self):
        """Teams with lines changed but not applied."""
        with self.lock:
            return set(self.kept) | ({self.team} if self.touched and self.team is not None else set())

    # --- the choices -----------------------------------------------------------------------------------
    def set_tab(self, tab):
        with self.lock:
            if self.team is not None and tab in {t for t, _, _ in TABS}:
                self.tab, self.picked = tab, None
                self.changed()

    def pick_slot(self, slot):
        with self.lock:
            if self.team is None or slot not in LN.S:
                return
            self.picked = None if self.picked == slot else slot
            self.changed()

    def place(self, who):
        """The player `who` goes to the place clicked."""
        with self.lock:
            slot = self.picked
            if self.team is None or slot is None or who not in self.players:
                return
            had = self.slots.get(slot)
            group = _group_of(slot)
            mine = next((s for s in group if self.slots.get(s) == who), None)
            dressed = {self.slots.get(s) for s in DRESSED}
            if mine is not None:                     # he plays in this group already: the two swap places
                self.slots[mine] = had
            elif slot in DRESSED and who not in dressed and had is not None:
                for s, w in list(self.slots.items()):     # a scratch comes in: he takes every place of the one he replaces
                    if w == had:
                        self.slots[s] = who
            self.slots[slot] = who          # (a scratched captain keeps his letter: the game allows it)
            self.picked = None
            self.touched = True
            self.changed()
        self.host.changed(RAIL)

    def set_letter(self, who, letter):
        with self.lock:
            if self.team is None or who not in self.players:
                return
            if letter == 'C':
                for w, l in list(self.letters.items()):
                    if l == 'C':
                        self.letters.pop(w)
            if letter in ('C', 'A'):
                self.letters[who] = letter
            else:
                self.letters.pop(who, None)
            self.touched = True
            self.changed()
        self.host.changed(RAIL)

    def _problems(self):
        pos = {w: p['pos'] for w, p in self.players.items()}
        name = {w: p['name'] for w, p in self.players.items()}
        return LN.check_lineup(self.slots, self.letters, pos, name, nhl=self.team in L.NHL_PRIMARY)

    def apply(self):
        ed = self.editor
        with ed.lock, self.lock:
            if self.team is None:
                return
            problems = self._problems()
            if problems:
                ed.set_status(problems[0], 'warn')
                return
            mine = dict(ed.teams.get(str(self.team)) or {})
            mine['lines'] = {'slots': dict(sorted(self.slots.items())), 'letters': dict(sorted(self.letters.items()))}
            ed.teams[str(self.team)] = mine
            ed.session_teams.add(str(self.team))
            ed._edits_saved(players=False)
            self.touched = False
            self.kept.pop(self.team, None)
            self.note = "Applied. Save the roster to keep them in it; every later update keeps them too."
            ed.refresh()
            self.changed()
        self.host.changed(RAIL)

    def undo(self):
        """Take back the team's own lines: the update's lines are used again."""
        ed = self.editor
        with ed.lock, self.lock:
            if self.team is None:
                return
            key = str(self.team)
            mine = ed.teams.get(key)
            if mine and 'lines' in mine:
                mine = {k: v for k, v in mine.items() if k != 'lines'}
                if mine:
                    ed.teams[key] = mine
                else:
                    ed.teams.pop(key, None)
                ed._edits_saved(players=False)
            if not ed.teams.get(key):
                ed.session_teams.discard(key)
            if self.tabbed:                 # the tab stays on the team: it reads it again once the roster is rebuilt
                self.kept.pop(self.team, None)
                self.touched, self.picked, self.stale, self.note = False, None, True, ''
            else:
                self.team, self.picked = None, None
            ed.refresh()
            self.changed()
            ed.set_status("Your lines are taken back. The next update gives the team its lines again.")
        self.host.changed(RAIL)

    # --- what the page shows ---------------------------------------------------------------------------
    def snapshot(self):
        with self.editor.lock, self.lock:
            if self.team is None:
                return {'why': self.why, 'view': self.editor.team_view(self.shown)} if self.tabbed else None
            snap = self.editor.snap
            where = {}
            rows = next(rows for t, _, rows in TABS if t == self.tab)
            for title, names in rows:
                for s in names:
                    if self.slots.get(s):
                        where.setdefault(self.slots[s], []).append(
                            _short(s) if title in ('Shooters', 'Extra attackers') else f"{title} {_short(s)}")
            dressed = {self.slots.get(s) for s in DRESSED}
            player = lambda w: dict(self.players[w], who=w) if w in self.players else None
            units = [{'title': title, 'slots': [{'slot': s, 'label': _short(s), 'full': LN.slot_label(s),
                                                  'player': player(self.slots.get(s)), 'picked': s == self.picked}
                                                 for s in names]} for title, names in rows]
            order = {'C': 0, 'L': 1, 'R': 2, 'D': 3, 'G': 4}
            people = sorted(self.players, key=lambda w: (w not in dressed, order.get(self.players[w]['pos'], 5),
                                                         -(self.players[w]['ovr'] or 0), self.players[w]['name']))
            picked_goal = self.picked in ('g1', 'g2')
            side = [dict(player(w), dressed=w in dressed, letter=self.letters.get(w), where=', '.join(where.get(w, [])),
                         fits=self.picked is None or (self.players[w]['pos'] == 'G') == picked_goal) for w in people]
            problems = self._problems()
            mine = bool((self.editor.teams.get(str(self.team)) or {}).get('lines'))
            return {'team': self.team, 'title': f"{snap.team_name(self.team) if snap else ''}: lines",
                    'tab': self.tab, 'tabs': [{'id': t, 'label': label} for t, label, _ in TABS],
                    'units': units, 'players': side, 'picked': self.picked,
                    'picked_label': LN.slot_label(self.picked) if self.picked else None,
                    'problems': problems, 'can_apply': not problems and (self.touched or not mine),
                    'touched': self.touched, 'mine': mine, 'note': self.note or NOTE,
                    'view': self.editor.team_view(self.team),
                    'letters_rule': ("One captain and two alternates, or no captain and three alternates."
                                     if self.team in L.NHL_PRIMARY else "One captain at most, three letters at most.")}
