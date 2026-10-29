"""The Draft & Pro tab without a window toolkit: the player's draft classes (made-up prospects for the next four drafts
of a new Be a GM / Season, draftclass.py) and his own Be a Pro player.

A class player is a new player of My edits with a prospect block (edits.json `players[key]["prospect"]`: growth tier
and potential); my pro is one with `"pro": true`. Both are made and changed on the Roster editor's card
(EditorController: `new_player(preset, extra)`, `open_person`), so Apply, Undo, the Save bar and every check are the
editor's; this controller lists them by draft year, sets the prospect block and says what the game will do with them.
Its list stands where the other team tabs have the team list (the page swaps it in), and it follows the editor like
the other team tabs (`follow_with`), so it reads the roster picked in Setup.

The game's own rules (lab round 44, docs/notes/lab-round-44.md): a new career drafts the players without NHL rights of
the CHL and European clubs, by birth date; it fits the potential into a band per growth tier; a top-tier prospect went
2nd overall, tier 5 and lower went undrafted. Be a NHL Pro lists NHL roster players, Be a CHL Pro the juniors; in the
patched game a junior without NHL rights crashes at the first game day (GAME_PATCH.md section 6), so my pro is best on
an NHL team.
"""
import os
import random
import threading

from .. import draftclass, gamepatch
from .. import layout as L
from ..editor import card as C
from ..editor import model
from ..leagues.pools import POOL_NAME
from ..roster import Roster

SLICE = 'prospects'
PRO = 'pro'
CAREERS = 'careers'                 # the running Be a Pro careers (app/career.py)
NOT_CLASSES = (PRO, CAREERS)
NO_ROSTER = "Pick a roster in Setup first."
# what each growth tier did in the lab's 2027 draft (round 44), in the player's words
TIER_HINTS = {1: "elite: went 2nd overall", 2: "top prospect: first round", 3: "first or second round",
              4: "later rounds", 5: "was not drafted", 6: "long shot", 7: "long shot"}
STATES = {'in': "in this roster", 'unsaved': "not saved yet: press Save to this roster",
          'waiting': "not in this roster yet", 'out': "left out"}
CLASS_NOTE = ("The game drafts the juniors and European players without NHL rights, by birth date: a player born by "
              "15 September {first} is in the {year} draft. Put a class player on a CHL or European club.")
PATCH_NOTE = ("Draft classes work in the patched game (32 teams, the year 2026): patch the game in the Game patch tab "
              "and update this roster.")
PRO_NOTE = ("Be a Pro lists players on an NHL roster (Be a NHL Pro) and juniors (Be a CHL Pro). The game works out "
            "his overall from his ratings and type, so it shows another number than ours.")
# where Be a Pro lists him (the Overall filter opens on 70-79; 88 in every rating made him 87 (lab round 46), 98 made
# him 99, listed under 90-99 (round 47))
PRO_WHERE = ("In the game: Career > Live the Life > New Pro > Be a {kind} Pro, {team}, his position, then step "
             "Overall (it starts on 70-79) until he shows.")
PRO_STARTS = ("The game's other New Pro starts (Pick a Team, NHL Entry Draft, Start in Junior, Legend) make a new player "
              "in the game itself. Load Pro lists the careers you saved.")
PRO_OUT = "Be a Pro cannot pick him there: put him on an NHL team or a CHL club"
CAREERS_SPAN = "Your pro in a career you play"
CAREERS_NOTE = ("The careers you saved in Live the Life (Load Pro lists the same). Change your pro's name, his ratings "
                "or the experience points he has to spend in Player Growth, then press Save this career with RPCS3 "
                "closed.")
UNSAVED_NOTE = ("Not in the game yet: the game reads only what is saved. Press Save to this roster (with RPCS3 closed), "
                "then start the game.")
PRO_PATCH_WARN = ("In the patched game a junior without NHL rights cannot start a Be a CHL Pro career yet (it crashes at "
                  "the first game day). Put him on an NHL team.")
# the random maker's choices
MAKE_COUNTS = (16, 32, 48, 64)
STRENGTH_LABELS = {'weak': "Weak", 'normal': "Normal", 'strong': "Strong"}
# the leagues a made or imported class plays in (draftclass.HOME_LEAGUE's names) and their club slots
MAKE_LEAGUES = {'CHL': L.CHL, 'SHL': L.SHL, 'Liiga': L.LIIGA, 'Extraliga': L.EXTRALIGA, 'NL': L.NL, 'DEL': L.DEL,
                'Norway': L.NORWAY}
LEAGUE_KEY = {'OHL': 'CHL', 'QMJHL': 'CHL', 'WHL': 'CHL', 'National League': 'NL'}     # the roster's league names
CLASS_KINDS = ['Draft class (*.json)', 'All files (*.*)']
MAX_FILE_BYTES = 4 << 20
REPORT_LINES = 12               # skipped players named in the import report, then "and N more"
INV_POS = {v: k for k, v in model.POS_KEY.items()}


def birth_text(birth):
    return "%04d-%02d-%02d" % tuple(birth) if birth else ''


def count_text(n):
    return "1 player" if n == 1 else f"{n} players"


class ProspectsController:
    def __init__(self, host, editor, careers=None):
        self.host, self.editor, self.careers = host, editor, careers     # careers: app/career.CareerController
        self.lock = threading.RLock()
        self.shown = False
        self.view = None                # a draft year (int) or PRO; None: the first class
        self.maker = None               # the random maker's window: {'count', 'strength', 'seed'}
        self.report = None              # what an import did: {'title', 'lines': [{'text', 'tone'}]}
        follow = getattr(editor, 'follow_with', None)
        if follow is not None:
            follow('prospects', self)

    def changed(self):
        self.host.changed(SLICE)

    # --- following the editor -------------------------------------------------------------------------------------
    def follow(self, team):
        with self.lock:
            self.shown = True
        self._look()
        self.changed()

    def _look(self):
        """List the Be a Pro careers when they are in view (again only when the picked roster's game changed)."""
        if self.careers is not None and self.shown and self._view() == CAREERS:
            self.careers.look()

    def hide(self):
        with self.lock:
            self.shown = False

    def roster_changed(self):
        self.changed()

    # --- what is listed ------------------------------------------------------------------------------------------
    def _season(self):
        snap = self.editor.snap
        return snap.season_year if snap is not None else (self.editor.season or 2026)

    def _views(self):
        return list(draftclass.class_years(self._season())) + [PRO] + ([CAREERS] if self.careers is not None else [])

    def _view(self):
        views = self._views()
        return self.view if self.view in views else views[0]

    def _birth(self, key, e):
        """(year, month, day) of a class player: as the shown roster has him, else as his edit says."""
        p = self._player(key)
        if p is not None:
            return tuple(p.birth)
        try:
            return tuple(int(x) for x in (e.get('set') or {}).get('birth'))
        except (TypeError, ValueError):
            return None

    def _player(self, key):
        snap = self.editor.snap
        if snap is None:
            return None
        now = {old: new for new, old in C.renamed(self.editor.edits).items()}
        return snap.by_who.get(now.get(key, key))

    def _saved(self, key):
        """The player of the edit kept under `key` in the roster as read from its file (without this visit's edits),
        or None: what the game has."""
        raw = self.editor.raw
        if raw is None:
            return None
        now = {old: new for new, old in C.renamed(self.editor.edits).items()}
        return raw.by_who.get(now.get(key, key)) or raw.by_who.get(key)

    def _clubs(self, key, e):
        p = self._player(key)
        if p is not None:
            return p.clubs
        team = e.get('team')
        return [team] if isinstance(team, int) else []

    def _state(self, key, e, year):
        """('in' | 'waiting' | 'out', why) of a class player in the shown roster."""
        clubs = self._clubs(key, e)
        if year not in draftclass.class_years(self._season()):
            return 'out', f"not eligible for the drafts {self._season() + 1}-{self._season() + draftclass.CLASSES_AHEAD}"
        if not clubs or not all(draftclass.is_draft_club(t) for t in clubs):
            return 'out', "not on a junior or European club (the game drafts only from those)"
        if self._player(key) is None:
            return 'waiting', "goes into the roster when you save it (or with the next update)"
        if self._saved(key) is None:
            return 'unsaved', ""
        return 'in', ""

    def _rows(self, year):
        """The class of draft `year`, as a draft board: the best tier and potential first."""
        snap, eds = self.editor.snap, self.editor.edits
        out = []
        for key, e in sorted(draftclass.prospects_of(eds).items()):
            birth = self._birth(key, e)
            if birth is None or draftclass.eligible_year(birth) != year:
                continue
            tier, potential = draftclass.fitted(e['prospect'])
            p = self._player(key)
            clubs = self._clubs(key, e)
            state, why = self._state(key, e, year)
            out.append({'key': key, 'name': p.name if p else e.get('label') or key,
                        'pos': p.pos if p else (e.get('set') or {}).get('pos') or 'C',
                        'born': birth_text(birth), 'club': ", ".join(snap.team_name(t) for t in clubs) if snap else '',
                        'tier': tier, 'stars': draftclass.stars(tier), 'potential': potential,
                        'ovr': (p.ovr if p else e.get('ovr')) or '', 'state': state, 'note': why or STATES[state]})
        return sorted(out, key=lambda r: (r['tier'], -r['potential'], r['name']))

    def _pro_rows(self):
        snap, out = self.editor.snap, []
        for key, e in sorted(self.editor.edits.items()):
            if not e.get('pro'):
                continue
            p = self._player(key)
            clubs = self._clubs(key, e)
            birth = self._birth(key, e)
            state, why = self._pro_state(key, clubs)
            out.append({'key': key, 'name': p.name if p else e.get('label') or key,
                        'pos': p.pos if p else (e.get('set') or {}).get('pos') or 'C',
                        'born': birth_text(birth), 'club': ", ".join(snap.team_name(t) for t in clubs) if snap else '',
                        'tier': None, 'potential': None, 'ovr': (p.ovr if p else e.get('ovr')) or '',
                        'state': state, 'note': why or STATES[state]})
        return out

    def _pro_state(self, key, clubs):
        """('in' | 'unsaved' | 'waiting' | 'out', why) of my pro: in the roster's file, shown only, not there yet, or
        on a team Be a Pro does not offer."""
        if not any(self.editor.pro_team(t) for t in clubs):
            return 'out', PRO_OUT
        if self._player(key) is None:
            return 'waiting', ""
        return ('in', "") if self._saved(key) is not None else ('unsaved', "")

    def _pro_where(self, snap):
        """Where Be a Pro lists the pro in the shown roster, or None (not in it yet, or on a team it does not offer)."""
        for key, e in sorted(self.editor.edits.items()):
            p = self._saved(key)
            if not e.get('pro') or p is None:
                continue
            for team in p.clubs:
                kind = 'NHL' if team in L.NHL_PRIMARY else 'CHL' if team in L.CHL else None
                if kind:
                    return PRO_WHERE.format(kind=kind, team=snap.team_name(team))
        return None

    def _selected(self):
        """The edit key of the player on the editor's card, if he is one of this tab's."""
        ed = self.editor
        p = ed.player if ed.card_open else None
        if p is None:
            return None
        key = ed.edit_key(p)
        e = ed.edits.get(key) or {}
        return key if isinstance(e.get('prospect'), dict) or e.get('pro') else None

    # --- the calls -------------------------------------------------------------------------------------------------
    def show(self, view):
        """Show the class of draft year `view` (2027 ...) or my pro ('pro')."""
        with self.lock:
            try:
                view = view if view in NOT_CLASSES else int(view)
            except (TypeError, ValueError):
                return
            if view in self._views():
                self.view = view
        self._look()
        self.changed()

    def step(self, step):
        """Alt+Up / Alt+Down: the class before or after."""
        with self.lock:
            views = self._views()
            at = views.index(self._view())
            self.view = views[max(0, min(len(views) - 1, at + (1 if step > 0 else -1)))]
        self._look()
        self.changed()

    def pick(self, key, typed=None):
        self.editor.open_person(key, typed)
        self.changed()

    def add(self):
        """A new class player for the class shown (or my pro): the editor's card, filled for a prospect."""
        with self.lock:
            view, season = self._view(), self._season()
            snap = self.editor.snap
        if snap is None or view == CAREERS:
            return
        if view == PRO:
            if any(e.get('pro') for e in self.editor.edits.values()):
                self.editor.set_status("You have a pro already: change him, or take him out first.", 'warn')
                return
            team = min(L.NHL_PRIMARY)
            self.editor.new_player(
                preset={'title': "My pro", 'note': PRO_NOTE,
                        'values': {'birth': f"{season - 19}-05-01", 'team': team, 'ovr': '60', 'country': 'CAN'}},
                extra={'pro': True})
        else:
            team = self.editor.team if draftclass.is_draft_club(self.editor.team) else min(L.OHL)
            self.editor.new_player(
                preset={'title': f"New prospect for the {view} draft",
                        'note': CLASS_NOTE.format(first=view - 18, year=view),
                        'values': {'birth': f"{view - 18}-03-01", 'team': team, 'ovr': '50'}},
                extra={'prospect': {'tier': 3}})
        self.changed()

    def _new_block(self):
        """The prospect block a new player on the card gets on Apply (None: the card is not a new class player)."""
        ed = self.editor
        extra = ed.new_extra if ed.card_open and ed.player is None else None
        return extra.get('prospect') if extra and isinstance(extra.get('prospect'), dict) else None

    def set(self, field, value):
        """Change the growth tier ('tier') or the potential ('potential') of the class player on the card (a new one
        gets it on Apply)."""
        ed = self.editor
        with ed.lock:
            key = self._selected()
            e = ed.edits.get(key) if key else None
            new = self._new_block() if e is None else None
            if new is None and (e is None or not isinstance(e.get('prospect'), dict)):
                return
            try:
                value = int(value)
            except (TypeError, ValueError):
                return
            block = dict(new if new is not None else e['prospect'])
            if field == 'tier':
                block['tier'] = min(max(value, 1), max(draftclass.TIER_BANDS))
                lo, hi = draftclass.TIER_BANDS[block['tier']]
                if block.get('potential') is not None and not lo <= block['potential'] <= hi:
                    block.pop('potential')          # the new band's top
            elif field == 'potential':
                lo, hi = draftclass.TIER_BANDS[draftclass.fitted(block)[0]]
                block['potential'] = min(max(value, lo), hi)
            else:
                return
            if new is not None:
                ed.new_extra = dict(ed.new_extra, prospect=block)
                ed.changed()
                self.changed()
                return
            if block == e['prospect']:
                return
            ed.edits[key] = dict(e, prospect=block)
            ed.session.add(key)
            ed._edits_saved()
            ed.refresh()
            ed.changed()
        self.changed()

    def remove(self, key):
        """Take a class player or my pro out: one this visit made is undone (he leaves the roster); one in the roster
        already stays a player, as a free agent outside the drafts."""
        ed = self.editor
        with ed.lock:
            e = ed.edits.get(key)
            if e is None or ed.busy:
                return
            p = self._player(key)
            if key in ed.session and p is not None and not self._in_raw(p) or p is None:
                del ed.edits[key]
                ed.session.discard(key)
                if ed.player is not None and p is not None and ed.player.who == p.who:
                    ed.player, ed.card_open = None, False
                ed.set_status(f"{e.get('label') or key} is out of My edits.")
            else:
                ed.edits[key] = {k: v for k, v in e.items() if k not in ('prospect', 'pro')}
                ed.edits[key]['team'] = model.FREE_AGENTS
                ed.session.add(key)
                ed.set_status(f"{e.get('label') or key} is a free agent now (outside the drafts). Save to keep it.")
            ed._edits_saved()
            ed.refresh()
            ed.changed()
        self.changed()

    def _in_raw(self, p):
        raw = self.editor.raw
        return raw is not None and p.who in raw.by_who

    # --- the random maker and class files ----------------------------------------------------------------------------
    def _draft_clubs(self, snap):
        """{league: [club slots]} a made or imported class can play on: the shown roster's CHL and European clubs with
        players and room (no prospect pool)."""
        out = {}
        for league, slots in MAKE_LEAGUES.items():
            clubs = [t for t in sorted(slots) if 0 < len(snap.roster(t)) <= L.MAX_PER_TEAM - 4
                     and not POOL_NAME.search(snap.team_name(t))]
            if clubs:
                out[league] = clubs
        return out

    def _no_room(self, cards):
        """A plain sentence when the shown roster has too few spare records for these players (None: they fit)."""
        room = self._room()
        if room is None:
            return None
        looks, need = dict(room['looks']), {'S': 0, 'G': 0}
        for c in cards:                         # a look takes a Create Player record while they last (records_needed)
            kind = 'G' if c.get('pos') == 'G' else 'S'
            if c.get('look') and looks[kind] > 0:
                looks[kind] -= 1
            else:
                need[kind] += 1
        if need['S'] <= room['spare']['S'] and need['G'] <= room['spare']['G']:
            return None
        goalies = sum(1 for c in cards if c.get('pos') == 'G')
        return (f"This roster has room for {room['skaters']} more skaters and {room['goalies']} more goalies: "
                f"that is too few for {len(cards) - goalies} skaters and {goalies} goalies.")

    def _add_players(self, entries):
        """Put new class players into My edits (with the editor's lock held) and rebuild the roster: `entries`
        [(card values as typed, prospect block, club slot)]. Returns ([names added], [(name, why) skipped])."""
        ed, snap = self.editor, self.editor.snap
        choices, added, skipped = ed.choices(), [], []
        known = {draftclass.plain(p.name) for p in snap.by_who.values()} | {
            draftclass.plain(e.get('label') or '') for e in ed.edits.values()}
        for card, block, team in entries:
            name = f"{card.get('first', '')} {card.get('last', '')}".strip() or "A player without a name"
            if draftclass.plain(name) in known:
                skipped.append((name, "a player of that name is in the roster or in My edits already"))
                continue
            values = dict(card, team=team, num=card.get('num') or '1')
            labels = model.GOALIE_ATTRIBUTES if values.get('pos') == 'G' else model.SKATER_ATTRIBUTES
            checked, problem = C.read(values, labels, True, choices, None, snap.heads)
            if problem:
                skipped.append((name, problem))
                continue
            who, edit = C.new_player(checked)
            if not card.get('num'):
                edit['set'].pop('num', None)       # he gets a number nobody on his club wears (edits._move)
            tier, potential = draftclass.fitted(block or {})
            edit['prospect'] = {'tier': tier, 'potential': potential}
            ed.edits[who] = edit
            ed.session.add(who)
            known.add(draftclass.plain(name))
            added.append(name)
        if added:
            ed._edits_saved()
            ed.refresh()
            ed.changed()
        return added, skipped

    def make_open(self):
        """The random maker's window, for the class shown."""
        with self.lock:
            if self._view() in NOT_CLASSES or self.editor.snap is None:
                return
            self.maker = {'count': 32, 'strength': 'normal', 'seed': random.randint(1, 9999)}
            self.report = None
        self.changed()

    def make_set(self, field, value):
        """Change the maker's 'count', 'strength' or 'seed'."""
        with self.lock:
            if self.maker is None:
                return
            try:
                if field == 'count':
                    self.maker['count'] = min(max(int(value), 1), max(MAKE_COUNTS))
                elif field == 'seed':
                    self.maker['seed'] = min(max(int(value), 0), 99999)
                elif field == 'strength' and value in draftclass.STRENGTHS:
                    self.maker['strength'] = value
                else:
                    return
            except (TypeError, ValueError):
                return
        self.changed()

    def close(self):
        """Close the maker's window or the import report."""
        with self.lock:
            self.maker = self.report = None
        self.changed()

    def make(self):
        """Make the class the maker's window describes and put it into My edits (made-up names: first and last names
        of different real players of the same country)."""
        ed = self.editor
        with self.lock:
            m, year = self.maker, self._view()
        if m is None or year in NOT_CLASSES:
            return
        with ed.lock:
            snap = ed.snap
            if snap is None or ed.busy:
                return
            # names of players outside the NHL only (a famous surname would make the player look like a real one's
            # relative); never a full name the roster or My edits has
            names = [(p.first, p.last, p.country) for p in snap.by_who.values()
                     if not any(t in L.NHL_PRIMARY or t in snap.copies for t in p.teams)]
            taken = [p.name for p in snap.by_who.values()] + [e.get('label') or '' for e in ed.edits.values()]
            try:
                made = draftclass.make(year, m['count'], names, self._draft_clubs(snap), m['seed'], m['strength'], taken)
            except ValueError as e:
                ed.set_status(str(e), 'bad')
                return
            looks = ed.looks_left()
            for pl in made:                     # created looks while the game's Create Player records last
                kind = 'G' if pl['card']['pos'] == 'G' else 'S'
                if looks[kind] > 0:
                    looks[kind] -= 1
                else:
                    pl['card'].pop('look', None)
            short = self._no_room([pl['card'] for pl in made])
            if short:
                ed.set_status(short + " Make a smaller class.", 'bad')
                return
            added, skipped = self._add_players([(pl['card'], pl['prospect'], pl['club']) for pl in made])
            note = (f"Made {count_text(len(added))} for the {year} draft ({STRENGTH_LABELS[m['strength']].lower()} "
                    f"class, number {m['seed']}). Save to write them into the roster."
                    + (f" {len(skipped)} could not be made: {skipped[0][1]}" if skipped else ""), 'good' if added else 'bad')
            if added:
                ed.next_note = note             # said when the roster is rebuilt with them
            else:
                ed.set_status(*note)
        with self.lock:
            self.maker = None
        self.changed()

    def _card_of(self, key, e):
        """A class player's card values as typed, for a class file: from his edit, or as the roster has one who was
        not made new."""
        if e.get('new'):
            s = e.get('set') or {}
            card = {k: str(s[k]) for k in ('first', 'last', 'num', 'shoots', 'country', 'style', 'head', 'skin', 'eyes')
                    if s.get(k) is not None}
            card['pos'] = INV_POS.get(s.get('pos'), 'C')
            if s.get('birth'):
                card['birth'] = birth_text(s['birth'])
            if s.get('height_in'):
                card['height'] = str(C.cm(s['height_in']))
            if s.get('weight_lb'):
                card['weight'] = str(C.kg(s['weight_lb']))
            card['ovr'] = str(e.get('ovr') or 50)
            card['ratings'] = {a: str(v) for a, v in (e.get('ratings') or {}).items()}
            p = self._player(key)
            look = p.look if p is not None and p.look else e.get('look')
            if look:
                card['look'] = dict(look)
            return card
        p = self._player(key)
        if p is None:
            return None
        return {'first': p.first, 'last': p.last, 'num': str(p.num), 'pos': p.pos, 'shoots': p.shoots,
                'birth': birth_text(p.birth), 'country': p.country, 'height': str(C.cm(p.height_in)),
                'weight': str(C.kg(p.weight_lb)), 'ovr': str(p.ovr or 50),
                **({'style': str(p.style)} if p.style is not None else {}),
                **{k: str(v) for k, v in p.face.items() if v is not None and not p.look},
                **({'look': dict(p.look)} if p.look else {}),
                'ratings': {a: str(v) for a, v in p.ratings.items() if 40 <= v <= 99}}

    def _file_players(self, year):
        snap, out = self.editor.snap, []
        for key, e in sorted(draftclass.prospects_of(self.editor.edits).items()):
            birth = self._birth(key, e)
            if birth is None or draftclass.eligible_year(birth) != year:
                continue
            card = self._card_of(key, e)
            if card is None:
                continue
            clubs = self._clubs(key, e)
            club = ({'league': snap.team_league.get(clubs[0], ''), 'name': snap.team_name(clubs[0])}
                    if clubs and clubs[0] in snap.team_league else None)
            out.append({'card': card, 'prospect': e['prospect'], 'club': club})
        return out

    def export_class(self):
        """Save the class shown as a class file (the players as their cards have them; no pictures)."""
        ed = self.editor
        with self.lock:
            year = self._view()
        if year in NOT_CLASSES or ed.snap is None:
            return
        with ed.lock:
            players = self._file_players(year)
        if not players:
            ed.set_status("This class has nobody to save yet.", 'warn')
            return
        path = self.host.ask_save("Save the draft class", f"draft_class_{year}.json", CLASS_KINDS)
        if not path:
            return
        if not path.lower().endswith('.json'):
            path += '.json'
        try:
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(draftclass.class_file(f"{year} draft class", year, players))
        except OSError as e:
            ed.set_status(f"The class could not be saved: {e.strerror or e}.", 'bad')
            return
        ed.set_status(f"Saved the {year} class ({count_text(len(players))}) to {os.path.basename(path)}. "
                      "Import puts it into another roster.", 'good')

    def import_class(self):
        """Put the players of a class file the player picks into the class shown."""
        with self.lock:
            year = self._view()
        if year in NOT_CLASSES or self.editor.snap is None or self.editor.busy:
            return
        path = self.host.ask_open("Pick a draft class file", CLASS_KINDS)
        if not path:
            return
        try:
            if os.path.getsize(path) > MAX_FILE_BYTES:
                raise ValueError
            with open(path, encoding='utf-8-sig') as f:
                text = f.read()
        except (OSError, UnicodeDecodeError, ValueError):
            text = ''
        self.import_text(text, os.path.basename(path))

    def import_text(self, text, source="the file"):
        """Put the players of a class file's text into the class shown: birth dates moved to its draft, clubs found by
        league and name (else a club of the same league, else a junior club), names already there skipped. The window
        then lists what happened."""
        ed = self.editor
        with self.lock:
            year = self._view()
        try:
            name, file_year, players = draftclass.read_class(text)
        except ValueError as e:
            self._report(f"Import {source}", [(str(e), 'bad')])
            return
        with ed.lock:
            snap = ed.snap
            if snap is None or year in NOT_CLASSES or ed.busy:
                return
            clubs = self._draft_clubs(snap)
            everyone = sorted(c for cs in clubs.values() for c in cs)
            found = {(snap.team_league.get(t), snap.team_name(t)): t for t in everyone}
            entries, moved, spread = [], {}, {}
            for pl in players:
                card = dict(pl['card'], birth=draftclass.shift_birth(pl['card'].get('birth', ''), year - file_year))
                club = pl['club'] or {}
                team = found.get((club.get('league'), club.get('name')))
                if team is None:
                    home = clubs.get(LEAGUE_KEY.get(club.get('league'), club.get('league'))) or clubs.get('CHL') or everyone
                    if not home:
                        self._report(f"Import {source}", [("This roster has no junior or European club to put the class "
                                                           "on.", 'bad')])
                        return
                    team = draftclass.spread(random.Random(f"{name}|{len(entries)}"), home, spread)
                    moved[f"{card.get('first', '')} {card.get('last', '')}".strip()] = snap.team_name(team)
                entries.append((card, pl['prospect'], team))
            short = self._no_room([c for c, _, _ in entries])
            if short:
                self._report(f"Import {source}", [(short, 'bad')])
                return
            added, skipped = self._add_players(entries)
        lines = [(f"{count_text(len(added))} added to the {year} draft from \"{name}\"."
                  + (" Save to write them into the roster." if added else ""), 'good' if added else 'warn')]
        if added and year != file_year:
            lines.append((f"The file was made for the {file_year} draft: their birth dates moved "
                          f"{abs(year - file_year)} year{'s' if abs(year - file_year) > 1 else ''} "
                          f"{'later' if year > file_year else 'earlier'}.", 'info'))
        fixed = [f"{who} ({club})" for who, club in moved.items() if who in added]
        if fixed:
            lines.append((f"{count_text(len(fixed))} on another club (theirs is not in this roster): "
                          + ", ".join(fixed[:REPORT_LINES]) + (f" and {len(fixed) - REPORT_LINES} more" if len(fixed) >
                                                               REPORT_LINES else "") + ".", 'info'))
        for who, why in skipped[:REPORT_LINES]:
            lines.append((f"Skipped {who}: {why[0].lower() + why[1:] if why else why}", 'warn'))
        if len(skipped) > REPORT_LINES:
            lines.append((f"... and {len(skipped) - REPORT_LINES} more skipped.", 'warn'))
        self._report(f"Import {source}", lines)

    def _report(self, title, lines):
        with self.lock:
            self.maker = None
            self.report = {'title': title, 'lines': [{'text': t, 'tone': tone} for t, tone in lines]}
        self.changed()

    # --- what the page shows ---------------------------------------------------------------------------------------
    def _room(self):
        """How many more new players fit the shown roster (the editor's build), or None: its spare player records plus
        the game's Create Player records still free for a created look (editor.looks_left)."""
        view = self.editor.view
        b = getattr(view[0], 'builder', None) if view else None
        donors = getattr(b, 'donors', None)
        if donors is None:
            return None
        spare, looks = {'S': donors.left('S'), 'G': donors.left('G')}, self.editor.looks_left()
        return {'skaters': spare['S'] + looks['S'], 'goalies': spare['G'] + looks['G'], 'spare': spare, 'looks': looks,
                'text': f"With a created look: {looks['S']} skaters and {looks['G']} goalies (the game's Create Player "
                        f"places; a few stay free for the game itself). Without one: {spare['S']} skaters and "
                        f"{spare['G']} goalies (spare player records; an update with every league on uses most of them)."}

    def snapshot(self):
        ed = self.editor
        with ed.lock:
            snap = ed.snap
            if snap is None:
                return {'loaded': False, 'busy': ed.busy, 'why': ed.status[0] if ed.busy else NO_ROSTER,
                        'views': [], 'view': None, 'rows': []}
            view = self._view()
            views = []
            for v in self._views():
                if v == CAREERS:
                    saves = self.careers.saves
                    views.append({'value': v, 'label': "Be a Pro careers", 'count': '' if saves is None else len(saves)})
                    continue
                n = len(self._pro_rows()) if v == PRO else len(self._rows(v))
                views.append({'value': v, 'label': "My pro" if v == PRO else f"{v} draft", 'count': n})
            if view == CAREERS:
                return {'loaded': True, 'busy': ed.busy, 'why': None, 'views': views, 'view': view,
                        'title': "Be a Pro careers", 'span': CAREERS_SPAN, 'note': CAREERS_NOTE, 'warn': None,
                        'unsaved': None, 'rows': [], 'selected': None, 'prospect': None, 'tiers': [],
                        'room': self._room(), 'can_add': False, 'maker': None, 'report': self.report}
            rows = self._pro_rows() if view == PRO else self._rows(view)
            selected = self._selected()
            block, source = None, None
            if selected and isinstance(ed.edits[selected].get('prospect'), dict):
                source = ed.edits[selected]['prospect']
            elif not selected:
                source = self._new_block()
            if source is not None:
                tier, potential = draftclass.fitted(source)
                lo, hi = draftclass.TIER_BANDS[tier]
                block = {'key': selected, 'tier': tier, 'stars': draftclass.stars(tier), 'potential': potential,
                         'lo': lo, 'hi': hi, 'hint': TIER_HINTS[tier]}
            patched = gamepatch.is_patch_roster(Roster(ed.raw_bytes)) if ed.raw_bytes else False
            if view == PRO:
                title, note = "My pro", " ".join(filter(None, (PRO_NOTE, self._pro_where(snap), PRO_STARTS,
                                                                PRO_PATCH_WARN if patched else None)))
                span = "Your own player, to pick in Be a Pro"
            else:
                title, note = f"{view} draft class", CLASS_NOTE.format(first=view - 18, year=view)
                span = f"Born 16 September {view - 19} to 15 September {view - 18}"
            return {
                'loaded': True, 'busy': ed.busy, 'why': None,
                'views': views, 'view': view, 'title': title, 'span': span, 'note': note,
                'warn': None if patched or view == PRO else PATCH_NOTE,
                'unsaved': UNSAVED_NOTE if any(r['state'] in ('unsaved', 'waiting') for r in rows) else None,
                'rows': rows, 'selected': selected, 'prospect': block,
                'tiers': [{'value': t, 'label': draftclass.stars(t), 'band': f"{lo}" if lo == hi else f"{lo}-{hi}",
                           'hint': TIER_HINTS[t]} for t, (lo, hi) in sorted(draftclass.TIER_BANDS.items())],
                'room': self._room(),
                'can_add': not ed.busy and (view != PRO or not any(e.get('pro') for e in ed.edits.values())),
                'maker': self._maker_view(view),
                'report': self.report,
            }

    def _maker_view(self, year):
        m = self.maker
        if m is None or year in NOT_CLASSES:
            return None
        tiers = draftclass.tiers_for(m['count'], m['strength'])
        return dict(m, year=year, counts=list(MAKE_COUNTS),
                    strengths=[{'value': k, 'label': v} for k, v in STRENGTH_LABELS.items()],
                    split=[{'tier': t, 'stars': draftclass.stars(t), 'count': tiers.count(t)}
                           for t in sorted(draftclass.TIER_BANDS)])
