"""The Roster editor's "Strategies" window without a window toolkit: one team's forecheck, pressure, power play and
penalty kill, and the sliders of the team, each forward line and each defence pair (strategy.py: the game's "Build Your
AI" choices). Apply keeps the values that differ from the roster's in edits.json (`teams[slot]["strategy"]`); they go in
after every update (edits.apply_teams)."""
import threading

from .. import layout as L
from .. import strategy as ST
from .editor import NO_ROSTER, RAIL

SLICE = 'strategy'
NOTE = ("The same choices as the game's own Strategy menu (Coaching Options), in its order. Sliders go from the left "
        "word to the right one; the middle is 5. The tendencies at the end of a section are in the roster but not in the "
        "game's menu; most teams keep them at 5.")


class StrategyController:
    def __init__(self, host, editor):
        self.host, self.editor = host, editor
        editor.strategy = self
        self.lock = threading.RLock()
        self.team = None                # the team shown (None: the window is closed)
        self.base = {}                  # the roster's values (with edits made before this visit)
        self.values = {}
        self.note = ''
        # the Strategy tab (it follows the team picked in the team list; the old window is opened by hand)
        self.tabbed = False
        self.visible = False
        self.shown = None               # the team the tab follows (its strategies may not be shown: self.why says why)
        self.why = ''
        self.stale = False
        self.roster = None
        self.kept = {}                  # team -> {field: value} changed but not applied
        editor.follow_with('strategy', self)

    def changed(self):
        self.host.changed(SLICE)

    def open(self):
        ed = self.editor
        with ed.lock:
            team, snap = ed.team, ed.snap
            if not isinstance(team, int) or snap is None:
                ed.set_status("Pick a team first.", 'warn')
                return
            if team in L.MIRROR_OF:
                ed.set_status("This team is a copy of another one: change the strategies of the team itself.", 'warn')
                return
            base = ST.read(snap.R, team)
            if base is None:
                ed.set_status("This team has no strategies in the roster.", 'warn')
                return
        with self.lock:
            self.team, self.base, self.values, self.note = team, base, dict(base), ''
            self.changed()

    def close(self):
        with self.lock:
            self.team = None
            self.changed()

    # --- the Strategy tab ------------------------------------------------------------------------------
    def follow(self, team):
        """The tab shows `team` (None: no roster yet). Values changed but not applied stay with their team."""
        ed = self.editor
        with ed.lock, self.lock:
            self.tabbed, self.visible = True, True
            key = ed.roster_key()
            if key != self.roster:
                self.roster, self.kept, self.stale, self.team = key, {}, True, None
            if team == self.shown and not self.stale:
                return
            self._keep()
            same = team == self.shown
            self.shown, self.stale, self.team, self.why = team, False, None, ''
            if not same:
                self.note = ''
            snap = ed.snap
            base = None
            if snap is None or team is None:
                self.why = "Reading the roster..." if ed.busy else NO_ROSTER
            elif not isinstance(team, int):
                self.why = "Free agents have no strategies. Pick a team in the list."
            elif team in L.MIRROR_OF:
                self.why = "This team is a copy of another one: change the strategies of the team itself."
            else:
                base = ST.read(snap.R, team)
                if base is None:
                    self.why = "This team has no strategies in the roster."
            if base is not None:
                self.team, self.base, self.values = team, base, dict(base)
                self.values.update({f: v for f, v in self.kept.pop(team, {}).items() if f in base})
            self.changed()

    def _touched(self):
        return any(self.values.get(f) != self.base.get(f) for f in ST.FIELDS)

    def _keep(self):
        if self.team is None:
            return
        changed = {f: v for f, v in self.values.items() if v != self.base.get(f)}
        if changed:
            self.kept[self.team] = changed
        else:
            self.kept.pop(self.team, None)

    def hide(self):
        with self.lock:
            self.visible = False

    def roster_changed(self):
        with self.lock:
            self.stale = True

    def drafts(self):
        """Teams with strategies changed but not applied."""
        with self.lock:
            return set(self.kept) | ({self.team} if self.team is not None and self._touched() else set())

    def set(self, field, value):
        with self.lock:
            if self.team is None or field not in ST.FIELDS:
                return
            try:
                n = int(value)
            except (TypeError, ValueError):
                return
            if 0 <= n <= ST.top(field):
                self.values[field] = n
                self.note = ''
                self.changed()
        self.host.changed(RAIL)

    def reset(self, field=None):
        """Back to the roster's value (one field, or all)."""
        with self.lock:
            if self.team is None:
                return
            for f in [field] if field else ST.FIELDS:
                if f in self.base:
                    self.values[f] = self.base[f]
            self.changed()
        self.host.changed(RAIL)

    def apply(self):
        ed = self.editor
        with ed.lock, self.lock:
            if self.team is None:
                return
            key = str(self.team)
            mine = dict(ed.teams.get(key) or {})
            plan = dict(mine.get('strategy') or {})
            plan.update({f: v for f, v in self.values.items() if v != self.base.get(f)})
            ok, _ = ST.clean(plan)
            if not ok:
                ed.set_status("Nothing changed.")
                return
            mine['strategy'] = dict(sorted(ok.items()))
            ed.teams[key] = mine
            ed.session_teams.add(key)
            ed._edits_saved(players=False)
            self.base = dict(self.values)
            self.kept.pop(self.team, None)
            self.note = "Applied. Save the roster to keep them in it; every later update keeps them too."
            ed.refresh()
            self.changed()
        self.host.changed(RAIL)

    def undo(self):
        """Take back the team's own strategies: the roster's are used again after the next update."""
        ed = self.editor
        with ed.lock, self.lock:
            if self.team is None:
                return
            key = str(self.team)
            mine = ed.teams.get(key)
            if mine and 'strategy' in mine:
                mine = {k: v for k, v in mine.items() if k != 'strategy'}
                if mine:
                    ed.teams[key] = mine
                else:
                    ed.teams.pop(key, None)
                ed._edits_saved(players=False)
            if not ed.teams.get(key):
                ed.session_teams.discard(key)
            if self.tabbed:                 # the tab stays on the team: it reads it again once the roster is rebuilt
                self.kept.pop(self.team, None)
                self.values, self.stale, self.note = dict(self.base), True, ''
            else:
                self.team = None
            ed.refresh()
            self.changed()
            ed.set_status("Your strategies are taken back. A new roster made from the community roster has its own again.")
        self.host.changed(RAIL)

    def snapshot(self):
        with self.editor.lock, self.lock:
            if self.team is None:
                return {'why': self.why, 'view': self.editor.team_view(self.shown)} if self.tabbed else None
            snap = self.editor.snap
            mine = (self.editor.teams.get(str(self.team)) or {}).get('strategy') or {}
            sections = []
            for title, rows in ST.SECTIONS:
                items = []
                for field, kind in rows:
                    row = {'field': field, 'label': ST.label(field), 'kind': kind, 'value': self.values.get(field, 0),
                           'changed': self.values.get(field) != self.base.get(field), 'mine': field in mine,
                           'top': ST.top(field), 'hidden': ST.hidden(field)}
                    if kind == 'choice':
                        row['options'] = [{'value': v, 'label': w} for v, w in ST.options(field)]
                    else:
                        words = ST.slider_words(field)
                        row['left'], row['right'] = words if words else ('', '')
                    items.append(row)
                sections.append({'title': title, 'rows': items})
            touched = self._touched()
            return {'team': self.team, 'title': f"{snap.team_name(self.team) if snap else ''}: strategies",
                    'sections': sections, 'note': self.note or NOTE, 'can_apply': touched, 'mine': bool(mine),
                    'view': self.editor.team_view(self.team)}
