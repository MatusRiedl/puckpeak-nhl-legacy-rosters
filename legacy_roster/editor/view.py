"""The "Roster editor" tab of the window: browse a roster, preview the update, change players.

    left    league and team list
    middle  the team's players (sortable; coloured by what changed)
    right   the selected player's card: basics, team, ratings; Apply / Undo my edit

"As is" is the chosen roster save, "To be" what the update makes of it (Preview update runs it in
memory). Both show the player's own edits (edits.py), which are kept on this PC and applied to
every later update as well. Save as new roster writes what is shown as a new save after the same
safety checks as an update. Slow work runs in a worker thread; results come back through the
window's queue (App.poll runs ('ui', callable) messages on the Tk thread).
"""
import datetime
import threading
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from .. import edits, pipeline, ratings, savedata
from .. import layout as L
from .. import theme as T
from ..art.portraits import person_key
from ..builder import Data
from ..widgets import GhostButton, PrimaryButton
from . import model

AS_IS, TO_BE = "As is", "To be"
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
        self.offset = ratings.overall_offset(app.pack.get('ea_ratings') or []) if app.pack else None
        self.season = (app.pack or {}).get('season')
        self.source = None              # (savedata folder, roster folder) the views were made from
        self.raw = None                 # Snapshot of the save as it is, without my edits
        self.raw_source = None
        self.views = {}                 # AS_IS / TO_BE -> (BuildResult, Snapshot) with my edits
        self.preview_bytes = None       # the update's result without my edits
        self.mode = AS_IS
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
        self.mode_switch = ctk.CTkSegmentedButton(bar, values=[AS_IS, TO_BE], command=self.set_mode,
                                                  font=T.font(13, 'semibold'), selected_color=T.ACCENT,
                                                  selected_hover_color=T.ACCENT_DEEP, unselected_color=T.CELL,
                                                  unselected_hover_color=T.CELL_HOVER, fg_color=T.CELL)
        self.mode_switch.set(AS_IS)
        self.mode_switch.pack(side='left', padx=(14, 8))
        self.preview_button = GhostButton(bar, "Preview update", self.preview, height=30)
        self.preview_button.pack(side='left')
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
        self.fields = {}
        row = 2
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
        self.save_name = tk.StringVar(value=savedata.default_name() + " edited")
        ctk.CTkEntry(bar, textvariable=self.save_name, width=220, height=34, corner_radius=10, fg_color=T.CELL,
                     border_color=T.BORDER, text_color=T.STRONG, font=T.font(14)).grid(row=0, column=2, padx=(8, 8))
        self.save_button = PrimaryButton(bar, "Save as new roster", self.save, width=190, height=38)
        self.save_button.grid(row=0, column=3)

    # --- loading what is shown ---------------------------------------------------------------------
    def opened(self):
        """The tab came into view: (re)load if the chosen roster changed."""
        slot = self.app.selected_slot()
        if slot is None or self.app.rpcs3 is None:
            self.roster_label.configure(text="Pick RPCS3 and a roster on the Update tab first.")
            return
        source = (self.app.rpcs3.savedata, slot.folder)
        if source != self.source:
            self.source, self.views, self.preview_bytes = source, {}, None
            self.mode_switch.set(AS_IS)
            self.mode = AS_IS
            self.load(AS_IS)

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

    def _failed(self, err):
        self.busy = False
        self._enable(True)
        self.set_status(f"That did not work: {err}", T.RED)

    def _enable(self, on):
        for w in (self.preview_button, self.save_button, self.apply_button):
            w.configure(state='normal' if on else 'disabled')

    def _with_edits(self, raw_bytes):
        return pipeline.build(raw_bytes, Data(season_year=self.season or 2026), steps=[], my_edits=self.edits)

    def load(self, mode):
        folder, roster = self.source
        slot = next(s for s in savedata.list_rosters(folder) if s.folder == roster)
        self.roster_label.configure(text=f"{slot.name}")

        def job():
            with open(slot.sys_data, 'rb') as f:
                raw = f.read()
            base = self.preview_bytes if mode == TO_BE else raw
            built = self._with_edits(base)
            return raw, built
        self._work("Reading the roster..." if mode == AS_IS else "Applying your edits...", job,
                   lambda r: self._loaded(mode, *r))

    def _loaded(self, mode, raw, built):
        if self.raw is None or self.raw_source != self.source:
            self.raw = model.Snapshot(raw, self.offset, self.season)
            self.raw_source = self.source
        self.views[mode] = (built, model.Snapshot(built.data, self.offset, self.season))
        self.show()

    def preview(self):
        """Run the update in memory with the switches of the Update tab; show it as "To be"."""
        folder, roster = self.source or (None, None)
        if folder is None:
            return
        steps = [s for s in self.app.steps if self.app.steps[s].get()]

        def job():
            res = pipeline.update(folder, roster, steps, progress=lambda m: self.app.queue.put(('ui', lambda: self.set_status(m))),
                                  dry_run=True)
            if not res.build.ok:
                raise RuntimeError("the update did not pass the safety checks: " + "; ".join(res.build.problems[:2]))
            built = self._with_edits(res.build.data)
            return res.build.data, built

        def done(r):
            self.preview_bytes = r[0]
            self.views[TO_BE] = (r[1], model.Snapshot(r[1].data, self.offset, self.season))
            self.mode_switch.set(TO_BE)
            self.mode = TO_BE
            self.show()
        self._work("Previewing the update (nothing is saved)...", job, done)

    def set_mode(self, mode):
        self.mode = mode
        if mode == TO_BE and self.preview_bytes is None:
            self.mode_switch.set(AS_IS)
            self.mode = AS_IS
            self.set_status("Press Preview update first: it shows what the update will make of this roster.", T.GOLD)
            return
        if mode not in self.views:
            self.load(mode)
        else:
            self.show()

    def refresh(self):
        """After an edit: rebuild the shown roster with the edits (and the other view later)."""
        stale = [m for m in self.views if m != self.mode]
        for m in stale:
            del self.views[m]
        self.load(self.mode)

    # --- showing -------------------------------------------------------------------------------------------
    @property
    def snap(self):
        view = self.views.get(self.mode)
        return view[1] if view else None

    def show(self):
        snap = self.snap
        if snap is None:
            return
        leagues = snap.leagues()
        self.league.configure(values=leagues)
        if self.league.get() not in leagues:
            self.league.set(leagues[0])
        self.fields['team'].configure(values=self.team_choices())
        built = self.views[self.mode][0]
        if built.problems:
            self.set_status(f"Not playable yet: {built.problems[0]}" + (f" (and {len(built.problems) - 1} more)"
                                                                        if len(built.problems) > 1 else ""), T.RED)
        else:
            what = "the roster as it is" if self.mode == AS_IS else "the roster after the update"
            self.set_status(f"Showing {what}" + (f", with your {len(self.edits)} edits" if self.edits else "")
                            + ". Pick a team, then a player.", T.MUTED)
        self.show_teams()

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
        renamed = self.renamed()
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
                                 + ("   ·   you edited this player" if key in self.edits else ""))
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
        self.undo_button.configure(state='normal' if key in self.edits else 'disabled')

    def new_player(self):
        if self.snap is None:
            return
        self.player = None
        self.table.selection_remove(*self.table.selection())
        self._fill_card(None)

    # --- edits ----------------------------------------------------------------------------------------------
    def renamed(self):
        """New key -> original key of every player an edit renamed (or gave another birthdate)."""
        out = {}
        for who, e in self.edits.items():
            s, was = e.get('set') or {}, e.get('was')
            if was and any(s.get(k) for k in ('first', 'last', 'birth')):
                out[person_key(s.get('first') or was['first'], s.get('last') or was['last'],
                               s.get('birth') or was['birth'])] = who
        return out

    def edited_keys(self):
        """Person keys the shown roster has for edited players (a renamed player has a new key)."""
        return set(self.edits) | set(self.renamed())

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
                               **({'ratings': values['ratings']} if values['ratings'] else {})}
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
            if not changes and not rated and 'team' not in e and key not in self.edits:
                self.set_status("Nothing changed.")
                return
            self.edits[key] = e
        edits.save(self.edits)
        self._update_edits_button()
        self.app.refresh_state()
        self.refresh()

    def undo(self):
        p = self.player
        if p is None:
            return
        key = self.edit_key(p)
        if key in self.edits:
            del self.edits[key]
            edits.save(self.edits)
            self._update_edits_button()
            self.app.refresh_state()
            self.refresh()

    def _update_edits_button(self):
        self.edits_button.configure(text=f"My edits ({len(self.edits)})")

    def show_edits(self):
        """A small window listing every edit, each with a Remove button."""
        top = ctk.CTkToplevel(self, fg_color=T.BG)
        top.title("My edits")
        top.geometry("520x420")
        top.transient(self.winfo_toplevel())
        ctk.CTkLabel(top, text="Kept on this PC and applied after every update. Remove one to undo it.",
                     font=T.font(13), text_color=T.MUTED, wraplength=480, justify='left').pack(padx=16, pady=(14, 6),
                                                                                              anchor='w')
        box = ctk.CTkScrollableFrame(top, fg_color=T.CARD, corner_radius=T.RADIUS)
        box.pack(fill='both', expand=True, padx=16, pady=(0, 16))

        def fill():
            for w in box.winfo_children():
                w.destroy()
            if not self.edits:
                ctk.CTkLabel(box, text="No edits yet.", font=T.font(13), text_color=T.FAINT).pack(pady=20)
            for who, e in sorted(self.edits.items(), key=lambda kv: kv[1].get('label', kv[0])):
                row = ctk.CTkFrame(box, fg_color=T.CELL, corner_radius=10)
                row.pack(fill='x', pady=3)
                what = ['new player'] if e.get('new') else []
                what += [k for k in (e.get('set') or {})] + (['ratings'] if e.get('ratings') else []) + \
                    (['team'] if 'team' in e else [])
                ctk.CTkLabel(row, text=e.get('label', who), font=T.font(14, 'semibold'), text_color=T.STRONG,
                             anchor='w').pack(side='left', padx=(12, 6), pady=6)
                ctk.CTkLabel(row, text=", ".join(what), font=T.font(12), text_color=T.MUTED,
                             anchor='w').pack(side='left')
                GhostButton(row, "Remove", lambda k=who: remove(k), height=26).pack(side='right', padx=8)

        def remove(k):
            self.edits.pop(k, None)
            edits.save(self.edits)
            self._update_edits_button()
            self.app.refresh_state()
            fill()
            if self.source:
                self.refresh()
        fill()

    # --- saving ---------------------------------------------------------------------------------------------
    def save(self):
        view = self.views.get(self.mode)
        if view is None or self.source is None:
            return
        built = view[0]
        if built.problems:
            self.set_status("This roster does not pass the safety checks, so it cannot be saved: "
                            + built.problems[0], T.RED)
            return
        folder, roster = self.source
        source = next(s for s in savedata.list_rosters(folder) if s.folder == roster)
        name = savedata.clean_name(self.save_name.get().strip() or savedata.default_name())

        def job():
            slot = savedata.install(folder, source, built.data, name)
            report = pipeline.write_report(built, f"{slot.folder}_edited")
            return slot, report

        def done(r):
            slot, _report = r
            self.set_status(f"Saved as \"{slot.name}\" ({slot.folder}). In the game: Roster Management > "
                            "Load Roster.", T.GREEN)
            self.app.set_rpcs3(self.app.rpcs3.exe, quiet=True)
        self._work("Saving...", job, done)

    def set_status(self, text, colour=T.MUTED):
        self.status.configure(text=text, text_color=colour)
