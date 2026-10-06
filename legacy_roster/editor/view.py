"""The "Roster editor" tab of the window: browse the roster picked on the Update tab and change players.

    left    league and team list
    middle  the team's players (sortable; coloured by the edits made now)
    right   the selected player's card: basics, team, ratings; Apply / Undo my edit

It shows the roster save picked in step 2 as it is (the game's own roster too), plus the edits made in
this visit (`session`); the edits are kept on this PC (edits.py) and applied to every later update
as well, but earlier ones are not shown on top of a roster: they are in it once it was saved. The
card shows the player's picture: his own, or what the game shows now (pictures.py). Saving writes
what is shown after the same safety checks as an update, into the roster itself (a backup copy
first, savedata.update_in_place) or as a new roster, as the Update tab's choice says. Slow work
runs in a worker thread; results come back through the window's queue (App.poll runs ('ui',
callable) messages on the Tk thread).
"""
import datetime
import os
import threading
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from .. import datasource, edits, pipeline, ratings, savedata
from .. import layout as L
from .. import theme as T
from ..art.portraits import person_key
from ..widgets import Choice, GhostButton, PrimaryButton
from . import model
from .pictures import NO_GAME, Pictures

POSITIONS = ('C', 'LW', 'RW', 'D', 'G')
COLUMNS = (('pos', "Pos", 36), ('num', "#", 30), ('name', "Name", 140), ('age', "Age", 36), ('nat', "Nat", 40),
           ('ovr', "OVR", 38), ('note', "Change", 130))
ROW_COLOURS = {'joined': T.GREEN, 'new': T.GREEN, 'changed': T.GOLD, 'left': T.RED, 'edited': '#7fd1ee'}


def _cm(inches):
    return round(inches * 2.54)


def _kg(pounds):
    return round(pounds * 0.4536)


class EditorTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        self.edits = edits.load()
        self.teams = edits.load_teams()
        self.pending_photo = None       # a picture chosen for the player on the card, not applied yet
        self.offset = ratings.overall_offset(app.pack.get('ea_ratings') or []) if app.pack else None
        self.season = (app.pack or {}).get('season')
        self.source = None              # (savedata folder, roster folder, file stamp) the view was made from
        self.slot = None                # that roster (savedata.Slot or DiscSlot)
        self.raw = None                 # Snapshot of the save as it is
        self.raw_source = None
        self.raw_bytes = None           # its SYS-DATA, as read (an update in place checks it is still that)
        self.view = None                # (BuildResult, Snapshot): the roster with this visit's edits
        self.session = set()            # keys (edits.py) of the player edits made since the roster was opened
        self.session_teams = set()      # slots of the team edits made since then
        self.pictures = None            # pictures.Pictures of the shown roster's game
        self.picture_token = 0          # the picture on the card belongs to the latest request only
        self.after_busy = None          # what to do once the running job is finished
        self.team = None
        self.player = None              # model.Player on the card (None: a new player)
        self.busy = False
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self._toolbar()
        self._teams()
        self._table()
        self._card()
        self._savebar()

    # --- building the tab ------------------------------------------------------------------------
    def _toolbar(self):
        bar = ctk.CTkFrame(self, fg_color='transparent')
        bar.grid(row=0, column=0, columnspan=3, sticky='ew', pady=(0, 8))
        self.roster_label = ctk.CTkLabel(bar, text="", font=T.font(14, 'semibold'), text_color=T.STRONG, anchor='w')
        self.roster_label.pack(side='left')
        self.edits_button = GhostButton(bar, "", self.show_edits, height=30)
        self.edits_button.pack(side='right')
        GhostButton(bar, "New player", self.new_player, height=30).pack(side='right', padx=(0, 8))
        self.search = ctk.CTkEntry(bar, placeholder_text="Find a player (Enter)", width=170, height=30,
                                   corner_radius=15, fg_color=T.CELL, border_color=T.BORDER, text_color=T.TEXT,
                                   font=T.font(13))
        self.search.pack(side='right', padx=(0, 8))
        self.search.bind('<Return>', lambda _e: self.show_search())
        self._update_edits_button()

    def _style(self):
        scale = T.scaling(self)
        style = ttk.Style(self)
        style.theme_use('default')
        family = T._FAMILY['normal']
        style.configure('Puck.Treeview', background=T.CELL, fieldbackground=T.CELL, foreground=T.TEXT,
                        rowheight=round(24 * scale), borderwidth=0, font=(family, -round(13 * scale)))
        style.map('Puck.Treeview', background=[('selected', T.ACCENT_LINE)], foreground=[('selected', T.STRONG)])
        style.configure('Puck.Treeview.Heading', background=T.CARD, foreground=T.MUTED, relief='flat',
                        font=(T._FAMILY['bold'], -round(12 * scale), 'bold'))
        style.map('Puck.Treeview.Heading', background=[('active', T.CELL_HOVER)])
        style.layout('Puck.Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])

    def _tree(self, master, columns, height):
        scale = T.scaling(self)
        frame = ctk.CTkFrame(master, fg_color=T.CELL, corner_radius=10)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show='headings', style='Puck.Treeview',
                            height=height, selectmode='browse')
        for key, title, width in columns:
            tree.heading(key, text=title, command=lambda k=key: self.sort(k))
            tree.column(key, width=round(width * scale), minwidth=round(width * scale * 0.8),
                        stretch=key in ('note', 'team'), anchor='w')
        bar = ctk.CTkScrollbar(frame, command=tree.yview, button_color=T.BORDER_STRONG, button_hover_color=T.FAINT)
        tree.configure(yscrollcommand=bar.set)
        tree.pack(side='left', fill='both', expand=True, padx=(6, 0), pady=6)
        bar.pack(side='right', fill='y', pady=6)
        for tag, colour in ROW_COLOURS.items():
            tree.tag_configure(tag, foreground=colour)
        return frame, tree

    def _teams(self):
        self._style()
        side = ctk.CTkFrame(self, fg_color='transparent', width=210)
        side.grid(row=1, column=0, sticky='nsw', padx=(0, 8))
        self.league = ctk.CTkOptionMenu(side, values=["NHL"], command=lambda _v: self.show_teams(), height=30,
                                        fg_color=T.CELL, button_color=T.BORDER_STRONG,
                                        button_hover_color=T.CELL_HOVER, dropdown_fg_color=T.CARD,
                                        font=T.font(13, 'semibold'), dropdown_font=T.font(13))
        self.league.pack(fill='x', pady=(0, 6))
        GhostButton(side, "Edit this team", self.edit_team, height=28).pack(fill='x', pady=(0, 6))
        GhostButton(side, "Jerseys and ice...", self.edit_uniforms, height=28).pack(fill='x', pady=(0, 6))
        frame, self.team_tree = self._tree(side, (('team', "Team", 190),), 12)
        frame.pack(fill='both', expand=True)
        self.team_tree.bind('<<TreeviewSelect>>', lambda _e: self.pick_team())

    def _table(self):
        frame, self.table = self._tree(self, COLUMNS, 14)
        frame.grid(row=1, column=1, sticky='nsew')
        self.table.bind('<<TreeviewSelect>>', lambda _e: self.pick_player())
        self.sort_key, self.sort_desc = 'ovr', True      # best players first

    def _card(self):
        card = ctk.CTkScrollableFrame(self, fg_color=T.CARD, corner_radius=T.RADIUS, width=280,
                                      scrollbar_button_color=T.BORDER_STRONG, scrollbar_button_hover_color=T.FAINT)
        card.grid(row=1, column=2, sticky='nse', padx=(8, 0))
        card.columnconfigure(1, weight=1)
        self.card = card
        self.card_title = ctk.CTkLabel(card, text="Pick a player", font=T.font(16, 'bold'), text_color=T.STRONG,
                                       anchor='w')
        self.card_title.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(4, 0))
        self.card_note = ctk.CTkLabel(card, text="", font=T.font(12), text_color=T.MUTED, anchor='w', justify='left',
                                      wraplength=280)
        self.card_note.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 6))
        # the player's picture first: what the game shows now, or what the update brings ("To be")
        self.photo_preview = ctk.CTkLabel(card, text="", font=T.font(11), text_color=T.FAINT, anchor='w',
                                          justify='left', wraplength=270)
        self.photo_preview.grid(row=2, column=0, columnspan=2, sticky='w')
        self.photo_caption = ctk.CTkLabel(card, text="", font=T.font(11), text_color=T.MUTED, anchor='w',
                                          justify='left', wraplength=270)
        self.photo_caption.grid(row=3, column=0, columnspan=2, sticky='w')
        GhostButton(card, "Choose picture...", self.choose_photo, height=26).grid(row=4, column=0, columnspan=2,
                                                                                 sticky='w', pady=(2, 8))
        self.fields = {}
        row = 5
        for key, label in (('first', "First name"), ('last', "Last name"), ('num', "Number"), ('pos', "Position"),
                           ('shoots', "Shoots"), ('birth', "Born (YYYY-MM-DD)"), ('country', "Country"),
                           ('height', "Height (cm)"), ('weight', "Weight (kg)"), ('team', "Team"), ('ovr', "Overall")):
            ctk.CTkLabel(card, text=label, font=T.font(12), text_color=T.MUTED, anchor='w').grid(
                row=row, column=0, sticky='w', padx=(0, 8), pady=2)
            if key == 'pos':
                w = ctk.CTkOptionMenu(card, values=list(POSITIONS), height=28, fg_color=T.CELL,
                                      button_color=T.BORDER_STRONG, dropdown_fg_color=T.CARD, font=T.font(13))
            elif key == 'shoots':
                w = ctk.CTkSegmentedButton(card, values=['L', 'R'], height=28, selected_color=T.ACCENT,
                                           unselected_color=T.CELL, fg_color=T.CELL, font=T.font(13))
            elif key in ('country', 'team'):
                w = ctk.CTkComboBox(card, values=[''], height=28, fg_color=T.CELL, border_color=T.BORDER,
                                    button_color=T.BORDER_STRONG, dropdown_fg_color=T.CARD, font=T.font(13),
                                    dropdown_font=T.font(12))
            else:
                w = ctk.CTkEntry(card, height=28, fg_color=T.CELL, border_color=T.BORDER, text_color=T.TEXT,
                                 font=T.font(13))
            w.grid(row=row, column=1, sticky='ew', pady=2)
            self.fields[key] = w
            row += 1
        self.fields['country'].configure(values=sorted(L.NAT_CODE))
        self.ovr_row = row - 1
        ctk.CTkLabel(card, text="RATINGS (40-99)", font=T.font(12, 'bold'), text_color=T.MUTED, anchor='w').grid(
            row=row, column=0, columnspan=2, sticky='w', pady=(10, 2))
        self.rating_frame = ctk.CTkFrame(card, fg_color='transparent')
        self.rating_frame.grid(row=row + 1, column=0, columnspan=2, sticky='ew')
        self.rating_frame.columnconfigure((1, 3), weight=1)
        self.rating_fields = {}
        buttons = ctk.CTkFrame(card, fg_color='transparent')
        buttons.grid(row=row + 2, column=0, columnspan=2, sticky='ew', pady=(10, 4))
        self.apply_button = PrimaryButton(buttons, "Apply", self.apply, width=110, height=34)
        self.apply_button.pack(side='left')
        self.undo_button = GhostButton(buttons, "Undo my edit", self.undo, height=30)
        self.undo_button.pack(side='left', padx=(8, 0))
        self._card_enabled(False)

    def _savebar(self):
        bar = ctk.CTkFrame(self, fg_color='transparent')
        bar.grid(row=2, column=0, columnspan=3, sticky='ew', pady=(8, 0))
        bar.columnconfigure(1, weight=1)
        self.status = ctk.CTkLabel(bar, text="", font=T.font(13), text_color=T.MUTED, anchor='w', justify='left',
                                   wraplength=560)
        self.status.grid(row=0, column=0, columnspan=2, sticky='ew')
        self.save_mode = Choice(bar, [('update', "Update this roster", None), ('new', "Save as a new roster", None)],
                                self._pick_save_mode, height=34)
        self.save_mode.grid(row=0, column=2, padx=(8, 8))
        self.save_name = tk.StringVar(value=savedata.default_name() + " edited")
        self.name_touched = False
        entry = ctk.CTkEntry(bar, textvariable=self.save_name, width=200, height=34, corner_radius=10, fg_color=T.CELL,
                             border_color=T.BORDER, text_color=T.STRONG, font=T.font(14))
        entry.grid(row=0, column=3, padx=(0, 8))
        entry.bind('<Key>', lambda _e: setattr(self, 'name_touched', True))
        self.save_button = PrimaryButton(bar, "Save", self.save, width=150, height=38)
        self.save_button.grid(row=0, column=4)

    def _pick_save_mode(self, value):
        """The same choice as on the Update tab."""
        self.app.pick_save_mode(value)
        self._sync_save_bar()

    def _sync_save_bar(self):
        slot = self.slot
        in_place = self.app.in_place(slot) if slot is not None else False
        self.save_mode.set('update' if in_place else 'new')
        if not self.name_touched:
            self.save_name.set(slot.name if in_place else savedata.default_name() + " edited")
        self.save_button.configure(text="Save to this roster" if in_place else "Save as new roster")

    # --- loading what is shown ---------------------------------------------------------------------
    def opened(self):
        """The tab came into view: (re)load if the chosen roster changed."""
        slot = self.app.selected_slot()
        if slot is None or self.app.rpcs3 is None:
            self.roster_label.configure(text="Pick RPCS3 and a roster on the Update tab first.")
            return
        source = (self.app.rpcs3.savedata, slot.folder, self._stamp(slot))
        self.slot = slot                    # a roster save, or the game's own roster (savedata.DiscSlot)
        if source != self.source:           # another roster, or the file changed (an update, the game, a save here)
            self.source, self.view, self.pictures = source, None, None
            self.session, self.session_teams = set(), set()
            self.name_touched = False
            self.load()
        self._sync_save_bar()

    @staticmethod
    def _stamp(slot):
        """Size and time of a roster save's file, so a changed file is read again (None for the game's own roster)."""
        try:
            st = os.stat(slot.sys_data)
            return st.st_size, st.st_mtime_ns
        except (OSError, TypeError):
            return None

    def _work(self, text, job, done):
        """Run `job()` in a worker thread; `done(result)` runs on the Tk thread afterwards."""
        if self.busy:
            return
        self.busy = True
        self.set_status(text)
        self._enable(False)

        def run():
            try:
                result = job()
                self.app.queue.put(('ui', lambda: self._finish(done, result)))
            except Exception as err:          # shown to the player; the details go into the log
                self.app.queue.put(('ui', lambda: self._failed(err)))
        threading.Thread(target=run, daemon=True).start()

    def _finish(self, done, result):
        self.busy = False
        self._enable(True)
        done(result)
        then, self.after_busy = self.after_busy, None
        if then:
            then()

    def _failed(self, err):
        self.busy = False
        self._enable(True)
        self.after_busy = None
        self.set_status(f"That did not work: {err}", T.RED)

    def _enable(self, on):
        for w in (self.save_button, self.apply_button):
            w.configure(state='normal' if on else 'disabled')

    def _with_edits(self, raw_bytes):
        """The roster with the edits made since it was opened (the earlier ones are in it already)."""
        mine = {k: v for k, v in self.edits.items() if k in self.session}
        teams = {k: v for k, v in self.teams.items() if k in self.session_teams}
        return model.apply_edits(raw_bytes, mine, teams, self.season)

    def load(self):
        slot = self.slot
        self.roster_label.configure(text=f"{slot.name}")

        def job():
            raw = savedata.read_roster(slot)
            return raw, self._with_edits(raw)
        self._work("Reading the roster...", job, lambda r: self._loaded(*r))

    def _loaded(self, raw, built):
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

    # --- showing -------------------------------------------------------------------------------------------
    @property
    def snap(self):
        return self.view[1] if self.view else None

    def show(self):
        snap = self.snap
        if snap is None:
            return
        leagues = snap.leagues()
        self.league.configure(values=leagues)
        if self.league.get() not in leagues:
            self.league.set(leagues[0])
        self.fields['team'].configure(values=self.team_choices())
        built = self.view[0]
        if built.problems:
            self.set_status(f"Not playable yet: {built.problems[0]}" + (f" (and {len(built.problems) - 1} more)"
                                                                        if len(built.problems) > 1 else ""), T.RED)
        else:
            self.set_status("Showing the roster as it is" + (f", with your {len(self.session)} edits not saved yet"
                                                            if self.session or self.session_teams else "")
                            + ". Pick a team, then a player.", T.MUTED)
        self.show_teams()
        if self.player is not None:          # the same player as this view has him (team, rating, picture)
            p = snap.by_who.get(self.player.who)
            if p is not None:
                self.player = p
                self._fill_card(p)

    def show_teams(self):
        snap = self.snap
        tree = self.team_tree
        tree.delete(*tree.get_children())
        for t in snap.teams_in(self.league.get()):
            tree.insert('', 'end', iid=str(t), values=(f"{snap.team_name(t)}  ({len(snap.rosters.get(t, []))})",))
        keep = str(self.team) if self.team is not None and tree.exists(str(self.team)) else None
        first = keep or (tree.get_children() or [None])[0]
        if first:
            tree.selection_set(first)
            tree.see(first)

    def pick_team(self):
        sel = self.team_tree.selection()
        if not sel:
            return
        self.team = sel[0] if sel[0] == model.FREE_AGENTS else int(sel[0])
        self.show_players(self.snap.roster(self.team), self.team)

    def show_players(self, players, team=None):
        snap, tree = self.snap, self.table
        tree.delete(*tree.get_children())
        renamed = self.renamed(session_only=True)
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
                tag, note = 'changed', self._change_note(self.raw.by_who.get(renamed.get(p.who, p.who)), p,
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
        self.rows = {}
        for i, (p, tag, note) in enumerate(rows):
            iid = f"{i}"
            self.rows[iid] = (p, tag)
            tree.insert('', 'end', iid=iid, tags=(tag,) if tag else (),
                        values=(p.pos, p.num, p.name, p.age(snap.season_year), p.country, p.ovr or '', note))
        if self.sort_key:
            self.sort(self.sort_key, toggle=False)

    @staticmethod
    def _change_note(old, new, fields):
        """'OVR 83 -> 86, #10 -> 12' rather than field names."""
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

    def show_search(self):
        if self.snap is None:
            return
        found = self.snap.search(self.search.get())
        self.show_players(found)
        self.set_status(f"{len(found)} players found" if found else "Nobody by that name in this roster.")

    def sort(self, key, toggle=True):
        tree = self.table
        if toggle:
            self.sort_desc = (not getattr(self, 'sort_desc', False)) if self.sort_key == key else key in ('ovr', 'age')
        self.sort_key = key
        idx = [c[0] for c in COLUMNS].index(key)

        def value(iid):
            v = tree.item(iid, 'values')[idx]
            try:
                return (0, float(v))
            except (TypeError, ValueError):
                return (1, str(v).lower())
        for k, iid in enumerate(sorted(tree.get_children(), key=value, reverse=self.sort_desc)):
            tree.move(iid, '', k)

    # --- the player card ---------------------------------------------------------------------------------
    def team_choices(self):
        snap = self.snap
        self.choice_slot = {"Free agents": 'FA'}
        for t in range(len(snap.team_names)):
            if t in L.MIRROR_OF or not snap.team_names[t].strip():
                continue
            self.choice_slot[f"{snap.team_league[t]} · {snap.team_names[t]}"] = t
        return list(self.choice_slot)

    def slot_choice(self, slot):
        return next((k for k, v in self.choice_slot.items() if v == slot), "Free agents")

    def _card_enabled(self, on):
        for w in list(self.fields.values()) + list(self.rating_fields.values()):
            w.configure(state='normal' if on else 'disabled')
        self.apply_button.enable(on)

    def _ratings_for(self, goalie):
        """The rating fields of a skater or a goalie. Built once per kind and kept while players of
        the same kind are picked (rebuilding 50 widgets on each pick made the card flicker)."""
        if getattr(self, '_rating_kind', None) == goalie and self.rating_fields:
            for w in self.rating_fields.values():
                w.delete(0, 'end')
            return
        self._rating_kind = goalie
        for w in self.rating_frame.winfo_children():
            w.destroy()
        self.rating_fields = {}
        labels = model.GOALIE_ATTRIBUTES if goalie else model.SKATER_ATTRIBUTES
        for k, label in enumerate(labels):
            r, c = divmod(k, 2)
            ctk.CTkLabel(self.rating_frame, text=label, font=T.font(11), text_color=T.MUTED, anchor='w').grid(
                row=r, column=2 * c, sticky='w', padx=(0, 4), pady=1)
            e = ctk.CTkEntry(self.rating_frame, width=44, height=24, fg_color=T.CELL, border_color=T.BORDER,
                             text_color=T.TEXT, font=T.font(12))
            e.grid(row=r, column=2 * c + 1, sticky='w', padx=(0, 8), pady=1)
            self.rating_fields[label] = e

    def _put(self, key, value):
        w = self.fields[key]
        if isinstance(w, ctk.CTkEntry):
            w.delete(0, 'end')
            w.insert(0, '' if value is None else str(value))
        else:
            w.set(value)

    def pick_player(self):
        sel = self.table.selection()
        if not sel or sel[0] not in self.rows:
            return
        p, tag = self.rows[sel[0]]
        if tag == 'left':
            p = self.snap.by_who.get(p.who)
            if p is None:
                return
        self.player = p
        self._fill_card(p)

    def _fill_card(self, p):
        snap = self.snap
        self.pending_photo = None
        self._show_picture(p)
        self._card_enabled(True)
        self._ratings_for(p is not None and p.pos == 'G')
        if p is None:
            self.card_title.configure(text="New player")
            self.card_note.configure(text="Takes a spare player record (the save has a fixed number). "
                                          "Give a name, birthdate, team and overall; ratings are optional.")
            for key in ('first', 'last', 'num', 'birth', 'height', 'weight'):
                self._put(key, '')
            self._put('pos', 'C')
            self._put('shoots', 'L')
            self._put('country', 'CAN')
            self._put('team', self.slot_choice(self.team if isinstance(self.team, int) else 'FA'))
            self._put('ovr', 70)
            self.undo_button.configure(state='disabled')
            return
        key = self.edit_key(p)
        teams = model.club(p.teams)
        self.card_title.configure(text=p.name)
        self.card_note.configure(text=(", ".join(snap.team_name(t) for t in teams) or "Free agent")
                                 + (f"   ·   OVR {p.ovr}" if p.ovr else "")
                                 + ("   ·   you edited this player (not saved yet)" if key in self.session else ""))
        self._put('first', p.first)
        self._put('last', p.last)
        self._put('num', p.num)
        self._put('pos', p.pos)
        self._put('shoots', p.shoots)
        self._put('birth', "%04d-%02d-%02d" % p.birth)
        self._put('country', p.country)
        self._put('height', _cm(p.height_in))
        self._put('weight', _kg(p.weight_lb))
        self._put('team', self.slot_choice(teams[0] if teams else 'FA'))
        self._put('ovr', p.ovr or '')
        self.fields['ovr'].configure(state='disabled')
        for label, w in self.rating_fields.items():
            w.delete(0, 'end')
            w.insert(0, str(p.ratings.get(label, '')))
        self.undo_button.configure(state='normal' if key in self.session else 'disabled')

    def new_player(self):
        if self.snap is None:
            return
        self.player = None
        self.table.selection_remove(*self.table.selection())
        self._fill_card(None)

    # --- edits ----------------------------------------------------------------------------------------------
    def renamed(self, session_only=False):
        """New key -> original key of every player an edit renamed (or gave another birthdate); only the
        edits of this visit with `session_only` (the earlier ones are in the roster under the new name)."""
        out = {}
        for who, e in self.edits.items():
            if session_only and who not in self.session:
                continue
            s, was = e.get('set') or {}, e.get('was')
            if was and any(s.get(k) for k in ('first', 'last', 'birth')):
                out[person_key(s.get('first') or was['first'], s.get('last') or was['last'],
                               s.get('birth') or was['birth'])] = who
        return out

    def edited_keys(self):
        """Person keys the shown roster has for players edited in this visit (a renamed player has a new key)."""
        return set(self.session) | set(self.renamed(session_only=True))

    def edit_key(self, p):
        """The key an edit of `p` is stored under: his original name if he was renamed before."""
        return p.who if p.who in self.edits else self.renamed().get(p.who, p.who)

    def _read_card(self):
        """The card's values, checked: (values, None) or (None, what is wrong)."""
        f = {k: (w.get() if not isinstance(w, ctk.CTkSegmentedButton) else w.get()) for k, w in self.fields.items()}
        out = {'first': f['first'].strip(), 'last': f['last'].strip(), 'pos': f['pos'], 'shoots': f['shoots'],
               'country': f['country'].strip().upper()}
        if not out['first'] or not out['last']:
            return None, "A player needs a first and a last name."
        try:
            out['num'] = int(f['num'])
            if not 1 <= out['num'] <= 99:
                raise ValueError
        except ValueError:
            return None, "The number must be between 1 and 99."
        try:
            out['birth'] = list(datetime.date.fromisoformat(f['birth'].strip()).timetuple()[:3])
        except ValueError:
            return None, "Write the birthdate as YYYY-MM-DD, for example 2004-11-16."
        if L.country_code(out['country']) is None:
            return None, f"The game has no country {out['country'] or '(empty)'}; pick one from the list."
        try:
            out['height_in'] = round(int(f['height']) / 2.54) if f['height'].strip() else None
            out['weight_lb'] = round(int(f['weight']) / 0.4536) if f['weight'].strip() else None
        except ValueError:
            return None, "Height and weight are whole numbers (cm, kg)."
        if f['team'] not in self.choice_slot:
            return None, "Pick the team from the list."
        out['team'] = self.choice_slot[f['team']]
        rated = {}
        for label, w in self.rating_fields.items():
            v = w.get().strip()
            if not v:
                continue
            try:
                rated[label] = int(v)
                if not 40 <= rated[label] <= 99:
                    raise ValueError
            except ValueError:
                return None, f"{label}: ratings go from 40 to 99."
        out['ratings'] = rated
        if self.player is None:
            try:
                out['ovr'] = int(f['ovr'])
            except ValueError:
                return None, "Give the new player an overall (40-99)."
        return out, None

    def apply(self):
        values, problem = self._read_card()
        if problem:
            self.set_status(problem, T.RED)
            return
        p = self.player
        if p is None:                          # a new player
            who = person_key(values['first'], values['last'], values['birth'])
            if self.snap.by_who.get(who):
                self.set_status("That player is in the roster already: edit him instead.", T.RED)
                return
            fields = {k: values[k] for k in ('first', 'last', 'num', 'pos', 'shoots', 'birth', 'country',
                                             'height_in', 'weight_lb') if values.get(k) is not None}
            fields['pos'] = model.POS_KEY[values['pos']]
            self.edits[who] = {'label': f"{values['first']} {values['last']}", 'new': True, 'set': fields,
                               'team': values['team'], 'ovr': values['ovr'],
                               **({'ratings': values['ratings']} if values['ratings'] else {}),
                               **({'photo': self.pending_photo} if self.pending_photo else {})}
        else:
            key = self.edit_key(p)
            e = dict(self.edits.get(key) or {'label': p.name})
            current = {'first': p.first, 'last': p.last, 'num': p.num, 'pos': model.POS_KEY.get(p.pos, p.pos),
                       'shoots': p.shoots, 'birth': list(p.birth), 'country': p.country,
                       'height_in': p.height_in, 'weight_lb': p.weight_lb}
            wanted = dict(values, pos=model.POS_KEY[values['pos']])
            changes = {k: wanted[k] for k in current if wanted.get(k) is not None and wanted[k] != current[k]
                       and not (k == 'height_in' and _cm(current[k]) == _cm(wanted[k]))
                       and not (k == 'weight_lb' and _kg(current[k]) == _kg(wanted[k]))}
            if any(k in changes for k in ('first', 'last', 'birth')) and 'was' not in e:
                e['was'] = {'first': p.first, 'last': p.last, 'birth': list(p.birth)}
            e['set'] = dict(e.get('set') or {}, **changes)
            rated = {a: v for a, v in values['ratings'].items() if p.ratings.get(a) != v}
            if rated:
                e['ratings'] = dict(e.get('ratings') or {}, **rated)
            teams = model.club(p.teams)
            if values['team'] != (teams[0] if teams else 'FA'):
                e['team'] = values['team']
            if self.pending_photo:
                e['photo'] = self.pending_photo
            if not changes and not rated and 'team' not in e and not self.pending_photo and key not in self.edits:
                self.set_status("Nothing changed.")
                return
            self.edits[key] = e
        self.session.add(key if p is not None else who)
        edits.save(self.edits)
        self._update_edits_button()
        self.app.refresh_state()
        self.refresh()

    # --- pictures of the player's own ------------------------------------------------------------------
    def _pick_picture(self, title):
        from tkinter import filedialog
        path = filedialog.askopenfilename(parent=self.winfo_toplevel(), title=title,
                                          filetypes=[("Pictures", "*.png *.jpg *.jpeg *.webp *.bmp *.gif")])
        if not path:
            return None
        try:
            from PIL import Image
            with Image.open(path) as img:
                img.load()
        except Exception:
            self.set_status("That file is not a picture this program can read (PNG, JPG, WebP).", T.RED)
            return None
        return edits.keep_picture(path)

    def choose_photo(self):
        link = self._pick_picture("A photo for this player")
        if link:
            self.pending_photo = link
            self._show_picture(self.player)
            self.set_status("Press Apply to keep the photo. It shows in the game after an update with "
                            "\"Photos and logos\" on.", T.GOLD)

    def _pictures(self):
        """Pictures of the game the shown roster belongs to (None before RPCS3 is found)."""
        if self.app.rpcs3 is None or self.source is None:
            return None
        title_id = self.source[1][:9]
        if self.pictures is None or self.pictures.title_id != title_id or self.pictures.rpcs3 is not self.app.rpcs3:
            self.pictures = Pictures(self.app.rpcs3, title_id)
        return self.pictures

    def _show_picture(self, p):
        """The picture for player `p` (None: a new player), as the game shows it: his own if he has
        one, else what the game shows now. It is made in a worker thread; only the latest request is shown."""
        self.picture_token += 1
        token = self.picture_token
        own = self.pending_photo or ((self.edits.get(self.edit_key(p)) or {}).get('photo') if p is not None else None)
        if p is None and not own:
            self.photo_preview.configure(image=None, text="")
            self.photo_caption.configure(text="")
            return
        pictures = self._pictures()
        self.photo_caption.configure(text="Loading the picture...")

        def job():
            try:
                if own:
                    return Pictures.mine(own)
                if pictures is None:
                    return None, NO_GAME
                return pictures.current(p.artid, p.hasportrait)
            except Exception:
                return None, "The picture could not be read."

        def run():
            result = job()
            self.app.queue.put(('ui', lambda: self._picture_ready(token, *result)))
        threading.Thread(target=run, daemon=True).start()

    def _picture_ready(self, token, pic, caption):
        if token != self.picture_token:          # the card shows someone else by now
            return
        if pic is None:
            self.photo_preview.configure(image=None, text="")
        else:
            self._preview = ctk.CTkImage(light_image=pic, dark_image=pic, size=(240, 120))
            self.photo_preview.configure(image=self._preview, text="")
        self.photo_caption.configure(text=caption)

    def edit_team(self):
        """A small window: the selected team's name, city, abbreviation and logo."""
        if not isinstance(self.team, int) or self.snap is None:
            self.set_status("Pick a team first.", T.GOLD)
            return
        slot, snap = self.team, self.snap
        T_ = snap.R.T
        mine = dict(self.teams.get(str(slot)) or {})
        top = ctk.CTkToplevel(self, fg_color=T.BG)
        top.title("Team")
        top.geometry("460x420")
        top.transient(self.winfo_toplevel())
        ctk.CTkLabel(top, text=snap.team_name(slot), font=T.font(16, 'bold'), text_color=T.STRONG).pack(
            padx=16, pady=(14, 2), anchor='w')
        ctk.CTkLabel(top, text="The game's menus show these names and the logo after an update with "
                               "\"Photos and logos\" on.", font=T.font(12), text_color=T.MUTED, wraplength=420,
                     justify='left').pack(padx=16, anchor='w')
        form = ctk.CTkFrame(top, fg_color='transparent')
        form.pack(fill='x', padx=16, pady=8)
        form.columnconfigure(1, weight=1)
        boxes = {}
        for k, (part, label, field) in enumerate((('full', "Full name", 'fullname'), ('city', "City", 'shortname'),
                                                  ('abbr', "Abbreviation", 'abbrname'))):
            ctk.CTkLabel(form, text=label, font=T.font(12), text_color=T.MUTED).grid(row=k, column=0, sticky='w',
                                                                                      padx=(0, 8), pady=3)
            e = ctk.CTkEntry(form, height=28, fg_color=T.CELL, border_color=T.BORDER, text_color=T.TEXT, font=T.font(13))
            e.insert(0, mine.get(part) or T_.get(slot, field))
            e.grid(row=k, column=1, sticky='ew', pady=3)
            boxes[part] = e
        preview = ctk.CTkLabel(top, text="", font=T.font(12), text_color=T.FAINT)

        def show_logo(link):
            if not link:
                return
            try:
                from PIL import Image
                from ..art import images
                pic = images.logo(Image.open(link[5:]), 't', (256, 256))
                top._logo = ctk.CTkImage(light_image=pic, dark_image=pic, size=(96, 96))
                preview.configure(image=top._logo, text="")
            except Exception:
                preview.configure(text="(your logo)")

        def choose_logo():
            link = self._pick_picture("A logo for this team")
            if link:
                mine['logo'] = link
                show_logo(link)

        GhostButton(top, "Choose logo...", choose_logo, height=28).pack(padx=16, anchor='w')
        preview.pack(padx=16, pady=6, anchor='w')
        show_logo(mine.get('logo'))

        def apply_team():
            for part, e in boxes.items():
                value = e.get().strip()
                field = {'full': 'fullname', 'city': 'shortname', 'abbr': 'abbrname'}[part]
                if value and value != T_.get(slot, field):
                    mine[part] = value
            if mine:
                self.teams[str(slot)] = mine
                self.session_teams.add(str(slot))
            edits.save(teams=self.teams)
            top.destroy()
            self._update_edits_button()
            self.refresh()

        def undo_team():
            self.teams.pop(str(slot), None)
            self.session_teams.discard(str(slot))
            edits.save(teams=self.teams)
            top.destroy()
            self._update_edits_button()
            self.refresh()
        bar = ctk.CTkFrame(top, fg_color='transparent')
        bar.pack(fill='x', padx=16, pady=(4, 14))
        PrimaryButton(bar, "Apply", apply_team, width=110, height=34).pack(side='left')
        GhostButton(bar, "Undo team edit", undo_team, height=30).pack(side='left', padx=(8, 0))

    def edit_uniforms(self):
        """The window for a team's jerseys and centre-ice logo (editor/uniforms.py)."""
        if not isinstance(self.team, int) or self.snap is None:
            self.set_status("Pick a team first.", T.GOLD)
            return
        if not 0 <= self.team < 32:
            self.set_status("Jerseys and the centre-ice logo can be changed for the 32 NHL teams.", T.GOLD)
            return
        from .uniforms import UniformsWindow
        UniformsWindow(self, self.team)

    def undo(self):
        p = self.player
        if p is None:
            return
        key = self.edit_key(p)
        if key in self.edits and key in self.session:      # an edit made before is in the roster: it stays there
            del self.edits[key]
            self.session.discard(key)
            edits.save(self.edits)
            self._update_edits_button()
            self.app.refresh_state()
            self.refresh()

    def _update_edits_button(self):
        self.edits_button.configure(text=f"My edits ({len(self.edits) + len(self.teams)})")

    def show_edits(self):
        """A small window listing every edit, each with a Remove button."""
        top = ctk.CTkToplevel(self, fg_color=T.BG)
        top.title("My edits")
        top.geometry("520x420")
        top.transient(self.winfo_toplevel())
        ctk.CTkLabel(top, text="Kept on this PC and applied after every update (the Update tab's My edits switch). "
                               "Removing one stops that; a roster that was saved with it keeps it.",
                     font=T.font(13), text_color=T.MUTED, wraplength=480, justify='left').pack(padx=16, pady=(14, 6),
                                                                                              anchor='w')
        box = ctk.CTkScrollableFrame(top, fg_color=T.CARD, corner_radius=T.RADIUS)
        box.pack(fill='both', expand=True, padx=16, pady=(0, 16))

        def fill():
            for w in box.winfo_children():
                w.destroy()
            if not self.edits and not self.teams:
                ctk.CTkLabel(box, text="No edits yet.", font=T.font(13), text_color=T.FAINT).pack(pady=20)
            for slot, e in sorted(self.teams.items(), key=lambda kv: int(kv[0])):
                row = ctk.CTkFrame(box, fg_color=T.CELL, corner_radius=10)
                row.pack(fill='x', pady=3)
                name = self.snap.team_name(int(slot)) if self.snap else f"team {slot}"
                ctk.CTkLabel(row, text=name, font=T.font(14, 'semibold'), text_color=T.STRONG,
                             anchor='w').pack(side='left', padx=(12, 6), pady=6)
                ctk.CTkLabel(row, text="team: " + ", ".join(sorted(e)), font=T.font(12), text_color=T.MUTED,
                             anchor='w').pack(side='left')
                GhostButton(row, "Remove", lambda k=slot: remove_team(k), height=26).pack(side='right', padx=8)
            for who, e in sorted(self.edits.items(), key=lambda kv: kv[1].get('label', kv[0])):
                row = ctk.CTkFrame(box, fg_color=T.CELL, corner_radius=10)
                row.pack(fill='x', pady=3)
                what = ['new player'] if e.get('new') else []
                what += [k for k in (e.get('set') or {})] + (['ratings'] if e.get('ratings') else []) + \
                    (['team'] if 'team' in e else []) + (['photo'] if e.get('photo') else [])
                ctk.CTkLabel(row, text=e.get('label', who), font=T.font(14, 'semibold'), text_color=T.STRONG,
                             anchor='w').pack(side='left', padx=(12, 6), pady=6)
                ctk.CTkLabel(row, text=", ".join(what), font=T.font(12), text_color=T.MUTED,
                             anchor='w').pack(side='left')
                GhostButton(row, "Remove", lambda k=who: remove(k), height=26).pack(side='right', padx=8)

        def remove_team(k):
            self.teams.pop(k, None)
            self.session_teams.discard(k)
            edits.save(teams=self.teams)
            self._update_edits_button()
            fill()
            if self.source:
                self.refresh()

        def remove(k):
            self.edits.pop(k, None)
            self.session.discard(k)
            edits.save(self.edits)
            self._update_edits_button()
            self.app.refresh_state()
            fill()
            if self.source:
                self.refresh()
        fill()

    # --- saving ---------------------------------------------------------------------------------------------
    def save(self):
        view = self.view
        if view is None or self.source is None:
            return
        built = view[0]
        if built.problems:
            self.set_status("This roster does not pass the safety checks, so it cannot be saved: "
                            + built.problems[0], T.RED)
            return
        folder, roster = self.source[:2]
        source = self.slot
        typed = self.save_name.get().strip()
        if self.app.in_place(source):
            if savedata.running_rpcs3():
                self.set_status("Close RPCS3 first: a roster can only be updated while the game is closed.", T.RED)
                return
            rename = typed if self.name_touched and typed and typed != source.name else None
            expected = self.raw_bytes

            def job():
                result = savedata.update_in_place(folder, source, built.data, rename, expected=expected,
                                                  backup_root=datasource.app_dir('backups'))
                return result, pipeline.write_report(built, f"{source.folder}_edited")

            def done(r):
                (slot, backup, changed), _report = r
                self.set_status((f"Updated \"{slot.name}\" ({slot.folder}, {slot.region})"
                                 + (f"; the old roster is kept in {backup}" if backup else "") + ". In the game: start it; "
                                 "if it is not the roster in use, Roster Management > Load Roster.") if changed else
                                "Nothing to save: the roster is the same.", T.GREEN)
                self.session, self.session_teams, self.source = set(), set(), None       # read it again
                self.name_touched = False
                self.app.set_rpcs3(self.app.rpcs3.where, quiet=True)
                self.opened()
            self._work("Saving...", job, done)
            return
        name = savedata.clean_name(typed or savedata.default_name())
        targets = self.app.save_targets(source) or [source.title_id]     # the Update tab's "Save for"

        def job():
            slots = [savedata.install(folder, source, built.data, name, title_id=t) for t in targets]
            report = pipeline.write_report(built, f"{slots[0].folder}_edited")
            return slots, report

        def done(r):
            slots, _report = r
            where = " and ".join(f"{s.folder}, {s.region}" for s in slots)
            self.set_status(f"Saved as \"{slots[0].name}\" ({where}). In the game: Roster Management > "
                            "Load Roster.", T.GREEN)
            self.app.set_rpcs3(self.app.rpcs3.where, quiet=True)
        self._work("Saving...", job, done)

    def set_status(self, text, colour=T.MUTED):
        self.status.configure(text=text, text_color=colour)
