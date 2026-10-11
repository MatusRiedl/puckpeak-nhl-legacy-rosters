"""The Roster editor tab without a window toolkit: what the page shows, and what its buttons do.

It shows the roster save picked on the Update tab as it is (the game's own roster too), plus the edits made
in this visit (`session`). The edits are kept on this PC (edits.py) and applied to every later update as
well, but earlier ones are not shown on top of a roster: they are in it once it was saved. Saving writes
what is shown after the same safety checks as an update, into the roster itself (a backup copy first,
savedata.update_in_place) or as a new roster, as the Update tab's choice says.

The page keeps what is typed on the card and sends it along with Apply, Save and a pick of another player
(`card`: see editor/card.py); a card that was typed on but not applied is applied first, as before. Slow work
(reading, rebuilding, saving, pictures) runs in a worker thread; the slices `editor` and `picture` say what
to show (the picture is a slice of its own, so the card's picture is not sent again with every change).
"""
import os
import threading

from .. import datasource, edits, pipeline, ratings, savedata
from .. import layout as L
from ..editor import card as C
from ..editor import model
from . import dataurl, jobs, settings as S

SLICE, PICTURE = 'editor', 'picture'
PORTRAIT = (512, 256)
NO_ROSTER = "Pick RPCS3 and a roster on the Update tab first."
COUNTRIES = sorted(L.NAT_CODE)


class EditorController:
    def __init__(self, host, update):
        self.host, self.update = host, update
        self.lock = threading.RLock()
        update.editor = self
        self.uniforms = None            # the Jerseys and ice controller (app/uniforms.py), once there is one
        self.equipment = None           # the Equipment controller (app/equipment.py)
        self.edits = edits.load()
        self.teams = edits.load_teams()
        pack = update.pack or {}
        self.offset = ratings.overall_offset(pack.get('ea_ratings') or []) if pack else None
        self.season = pack.get('season')
        self.pending_photo = None       # a picture chosen for the player on the card, not applied yet
        self.source = None              # (savedata folder, roster folder, file stamp) the view was made from
        self.slot = None                # that roster (savedata.Slot or DiscSlot)
        self.raw = None                 # Snapshot of the save as it is
        self.raw_source = None
        self.raw_bytes = None           # its SYS-DATA, as read (an update in place checks it is still that)
        self.view = None                # (BuildResult, Snapshot): the roster with this visit's edits
        self.session = set()            # keys (edits.py) of the player edits made since the roster was opened
        self.session_teams = set()      # slots of the team edits made since then
        self.pictures = None            # editor.pictures.Pictures of the shown roster's game
        self.picture = None             # {'token', 'url', 'caption'} of the card's picture
        self.picture_token = 0          # the picture on the card belongs to the latest request only
        self.after_busy = None          # what to do once the running job is finished
        self.busy = False
        self.league = None
        self.team = None
        self.player = None              # model.Player on the card
        self.card_open = False          # the card shows a player (or a new one, with player None)
        self.card_key = 0               # changes whenever the card is filled again (the page drops what was typed)
        self.new_who = None             # the player just added: the card shows him once the roster is rebuilt
        self.found = None               # the players found by a search (None: the team's players show)
        self.query = ''
        self.rows, self.row_players = [], {}
        self.name = savedata.default_name() + " edited"
        self.name_touched = False
        self.status = (NO_ROSTER, 'info')
        self.modal = None               # the Team or My edits window: dict, or None

    # --- helpers ------------------------------------------------------------------------------------
    def changed(self):
        self.host.changed(SLICE)

    def set_status(self, text, tone='info'):
        self.status = (text, tone)
        self.changed()

    @property
    def snap(self):
        return self.view[1] if self.view else None

    def edited_keys(self):
        """Person keys the shown roster has for players edited in this visit (a renamed player has a new key)."""
        return set(self.session) | set(C.renamed(self.edits, self.session))

    def edit_key(self, p):
        """The key an edit of `p` is stored under: his original name if he was renamed before."""
        return p.who if p.who in self.edits else C.renamed(self.edits).get(p.who, p.who)

    def choices(self):
        """Team choices of the card: slot -> 'NHL · Boston Bruins' (and 'FA' -> Free agents)."""
        snap = self.snap
        out = {model.FREE_AGENTS: "Free agents"}
        if snap is not None:
            for t in range(len(snap.team_names)):
                if t in L.MIRROR_OF or not snap.team_names[t].strip():
                    continue
                out[t] = f"{snap.team_league[t]} · {snap.team_names[t]}"
        return out

    def _edits_saved(self, players=True):
        edits.save(self.edits) if players else edits.save(teams=self.teams)
        self.update.changed()           # the Update tab's My edits row

    # --- loading ------------------------------------------------------------------------------------
    def opened(self):
        """The tab came into view: (re)load if the chosen roster changed."""
        with self.lock:
            upd = self.update
            slot = upd.selected_slot()
            if slot is None or upd.rpcs3 is None:
                self.slot = None
                if not self.busy:
                    self.view, self.source = None, None
                    self.set_status(NO_ROSTER)
                return
            source = (upd.rpcs3.savedata, slot.folder, self._stamp(slot))
            self.slot = slot
            if source != self.source:       # another roster, or the file changed (an update, the game, a save here)
                self.source, self.view, self.pictures = source, None, None
                self.session, self.session_teams = set(), set()
                self.name_touched = False
                self.player, self.card_open, self.found, self.query = None, False, None, ''
                self.pending_photo = None
                self._clear_picture()
                self.load()
            self._sync_name()
            self.changed()

    @staticmethod
    def _stamp(slot):
        """Size and time of a roster save's file, so a changed file is read again (None for the game's own roster)."""
        try:
            st = os.stat(slot.sys_data)
            return st.st_size, st.st_mtime_ns
        except (OSError, TypeError, AttributeError):
            return None

    def _sync_name(self):
        if not self.name_touched and self.slot is not None:
            self.name = self.slot.name if self.update.in_place(self.slot) else savedata.default_name() + " edited"

    def _work(self, text, job, done):
        """Run `job()` in a worker thread; `done(result)` afterwards (under the lock)."""
        if self.busy:
            return
        self.busy = True
        self.set_status(text)
        self.update.changed()           # the Update tab waits for the editor before it touches a roster

        def finished(result):
            with self.lock:
                self.busy = False
                done(result)
                then, self.after_busy = self.after_busy, None
                self.changed()
            self.update.changed()
            if then:
                then()

        def failed(message):
            with self.lock:
                self.busy = False
                self.after_busy = None
                self.set_status(f"That did not work: {message}", 'bad')
            self.update.changed()
        jobs.run(job, finished, failed)

    def _with_edits(self, raw_bytes):
        """The roster with the edits made since it was opened (the earlier ones are in it already)."""
        mine = {k: v for k, v in self.edits.items() if k in self.session}
        teams = {k: v for k, v in self.teams.items() if k in self.session_teams}
        return model.apply_edits(raw_bytes, mine, teams, self.season)

    def load(self):
        slot, source = self.slot, self.source

        def job():
            raw = savedata.read_roster(slot)
            return raw, self._with_edits(raw)
        self._work("Reading the roster...", job, lambda r: self._loaded(source, *r))

    def _loaded(self, source, raw, built):
        if source != self.source:           # another roster was picked meanwhile: read that one
            self.after_busy = self.load if self.source else None
            return
        if self.raw is None or self.raw_source != self.source:
            self.raw = model.Snapshot(raw, self.offset, self.season)
            self.raw_source = self.source
            self.raw_bytes = raw
        self.view = (built, model.Snapshot(built.data, self.offset, self.season))
        self.show()

    def refresh(self):
        """After an edit: rebuild the shown roster with the edits."""
        if self.busy:
            self.after_busy = self.load
            return
        self.load()

    # --- showing ------------------------------------------------------------------------------------
    def show(self):
        snap = self.snap
        if snap is None:
            return
        leagues = snap.leagues()
        if self.league not in leagues:
            self.league = leagues[0]
        built = self.view[0]
        if built.problems:
            more = f" (and {len(built.problems) - 1} more)" if len(built.problems) > 1 else ""
            self.set_status(f"Not playable yet: {built.problems[0]}{more}", 'bad')
        else:
            self.set_status("Showing the roster as it is" + (f", with your {len(self.session)} edits not saved yet"
                                                            if self.session or self.session_teams else "")
                            + ". Pick a team, then a player.")
        self._show_teams()
        if self.new_who is not None and self.player is None and self.card_open:
            p = snap.by_who.get(self.new_who)       # the player just added: show him as the roster has him
            if p is not None:
                self.player = p
                self._fill_card(p)
            self.new_who = None
        elif self.player is not None:               # the same player as this view has him (team, rating, picture)
            p = snap.by_who.get(self.player.who)
            if p is not None:
                self.player = p
                self._fill_card(p)

    def _show_teams(self):
        teams = self.snap.teams_in(self.league)
        if self.team not in teams:
            self.team = teams[0] if teams else None
        if self.found is not None:
            self.found = self.snap.search(self.query)
            self._show_players(self.found)
        else:
            self._show_players(self.snap.roster(self.team) if self.team is not None else [], self.team)

    def _show_players(self, players, team=None):
        snap = self.snap
        renamed = C.renamed(self.edits, self.session)
        diff = model.compare(self.raw, snap, team, renamed) if team is not None and self.raw else \
            {'joined': {}, 'left': [], 'changed': {}}
        edited = self.edited_keys()
        rows = []
        for p in players:
            tag, note = '', ''
            if p.who in diff['joined']:
                tag, note = ('new', "new to the game") if diff['joined'][p.who] == 'new to the game' else \
                    ('joined', f"from {diff['joined'][p.who]}")
            elif p.who in diff['changed']:
                tag, note = 'changed', C.change_note(self.raw.by_who.get(renamed.get(p.who, p.who)), p,
                                                     diff['changed'][p.who])
            if team is None:
                note = ", ".join(snap.team_name(t) for t in model.club(p.teams)) or "free agent"
            if p.who in edited:
                tag, note = 'edited', ("your edit; " + note).rstrip('; ')
            rows.append((p, tag, note))
        for p in diff['left']:
            now = snap.by_who.get(p.who)
            where = ", ".join(snap.team_name(t) for t in model.club(now.teams)) if now else ''
            rows.append((p, 'left', f"left: now {where or 'free agent'}" if now else "left"))
        self.row_players = {}
        self.rows = []
        for i, (p, tag, note) in enumerate(rows):
            ident = str(i)
            self.row_players[ident] = (p, tag)
            self.rows.append({'id': ident, 'who': p.who, 'pos': p.pos, 'num': p.num, 'name': p.name,
                              'age': p.age(snap.season_year), 'nat': p.country, 'ovr': p.ovr or '', 'note': note,
                              'tag': tag})

    def set_league(self, league):
        with self.lock:
            if self.snap is None or league not in self.snap.leagues():
                return
            self.league, self.found, self.query = league, None, ''
            self._show_teams()
            self.changed()

    def pick_team(self, team):
        with self.lock:
            team = C.team_value(team)
            if self.snap is None or team is None or team not in self.snap.teams_in(self.league):
                return
            self.team, self.found, self.query = team, None, ''
            self._show_players(self.snap.roster(team), team)
            self.changed()

    def search(self, text):
        with self.lock:
            if self.snap is None:
                return
            self.query = str(text or '').strip()
            if not self.query:              # an empty search: back to the team
                self.found = None
                self._show_teams()
                self.changed()
                return
            self.found = self.snap.search(self.query)
            self._show_players(self.found)
            self.set_status(f"{len(self.found)} players found" if self.found else "Nobody by that name in this roster.")

    # --- the player card ----------------------------------------------------------------------------
    def pick_player(self, ident, typed=None):
        with self.lock:
            if self.snap is None or ident not in self.row_players:
                return
            p, tag = self.row_players[ident]
            if tag == 'left':
                p = self.snap.by_who.get(p.who)
                if p is None:
                    return
            if self.card_open and self.player is not None and p.who == self.player.who:
                return                      # the same row again: the card is kept as typed
            lost = None
            if self.card_open and typed and self.apply(typed, quiet=True) == 'error':
                lost = f"The changes to {self.player.name if self.player else 'the new player'} were not taken: " \
                       + self.status[0]
            self.player, self.card_open, self.new_who = p, True, None
            self._fill_card(p)
            if lost:
                self.set_status(lost, 'bad')
            self.changed()

    def new_player(self):
        with self.lock:
            if self.snap is None:
                return
            self.player, self.card_open, self.new_who = None, True, None
            self._fill_card(None)
            self.changed()

    def _fill_card(self, p):
        self.pending_photo = None
        self.card_key += 1
        self._show_picture(p)

    def _card_view(self):
        if not self.card_open or self.snap is None:
            return None
        snap, p = self.snap, self.player
        goalie = p is not None and p.pos == 'G'
        labels = model.GOALIE_ATTRIBUTES if goalie else model.SKATER_ATTRIBUTES
        if p is None:
            team = self.team if isinstance(self.team, int) else model.FREE_AGENTS
            return {'key': self.card_key, 'new': True, 'title': "New player",
                    'note': "Takes a spare player record (the save has a fixed number). Give a name, birthdate, "
                            "team and overall; ratings are optional.",
                    'values': {'first': '', 'last': '', 'num': '', 'pos': 'C', 'shoots': 'L', 'birth': '',
                               'country': 'CAN', 'height': '', 'weight': '', 'team': team, 'ovr': '70',
                               'ratings': {}},
                    'labels': list(model.SKATER_ATTRIBUTES), 'goalie_labels': list(model.GOALIE_ATTRIBUTES),
                    'undo': False, 'photo_pending': bool(self.pending_photo)}
        key = self.edit_key(p)
        teams = model.club(p.teams)
        return {'key': self.card_key, 'new': False, 'title': p.name, 'who': p.who,
                'note': (", ".join(snap.team_name(t) for t in teams) or "Free agent")
                        + (f"   ·   OVR {p.ovr}" if p.ovr else "")
                        + ("   ·   you edited this player (not saved yet)" if key in self.session else ""),
                'values': {'first': p.first, 'last': p.last, 'num': str(p.num), 'pos': p.pos, 'shoots': p.shoots,
                           'birth': "%04d-%02d-%02d" % p.birth, 'country': p.country,
                           'height': str(C.cm(p.height_in)), 'weight': str(C.kg(p.weight_lb)),
                           'team': teams[0] if teams else model.FREE_AGENTS, 'ovr': str(p.ovr or ''),
                           'ratings': {a: str(p.ratings.get(a, '')) for a in labels}},
                'labels': list(labels), 'goalie_labels': list(model.GOALIE_ATTRIBUTES),
                'undo': key in self.session, 'photo_pending': bool(self.pending_photo),
                'equipment': p.equipment is not None}

    def apply(self, typed, quiet=False):
        """Take the card's values into the edits. Says what happened: 'applied' (the roster is being rebuilt),
        'nothing' (the card has no change) or 'error' (the status line says why). `quiet`: the player did not
        press Apply (Save or another player did); a card without a real change is left alone."""
        with self.lock:
            if self.snap is None or not self.card_open:
                return 'nothing'
            p = self.player
            goalie = (typed or {}).get('pos') == 'G' if p is None else p.pos == 'G'
            labels = model.GOALIE_ATTRIBUTES if goalie else model.SKATER_ATTRIBUTES
            values, problem = C.read(typed or {}, labels, p is None, self.choices(), p.ratings if p else None)
            if problem:
                self.set_status(problem, 'bad')
                return 'error'
            if p is None:                       # a new player
                who, edit = C.new_player(values, self.pending_photo)
                if self.snap.by_who.get(who):
                    self.set_status("That player is in the roster already: edit him instead.", 'bad')
                    return 'error'
                self.edits[who] = edit
                self.new_who = who
                key = who
            else:
                key = self.edit_key(p)
                edit, real = C.player_edit(p, values, self.edits.get(key), self.pending_photo)
                if not real and (quiet or ('team' not in edit and key not in self.edits)):
                    if not quiet:
                        self.set_status("Nothing changed.")
                    return 'nothing'
                self.edits[key] = edit
            self.session.add(key)
            self.pending_photo = None
            self._edits_saved()
            self.refresh()
            self.changed()
            return 'applied'

    def undo(self):
        with self.lock:
            p = self.player
            if p is None:
                return
            key = self.edit_key(p)
            if key in self.edits and key in self.session:      # an edit made before is in the roster: it stays there
                del self.edits[key]
                self.session.discard(key)
                self._edits_saved()
                self.refresh()

    # --- pictures -----------------------------------------------------------------------------------
    def pick_picture(self, title):
        """A picture file the player picks, kept in the program's folder: its 'file:' link, or None."""
        start = os.path.expanduser('~')
        path = self.host.ask_open(title, ['Pictures (*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif)'], start)
        if not path:
            return None
        try:
            from PIL import Image
            with Image.open(path) as img:
                img.load()
        except Exception:
            self.set_status("That file is not a picture this program can read (PNG, JPG, WebP).", 'bad')
            return None
        return edits.keep_picture(path)

    def choose_photo(self):
        with self.lock:
            if not self.card_open:
                return
        link = self.pick_picture("A photo for this player")
        if link:
            with self.lock:
                self.pending_photo = link
                self._show_picture(self.player)
                self.set_status("Press Apply to keep the photo. It shows in the game after an update with "
                                "\"Photos and logos\" on.", 'warn')

    def _pictures(self):
        """Pictures of the game the shown roster belongs to (None before RPCS3 is found)."""
        rpcs3 = self.update.rpcs3
        if rpcs3 is None or self.source is None:
            return None
        from ..editor.pictures import Pictures
        title_id = self.source[1][:9]
        if self.pictures is None or self.pictures.title_id != title_id or self.pictures.rpcs3 is not rpcs3:
            self.pictures = Pictures(rpcs3, title_id)
        return self.pictures

    def _clear_picture(self):
        self.picture_token += 1
        self.picture = {'token': self.picture_token, 'url': None, 'caption': '', 'loading': False}
        self.host.changed(PICTURE)

    def _show_picture(self, p):
        """The picture for player `p` (None: a new player), as the game shows it: his own if he has one, else
        what the game shows now. It is made in a worker thread; only the latest request is shown."""
        own = self.pending_photo or ((self.edits.get(self.edit_key(p)) or {}).get('photo') if p is not None else None)
        if p is None and not own:
            self._clear_picture()
            return
        self.picture_token += 1
        token = self.picture_token
        self.picture = {'token': token, 'url': (self.picture or {}).get('url'), 'caption': "Loading the picture...",
                        'loading': True}
        self.host.changed(PICTURE)
        try:
            pictures = self._pictures()
        except Exception:
            pictures = None

        def job():
            try:
                from ..editor.pictures import NO_GAME, Pictures
                if own:
                    pic, caption = Pictures.mine(own)
                elif pictures is None:
                    pic, caption = None, NO_GAME
                else:
                    pic, caption = pictures.current(p.artid, p.hasportrait)
                return dataurl.picture(pic, PORTRAIT), caption
            except Exception:
                return None, "The picture could not be read."

        def run():
            url, caption = job()
            with self.lock:
                if token != self.picture_token:     # the card shows someone else by now
                    return
                self.picture = {'token': token, 'url': url, 'caption': caption, 'loading': False}
            self.host.changed(PICTURE)
        threading.Thread(target=run, daemon=True).start()

    def picture_view(self):
        return self.picture

    # --- the Team window -----------------------------------------------------------------------------
    def team_open(self):
        with self.lock:
            if not isinstance(self.team, int) or self.snap is None:
                self.set_status("Pick a team first.", 'warn')
                return
            slot, snap = self.team, self.snap
            T = snap.R.T
            mine = dict(self.teams.get(str(slot)) or {})
            self.modal = {'kind': 'team', 'slot': slot, 'name': snap.team_name(slot),
                          'fields': {part: mine.get(part) or T.get(slot, field)
                                     for part, field in (('full', 'fullname'), ('city', 'shortname'),
                                                         ('abbr', 'abbrname'))},
                          'logo': None, 'logo_text': '', 'mine': bool(self.teams.get(str(slot)))}
            self._logo_link = mine.get('logo')
            self._team_logo()
            self.changed()

    def _team_logo(self):
        link, modal = self._logo_link, self.modal
        if not link or modal is None:
            return
        modal['logo_text'] = "Loading..."

        def run():
            try:
                from PIL import Image
                from ..art import images
                url, text = dataurl.picture(images.logo(Image.open(link[5:]), 't', (256, 256)), (192, 192)), ''
            except Exception:
                url, text = None, "(your logo)"
            with self.lock:
                if self.modal is modal:
                    modal['logo'], modal['logo_text'] = url, text
                    self.changed()
        threading.Thread(target=run, daemon=True).start()

    def team_choose_logo(self):
        with self.lock:
            if (self.modal or {}).get('kind') != 'team':
                return
        link = self.pick_picture("A logo for this team")
        if link:
            with self.lock:
                self._logo_link = link
                self._team_logo()
                self.changed()

    def team_apply(self, values):
        with self.lock:
            modal = self.modal
            if (modal or {}).get('kind') != 'team' or self.snap is None:
                return
            slot = modal['slot']
            T = self.snap.R.T
            mine = dict(self.teams.get(str(slot)) or {})
            for part, field in (('full', 'fullname'), ('city', 'shortname'), ('abbr', 'abbrname')):
                value = str((values or {}).get(part) or '').strip()
                if value and value != T.get(slot, field):
                    mine[part] = value
                else:
                    mine.pop(part, None)
            if self._logo_link:
                mine['logo'] = self._logo_link
            if mine:
                self.teams[str(slot)] = mine
                self.session_teams.add(str(slot))
            else:
                self.teams.pop(str(slot), None)
            self._edits_saved(players=False)
            self.modal = None
            self.refresh()
            self.changed()

    def team_undo(self):
        with self.lock:
            modal = self.modal
            if (modal or {}).get('kind') != 'team':
                return
            slot = str(modal['slot'])
            self.teams.pop(slot, None)
            self.session_teams.discard(slot)
            self._edits_saved(players=False)
            self.modal = None
            self.refresh()
            self.changed()

    def close_modal(self):
        with self.lock:
            self.modal = None
            self.changed()

    # --- My edits -------------------------------------------------------------------------------------
    def edits_open(self):
        with self.lock:
            self.modal = {'kind': 'edits'}
            self.changed()

    def _edits_view(self):
        items = []
        for slot, e in sorted(self.teams.items(), key=lambda kv: int(kv[0])):
            name = self.snap.team_name(int(slot)) if self.snap else f"team {slot}"
            items.append({'kind': 'team', 'key': slot, 'name': name, 'what': "team: " + ", ".join(sorted(e))})
        for who, e in sorted(self.edits.items(), key=lambda kv: kv[1].get('label', kv[0])):
            items.append({'kind': 'player', 'key': who, 'name': e.get('label', who),
                          'what': ", ".join(C.what_changed(e))})
        return items

    def edits_remove(self, kind, key):
        with self.lock:
            if kind == 'team':
                self.teams.pop(key, None)
                self.session_teams.discard(key)
                self._edits_saved(players=False)
            else:
                self.edits.pop(key, None)
                self.session.discard(key)
                self._edits_saved()
            if self.source:
                self.refresh()
            self.changed()

    # --- Jerseys and ice -----------------------------------------------------------------------------
    def uniforms_open(self):
        with self.lock:
            if not isinstance(self.team, int) or self.snap is None:
                self.set_status("Pick a team first.", 'warn')
                return
            if not 0 <= self.team < 32:
                self.set_status("Jerseys and the centre-ice logo can be changed for the 32 NHL teams.", 'warn')
                return
            team = self.team
        if self.uniforms is not None:
            self.uniforms.open(team)

    # --- saving ---------------------------------------------------------------------------------------
    def set_save_mode(self, mode):
        self.update.set_save_mode(mode)         # the same choice as on the Update tab
        with self.lock:
            self.name_touched = False
            self._sync_name()
            self.changed()

    def set_name(self, text):
        with self.lock:
            self.name = str(text or '')
            self.name_touched = True
            self.changed()

    def save(self, typed=None, applied=False):
        with self.lock:
            view = self.view
            if view is None or self.source is None or self.busy:
                return
            if self.card_open and typed and not applied:
                # what is typed on the card but was not applied counts: it is applied first, then the saving goes on
                state = self.apply(typed, quiet=True)
                if state == 'error':
                    return                      # the status line says what is wrong with the card
                if state == 'applied':
                    self.after_busy = lambda: self.save(applied=True)      # when the roster is rebuilt with it
                    return
            built = view[0]
            if built.problems:
                self.set_status("This roster does not pass the safety checks, so it cannot be saved: "
                                + built.problems[0], 'bad')
                return
            folder = self.source[0]
            source, upd = self.slot, self.update
            typed_name = self.name.strip()
            if upd.in_place(source):
                if upd.busy:
                    self.set_status("The Update tab is working. Save when it is done.", 'bad')
                    return
                if savedata.running_rpcs3():
                    self.set_status("Close RPCS3 first: a roster can only be updated while the game is closed.", 'bad')
                    return
                rename = typed_name if self.name_touched and typed_name and typed_name != source.name else None
                expected = self.raw_bytes

                def job():
                    result = savedata.update_in_place(folder, source, built.data, rename, expected=expected,
                                                      backup_root=datasource.app_dir('backups'))
                    return result, pipeline.write_report(built, f"{source.folder}_edited")

                def done(r):
                    (slot, backup, changed), _report = r
                    self.set_status((f"Updated \"{slot.name}\" ({slot.folder}, {slot.region})"
                                     + (f"; the old roster is kept in {backup}" if backup else "")
                                     + ". In the game: start it; if it is not the roster in use, Roster Management > "
                                     "Load Roster.") if changed else "Nothing to save: the roster is the same.", 'good')
                    self.session, self.session_teams, self.source = set(), set(), None       # read it again
                    self.name_touched = False
                    self.after_busy = self._rescan
                self._work("Saving...", job, done)
                return
            name = savedata.clean_name(typed_name or savedata.default_name())
            targets = upd.save_targets(source) or [source.title_id]     # the Update tab's "Save for"

            def job():
                slots = [savedata.install(folder, source, built.data, name, title_id=t) for t in targets]
                report = pipeline.write_report(built, f"{slots[0].folder}_edited")
                return slots, report

            def done(r):
                slots, _report = r
                where = " and ".join(f"{s.folder}, {s.region}" for s in slots)
                self.set_status(f"Saved as \"{slots[0].name}\" ({where}). In the game: Roster Management > "
                                "Load Roster.", 'good')
                self.after_busy = lambda: self._rescan(reopen=False)
            self._work("Saving...", job, done)

    def _rescan(self, reopen=True):
        """The Update tab lists the rosters again (a new one, a new time); the editor reads the saved one again."""
        upd = self.update
        if upd.rpcs3 is not None:
            upd.set_rpcs3(upd.rpcs3.where, quiet=True)
        if reopen:
            self.opened()

    def closing(self):
        """May the window close now? Not while a roster is being saved."""
        with self.lock:
            if not self.busy or self.status[0] != "Saving...":
                return True
            self.update.ask("Please wait", ["The Roster editor is saving a roster. Close the window when it is done."],
                            [("OK", 'ok', 'primary')], {})
            return False

    # --- what the page shows ----------------------------------------------------------------------------
    def snapshot(self):
        with self.lock:
            snap, upd = self.snap, self.update
            slot = self.slot
            in_place = upd.in_place(slot) if slot is not None else False
            ready = snap is not None and not self.busy
            built = self.view[0] if self.view else None
            team_slot = self.team if isinstance(self.team, int) else None
            choices = self.choices()
            modal = self.modal
            if modal is not None and modal.get('kind') == 'edits':
                modal = dict(modal, items=self._edits_view())
            return {
                'busy': self.busy,
                'loaded': snap is not None,
                'roster': {'name': slot.name, 'region': slot.region, 'folder': slot.folder} if slot else None,
                'status': {'text': self.status[0], 'tone': self.status[1]},
                'progress': {'value': 0, 'active': self.busy, 'indeterminate': self.busy},
                'leagues': snap.leagues() if snap else [],
                'league': self.league,
                'teams': [{'id': t, 'name': snap.team_name(t), 'count': len(snap.rosters.get(t, []))}
                          for t in snap.teams_in(self.league)] if snap and self.league else [],
                'team': self.team,
                'team_name': snap.team_name(self.team) if snap and self.team is not None else '',
                'query': self.query,
                'searching': self.found is not None,
                'rows': self.rows if snap else [],
                'selected': self.player.who if self.card_open and self.player is not None else None,
                'card': self._card_view(),
                'choices': {'teams': [[k, v] for k, v in choices.items()], 'countries': COUNTRIES,
                            'positions': list(C.POSITIONS)},
                'edits_count': len(self.edits) + len(self.teams),
                'team_tools': {'team': team_slot is not None and snap is not None,
                               'uniforms': team_slot is not None and snap is not None and 0 <= team_slot < 32},
                'save': {'mode': S.IN_PLACE if in_place else S.AS_NEW,
                         'mode_enabled': ready and slot is not None and not getattr(slot, 'disc', False) and not upd.busy,
                         'name': self.name,
                         'button': {'text': "Save to this roster" if in_place else "Save as new roster",
                                    'enabled': ready and built is not None and not upd.busy}},
                'modal': modal,
            }
