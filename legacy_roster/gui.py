"""The window: say where RPCS3 is, pick a roster, switch on what to update, press one button."""
import datetime
import json
import os
import queue
import subprocess
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog

try:
    import customtkinter as ctk
except ImportError:      # only when run from source without the window's one extra package
    sys.exit("The window needs the 'customtkinter' package:  pip install customtkinter\n"
             "(the command line works without it:  python -m legacy_roster list --rpcs3 <rpcs3.exe>)")

from . import __version__, datasource, layout, pipeline, savedata
from . import theme as T
from .art.install import ArtError, installed as art_installed, remove as remove_art
from .art.photopack import PhotoPack
from .editor.view import EditorTab
from . import edits as my_edits
from .progress import fraction
from .roster import Roster
from .widgets import Banner, Card, GhostButton, PrimaryButton, RosterRow, SwitchRow

SETTINGS = 'settings.json'
PHOTOS = 'photos'           # the "Photos and logos" switch in the remembered settings
EDITS = 'edits'             # the "My edits" switch
UPDATE_TAB, EDITOR_TAB = "Update", "Roster editor"
MIN_HEIGHT = 640
DETAILS_HEIGHT = 150
SITE = "https://www.puckpeak.com"
SITE_LABEL = "www.puckpeak.com"
TAGLINE = "NHL & hockey analytics like never before"
HOW_TO_LOAD ="In the game: Roster Management > Load Roster, pick it, then save the roster once so it stays active."


def load_settings():
    try:
        with open(datasource.app_dir(SETTINGS), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(values):
    try:
        with open(datasource.app_dir(SETTINGS), 'w', encoding='utf-8') as f:
            json.dump(values, f)
    except OSError:
        pass


def open_site():
    """Puck Peak's website in the player's browser (the header logo and line link there)."""
    import webbrowser
    webbrowser.open(SITE)


def friendly_date(when, now=None):
    now = now or datetime.datetime.now()
    days = (now.date() - when.date()).days
    if days == 0:
        return f"today {when:%H:%M}"
    if days == 1:
        return f"yesterday {when:%H:%M}"
    return f"{when.day} {when:%b %Y}"


def shorten(path, fits):
    """`path` with as much of its middle cut out as needed for fits(text) to be true, so both the
    drive and the file name stay visible."""
    text, keep = path, len(path)
    while keep > 12 and not fits(text):
        keep -= 1
        text = path[:keep // 2] + "..." + path[len(path) - (keep - keep // 2):]
    return text


def short_reason(problem):
    if 'stock EA roster' in problem:
        return "Cannot be used: this is the stock EA roster (no Utah, Seattle or Vegas)."
    return "Cannot be used: " + problem.split('. ')[0].rstrip('.') + "."


class App:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.queue = queue.Queue()
        self.rpcs3 = None           # savedata.Rpcs3 once the program has been found
        self.slots = []
        self.usable = {}            # roster folder -> None when usable, else the reason it is not
        self.rows = {}              # roster folder -> RosterRow
        self.selected = None        # roster folder to start from
        self.busy = False
        self.photos_running = False # the running update also makes photos and logos
        self.at = 0.0               # progress of the running update, 0..1
        self.last_report = None
        self.name_edited = False
        self.details_open = False
        self.details_grown = self.banner_grown = 0      # how much those panels made the window grow
        try:
            self.pack = datasource.load_pack(offline=True)
        except datasource.Offline:
            self.pack = {}

        root.title(f"Puck Peak  -  Legacy Roster Updater {__version__}")
        # as tall as the content likes, but never taller than the screen (768-line laptops)
        room = T.screen_height(root) - 90
        root.geometry(f"1000x{max(MIN_HEIGHT, min(730, room))}")
        root.minsize(940, MIN_HEIGHT)
        self._header()
        self._footer()              # packed before the body, so it is the body that gives way
        self.tabs = ctk.CTkTabview(root, fg_color=T.BG, corner_radius=0, border_width=0, height=10,
                                   segmented_button_fg_color=T.CELL, segmented_button_selected_color=T.ACCENT,
                                   segmented_button_selected_hover_color=T.ACCENT_DEEP,
                                   segmented_button_unselected_color=T.CELL,
                                   segmented_button_unselected_hover_color=T.CELL_HOVER, text_color=T.TEXT,
                                   command=self.tab_changed)
        self.tabs.pack(fill='both', expand=True, padx=12, pady=(2, 0))
        self.tabs._segmented_button.configure(font=T.font(14, 'semibold'))
        body = ctk.CTkFrame(self.tabs.add(UPDATE_TAB), fg_color='transparent')
        body.pack(fill='both', expand=True, padx=6, pady=(4, 0))
        body.columnconfigure(0, weight=11, uniform='col')
        body.columnconfigure(1, weight=9, uniform='col')
        body.rowconfigure(1, weight=1)
        self._card_rpcs3(body).grid(row=0, column=0, sticky='nsew', padx=(0, 6), pady=(0, 10))
        self._card_roster(body).grid(row=1, column=0, sticky='nsew', padx=(0, 6), pady=(0, 10))
        self._card_updates(body).grid(row=0, column=1, rowspan=2, sticky='nsew', padx=(6, 0), pady=(0, 10))
        self._card_name(body).grid(row=2, column=0, columnspan=2, sticky='nsew')
        self.banner = Banner(body)
        self.banner.grid(row=3, column=0, columnspan=2, sticky='nsew', pady=(10, 0))
        self.banner.grid_remove()
        self.editor = EditorTab(self.tabs.add(EDITOR_TAB), self)
        self.editor.pack(fill='both', expand=True, padx=6, pady=(4, 0))

        root.bind('<Return>', lambda _e: self.start())
        self.set_rpcs3(self.settings.get('rpcs3') or self.settings.get('folder') or savedata.running_rpcs3(),
                       quiet=True)
        self.tick()
        self.poll()

    # --- building the window ----------------------------------------------------------------
    def _header(self):
        head = ctk.CTkFrame(self.root, fg_color='transparent')
        head.pack(fill='x', pady=(12, 0))
        logo = tk.Label(head, image=T.logo(self.root), bg=T.BG, bd=0, cursor='hand2')
        logo.pack()
        logo.bind('<Button-1>', lambda _e: open_site())
        link = ctk.CTkLabel(head, text=f"{TAGLINE}   ·   {SITE_LABEL}", font=T.font(14, 'semibold'),
                            text_color=T.ACCENT, cursor='hand2')
        link.pack(pady=(0, 2))
        link.bind('<Button-1>', lambda _e: open_site())
        link.bind('<Enter>', lambda _e: link.configure(font=T.font(14, 'semibold', underline=True)))
        link.bind('<Leave>', lambda _e: link.configure(font=T.font(14, 'semibold')))
        line = ctk.CTkFrame(head, fg_color='transparent')
        line.pack(pady=(0, 6))
        ctk.CTkLabel(line, text="LEGACY ROSTER UPDATER", font=T.font(13, 'bold'), text_color=T.TEXT).pack(side='left')
        ctk.CTkLabel(line, text=f"   |   NHL Legacy Edition on RPCS3   |   version {__version__}",
                     font=T.font(13), text_color=T.MUTED).pack(side='left')
        tk.Label(self.root, image=T.glow_line(self.root, 760), bg=T.BG, bd=0).pack()

    def _card_rpcs3(self, master):
        card = Card(master, 1, "Where is RPCS3?")
        row = ctk.CTkFrame(card.body, fg_color='transparent')
        row.pack(fill='x')
        row.columnconfigure(0, weight=1)
        box = ctk.CTkFrame(row, fg_color=T.CELL, corner_radius=10, height=40)
        box.grid(row=0, column=0, sticky='ew')
        box.pack_propagate(False)
        self.path = ctk.CTkLabel(box, text="", font=T.font(14), text_color=T.TEXT, anchor='w')
        self.path.pack(fill='both', expand=True, padx=12)
        self.path_full = ""
        # the label's own size event (customtkinter's bind() would listen to its inner parts)
        tk.Frame.bind(self.path, '<Configure>', lambda _e: self.fit_path(), '+')
        self.change = GhostButton(row, "Change", self.browse, width=96, height=40)
        self.find = PrimaryButton(row, "Find rpcs3.exe", self.browse, width=150, height=40)
        self.rpcs3_note = ctk.CTkLabel(card.body, text="", font=T.font(13), text_color=T.MUTED, anchor='w',
                                       justify='left', wraplength=470)
        self.rpcs3_note.pack(fill='x', pady=(8, 0))
        return card

    def _card_roster(self, master):
        card = Card(master, 2, "Which roster should be updated?")
        self.roster_card = card
        self.roster_list = ctk.CTkScrollableFrame(card.body, fg_color='transparent', height=96,
                                                  scrollbar_button_color=T.BORDER_STRONG,
                                                  scrollbar_button_hover_color=T.FAINT)
        self.roster_list.pack(fill='both', expand=True)
        self.roster_empty = ctk.CTkLabel(card.body, text="Pick RPCS3 first. Your rosters will be listed here.",
                                         font=T.font(14), text_color=T.FAINT)
        return card

    def _card_updates(self, master):
        card = Card(master, 3, "What should be updated?")
        sources = self.pack.get('sources', {})
        notes = {pipeline.NHL: "Today's rosters from NHL.com",
                 pipeline.RATINGS: self._dated(sources.get('ea_ratings')),
                 pipeline.NATIONAL: self._dated(sources.get('iihf'))}
        remembered = self.settings.get('steps', {})
        available = pipeline.steps_for(self.pack)
        later = [name.split(' (')[0] for name in pipeline.planned(self.pack)]
        if later:
            ctk.CTkLabel(card.body, text="Coming later:  " + "  ·  ".join(later), font=T.font(12),
                         text_color=T.FAINT, anchor='w', justify='left', wraplength=380
                         ).pack(side='bottom', fill='x', pady=(4, 0))
        # shown only while photos and logos are installed
        self.remove_art = GhostButton(card.body, "Remove photos and logos", self.remove_photos, height=28)
        # the list scrolls: on a small screen, or once more leagues are available than fit
        rows = ctk.CTkScrollableFrame(card.body, fg_color='transparent', height=96,
                                      scrollbar_button_color=T.BORDER_STRONG, scrollbar_button_hover_color=T.FAINT)
        rows.pack(fill='both', expand=True)
        self.steps, self.switches = {}, []
        for step in available:
            new = step in pipeline.EXPERIMENTAL
            var = tk.BooleanVar(value=remembered.get(step, not new))
            self.steps[step] = var
            row = SwitchRow(rows, pipeline.STEP_LABELS[step], notes.get(step) or self._dated(sources.get(step)),
                            var, self.refresh_state, new=new, extra=pipeline.left_out_note(self.pack, step))
            row.pack(fill='x', pady=(0, 5), padx=(1, 10))
            self.switches.append(row)
        bundled = PhotoPack.open()
        self.photos = tk.BooleanVar(value=remembered.get(PHOTOS, bundled is not None))
        note = (f"{len(bundled):,} photos and logos in this program, from {bundled.built}" if bundled else
                "Current photos and club logos, downloaded on this PC")
        row = SwitchRow(rows, "Photos and logos", note, self.photos, self.refresh_state, new=True,
                        extra="RPCS3 must be closed. They can be removed at any time.")
        row.pack(fill='x', pady=(0, 5), padx=(1, 10))
        self.switches.append(row)
        self.use_edits = tk.BooleanVar(value=remembered.get(EDITS, True))
        row = SwitchRow(rows, "My edits", "Your changes from the Roster editor, applied after the update",
                        self.use_edits, self.refresh_state, new=True,
                        extra="Kept on this PC, so the next download does not undo them.")
        row.pack(fill='x', pady=(0, 5), padx=(1, 10))
        self.switches.append(row)
        return card

    def _card_name(self, master):
        card = Card(master, 4, "Name of the new roster")
        row = ctk.CTkFrame(card.body, fg_color='transparent')
        row.pack(fill='x')
        row.columnconfigure(0, weight=1)
        self.name = tk.StringVar(value=savedata.default_name())
        self.name_entry = ctk.CTkEntry(row, textvariable=self.name, height=42, corner_radius=10, fg_color=T.CELL,
                                       border_color=T.BORDER, border_width=1, text_color=T.STRONG, font=T.font(15))
        self.name_entry.grid(row=0, column=0, sticky='ew')
        self.name_entry.bind('<Key>', lambda _e: setattr(self, 'name_edited', True))
        self.go = PrimaryButton(row, "Update roster", self.start, width=190)
        self.go.grid(row=0, column=1, padx=(12, 0))
        self.name_note = ctk.CTkLabel(card.body, text="This is the name you will see in the game's Load Roster list.",
                                      font=T.font(13), text_color=T.MUTED, anchor='w', justify='left', wraplength=900)
        self.name_note.pack(fill='x', pady=(8, 0))
        return card

    def _footer(self):
        foot = self.foot = ctk.CTkFrame(self.root, fg_color='transparent')
        foot.pack(side='bottom', fill='x', padx=18, pady=(10, 12))
        foot.columnconfigure(1, weight=1)
        self.bar = ctk.CTkProgressBar(foot, width=260, height=8, corner_radius=4, fg_color=T.CELL,
                                      progress_color=T.CELL)
        self.bar.set(0)
        self.bar.grid(row=0, column=0, padx=(2, 12))
        self.status = ctk.CTkLabel(foot, text="Ready.", font=T.font(13), text_color=T.MUTED, anchor='w')
        self.status.grid(row=0, column=1, sticky='ew')
        self.details_button = GhostButton(foot, "Details", self.toggle_details, width=84, height=28)
        self.details_button.grid(row=0, column=2)
        self.details = ctk.CTkTextbox(self.root, height=DETAILS_HEIGHT, fg_color=T.CARD, border_color=T.BORDER,
                                      border_width=1, corner_radius=10, text_color=T.BODY, font=T.font(12),
                                      state='disabled', wrap='word')

    @staticmethod
    def _dated(source):
        return f"{source['label']}, data from {source['date']}" if source else "No data available"

    # --- small helpers -----------------------------------------------------------------------
    def say(self, text):
        """A line from the engine: into the details, onto the status line, into the progress bar."""
        self.details.configure(state='normal')
        self.details.insert('end', text + '\n')
        self.details.see('end')
        self.details.configure(state='disabled')
        if self.busy and text:
            value = fraction(text, self.at, photos=self.photos_running)
            if value is not None:
                self.at = value
                self.set_bar(value)
            self.status.configure(text=f"{round(self.at * 100)}%   {text}", text_color=T.BODY)

    def selected_slot(self):
        return next((s for s in self.slots if s.folder == self.selected), None)

    def tick(self):
        """Keep the suggested name at the current time until the user types their own."""
        if not self.name_edited and not self.busy:
            self.name.set(savedata.default_name())
        self.root.after(15000, self.tick)

    def show_path(self, text, colour):
        self.path_full = text
        self.path.configure(text_color=colour)
        self.fit_path()

    def fit_path(self):
        """The RPCS3 path, shortened in the middle when the box is too narrow for all of it."""
        room = self.path.winfo_width() / T.scaling(self.root) - 4
        if room < 40:                   # not laid out yet: the label's resize event calls this again
            self.path.configure(text=self.path_full)
            return
        self.path.configure(text=shorten(self.path_full, lambda text: T.text_width(self.root, text, 14) <= room))

    def set_bar(self, value):
        self.bar.configure(progress_color=T.ACCENT if value > 0 else T.CELL)    # no stub at zero
        self.bar.set(value)

    def resize(self, delta):
        """Make the window `delta` taller (negative: shorter again) so a panel that appears does
        not squeeze the cards. Returns what was actually applied: the screen may not have the room."""
        if self.root.state() != 'normal':
            return 0
        scale = T.scaling(self.root)
        width, height = round(self.root.winfo_width() / scale), round(self.root.winfo_height() / scale)
        new = max(MIN_HEIGHT, min(height + delta, T.screen_height(self.root) - 70))
        self.root.geometry(f"{width}x{new}")
        return new - height

    def toggle_details(self):
        self.details_open = not self.details_open
        if self.details_open:        # below the progress row
            self.details.pack(side='bottom', fill='x', padx=18, pady=(0, 12), before=self.foot)
            self.details_grown = self.resize(DETAILS_HEIGHT + 12)
        else:
            self.details.pack_forget()
            self.resize(-self.details_grown)
        self.details_button.configure(text="Hide details" if self.details_open else "Details")

    def show_banner(self, good, title, lines, buttons):
        self.hide_banner()
        self.banner.show(good, title, lines, buttons)
        self.banner.grid()
        self.root.update_idletasks()
        self.banner_grown = self.resize(round(self.banner.winfo_reqheight() / T.scaling(self.root)) + 10)

    def hide_banner(self):
        if self.banner.winfo_ismapped():
            self.banner.grid_remove()
            self.resize(-self.banner_grown)
        self.banner_grown = 0

    # --- RPCS3 and its rosters ------------------------------------------------------------------
    def browse(self):
        start = self.rpcs3.folder if self.rpcs3 else os.path.expanduser('~')
        path = filedialog.askopenfilename(parent=self.root, title="Where is rpcs3.exe?", initialdir=start,
                                          filetypes=[("RPCS3", "rpcs3.exe"), ("Programs", "*.exe")])
        if path:
            self.set_rpcs3(os.path.normpath(path))

    def set_rpcs3(self, path, quiet=False):
        """Find the saves behind `path` (rpcs3.exe or its folder) and list the rosters."""
        self.rpcs3, self.slots, self.usable, problem = None, [], {}, None
        if path:
            try:
                self.rpcs3 = savedata.find_rpcs3(path)
            except (savedata.Rpcs3Error, OSError) as err:
                problem = str(err)
        if self.rpcs3:
            self.slots = savedata.list_rosters(self.rpcs3.savedata)
            for s in self.slots:
                try:
                    layout.check_base(Roster(s.sys_data))
                    self.usable[s.folder] = None
                except (layout.LayoutError, ValueError, KeyError) as err:
                    self.usable[s.folder] = str(err)
            self.settings['rpcs3'] = self.rpcs3.exe
            self.settings.pop('folder', None)
            save_settings(self.settings)
            running = " RPCS3 is running." if savedata.running_rpcs3() else ""
            self.show_path(self.rpcs3.exe, T.TEXT)
            self.rpcs3_note.configure(
                text=f"Found {len(self.slots)} roster{'s' if len(self.slots) != 1 else ''} of NHL Legacy.{running}",
                text_color=T.GREEN)
            self.find.grid_remove()
            self.change.grid(row=0, column=1, padx=(10, 0))
        else:
            self.show_path("Not set yet", T.FAINT)
            self.rpcs3_note.configure(
                text=problem if problem and not quiet else
                "Pick the file rpcs3.exe in your RPCS3 folder. The program finds your saves from there.",
                text_color=T.RED if problem and not quiet else T.MUTED)
            self.change.grid_remove()
            self.find.grid(row=0, column=1, padx=(10, 0))
        self.list_rosters()

    def list_rosters(self):
        for row in self.rows.values():
            row.destroy()
        self.rows = {}
        if not self.slots:
            self.roster_list.pack_forget()
            self.roster_empty.pack(fill='both', expand=True, pady=24)
            self.selected = None
            self.refresh_state()
            return
        self.roster_empty.pack_forget()
        self.roster_list.pack(fill='both', expand=True)
        for s in self.slots:
            problem = self.usable[s.folder]
            row = RosterRow(self.roster_list, s.name, f"Saved {friendly_date(s.modified)}   |   {s.folder}",
                            chip=("made here", 'made') if s.tool_made and problem is None else None,
                            problem=short_reason(problem) if problem else None,
                            command=lambda folder=s.folder: self.select(folder))
            row.pack(fill='x', pady=(0, 5), padx=(1, 10))
            self.rows[s.folder] = row
        keep = self.selected if self.selected in self.rows and self.usable.get(self.selected) is None else None
        self.select(keep or next((s.folder for s in self.slots if self.usable[s.folder] is None), None))
        self.root.after(50, self.reveal_selected)

    def reveal_selected(self):
        """Scroll the roster list so the selected roster can be seen (the list is rebuilt after an update)."""
        row = self.rows.get(self.selected)
        canvas = getattr(self.roster_list, '_parent_canvas', None)
        if row is None or canvas is None or not row.winfo_exists():
            return
        self.root.update_idletasks()
        total = max(1, self.roster_list.winfo_height())
        top, bottom = canvas.yview()
        start, end = row.winfo_y() / total, (row.winfo_y() + row.winfo_height()) / total
        if start < top or end > bottom:
            canvas.yview_moveto(max(0.0, start - 0.02))

    def select(self, folder):
        if self.busy:
            return
        self.selected = folder
        for name, row in self.rows.items():
            row.select(name == folder)
        self.refresh_state()

    def refresh_state(self):
        slot = self.selected_slot()
        ready = slot is not None and not self.busy
        if slot is not None:
            target = savedata.next_free(self.rpcs3.savedata, slot.title_id)
            self.name_note.configure(text=f"Saved as a new roster next to the others (folder {target}). "
                                          f"\"{slot.name}\" and your other rosters are not changed.")
        else:
            self.name_note.configure(text="This is the name you will see in the game's Load Roster list.")
        any_step = any(v.get() for v in self.steps.values())
        self.go.enable(ready and any_step)
        if not self.busy and not self.banner.winfo_ismapped():
            self.status.configure(text_color=T.MUTED,
                                  text="Ready." if ready and any_step else
                                  "Start with step 1: find rpcs3.exe." if self.rpcs3 is None else
                                  "Switch on at least one thing to update." if slot is not None else
                                  "None of the rosters found can be updated.")
        for row in self.switches:
            row.enable(not self.busy)
        self.name_entry.configure(state='normal' if not self.busy else 'disabled')
        self.change.configure(state='normal' if not self.busy else 'disabled')
        self.settings['steps'] = {k: v.get() for k, v in self.steps.items()}
        self.settings['steps'][PHOTOS] = self.photos.get()
        self.settings['steps'][EDITS] = self.use_edits.get()
        if art_installed():
            self.remove_art.pack(side='bottom', anchor='w', pady=(6, 0))
            self.remove_art.configure(state='normal' if not self.busy else 'disabled')
        else:
            self.remove_art.pack_forget()

    # --- the update ------------------------------------------------------------------------------
    def start(self):
        slot = self.selected_slot()
        steps = [s for s in self.steps if self.steps[s].get()]
        if slot is None or self.busy or not steps:
            return
        save_settings(self.settings)
        name = self.name.get().strip() if self.name_edited else savedata.default_name()
        self.busy, self.at, self.last_report = True, 0.0, None
        self.hide_banner()
        self.set_bar(0)
        self.refresh_state()
        self.go.configure(text="Updating...")
        self.status.configure(text="0%   Starting...", text_color=T.BODY)
        self.say("")
        art = self.rpcs3 if self.photos.get() else None
        self.photos_running = art is not None
        mine = my_edits.load() if self.use_edits.get() else None
        threading.Thread(target=self.work, args=(self.rpcs3.savedata, slot.folder, steps, name, art, mine),
                         daemon=True).start()

    def work(self, folder, source, steps, name, art=None, mine=None):
        try:
            result = pipeline.update(folder, source, steps, name, lambda msg: self.queue.put(('say', msg)),
                                     art_rpcs3=art, my_edits=mine or None)
            self.queue.put(('done', (result, savedata.running_rpcs3() is not None)))
        except (layout.LayoutError, datasource.Offline, FileNotFoundError, ArtError) as err:
            self.queue.put(('error', str(err)))
        except Exception as err:      # anything unexpected: keep the details for a bug report
            path = datasource.app_dir('logs', 'error.log')
            with open(path, 'a', encoding='utf-8') as f:
                f.write(traceback.format_exc() + '\n')
            self.queue.put(('error', f"Something went wrong: {err}\nThe details were saved to {path}"))

    def poll(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == 'say':
                    self.say(payload)
                elif kind == 'error':
                    self.finish()
                    self.say(payload)
                    self.failed("Nothing was saved", [payload, "Your existing rosters are untouched."])
                elif kind == 'done':
                    self.finish()
                    self.report(*payload)
                elif kind == 'ui':           # the roster editor's worker hands back its result
                    payload()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def finish(self):
        self.busy = False
        self.go.configure(text="Update roster")
        self.set_rpcs3(self.rpcs3.exe if self.rpcs3 else None, quiet=True)

    def failed(self, title, lines):
        self.set_bar(0)
        self.status.configure(text="Nothing was saved.", text_color=T.RED)
        self.show_banner(False, title, lines,
                         [("Show details", self.toggle_details)] if not self.details_open else [])

    def report(self, result, rpcs3_running):
        self.last_report = result.report_path
        lines = result.build.summary()
        for line in lines:
            self.say(line)
        if result.slot is None:
            problems = result.build.problems
            for p in problems[:15]:
                self.say("   - " + p)
            self.failed("The new roster failed the safety checks, so nothing was saved",
                        problems[:3] + ["Your existing rosters are untouched."])
            return
        thin = result.build.info.get('thinner_ahl_teams') or []
        if thin:
            self.say(f"Note: {len(thin)} AHL teams lost players to NHL rosters and are short-handed. "
                     "Switch on \"AHL rosters\" to fill them with their real players.")
        art = result.art_line()
        if art:
            self.say(art)
        self.say(f"Done. {HOW_TO_LOAD}")
        self.name_edited = False
        self.set_bar(1)
        self.status.configure(text=f"Done: saved as \"{result.slot.name}\".", text_color=T.GREEN)
        buttons = [("List of changes", self.show_report), ("Open save folder", self.show_folder)]
        if not rpcs3_running:
            buttons.append(("Start RPCS3", self.start_rpcs3))
        lines = [result.build.headline()] + ([art] if art else []) + [HOW_TO_LOAD]
        self.show_banner(True, f"Saved as \"{result.slot.name}\"", lines, buttons)
        self.refresh_state()

    def tab_changed(self):
        if self.tabs.get() == EDITOR_TAB:
            self.editor.opened()

    def remove_photos(self):
        """Put back every game file the photos and logos replaced."""
        if self.busy:
            return
        messages = []
        try:
            remove_art(say=messages.append)
        except ArtError as err:
            self.show_banner(False, "The photos and logos are still there", [str(err)], [])
            return
        for m in messages:
            self.say(m)
        self.show_banner(True, "Photos and logos removed",
                         messages + ["The game shows its own pictures again. Your rosters are not changed."], [])
        self.refresh_state()

    def show_folder(self):
        if self.rpcs3:
            os.startfile(self.rpcs3.savedata)

    def show_report(self):
        if self.last_report and os.path.exists(self.last_report):
            os.startfile(self.last_report)

    def start_rpcs3(self):
        if self.rpcs3 and not savedata.running_rpcs3():
            subprocess.Popen([self.rpcs3.exe], cwd=self.rpcs3.folder)


def main():
    ctk.set_appearance_mode('dark')
    root = ctk.CTk(fg_color=T.BG)
    T.load_fonts(root)
    icon = os.path.join(T.DATA, 'app.ico')
    if os.name == 'nt' and os.path.exists(icon):
        root.after(250, lambda: root.iconbitmap(icon))      # after the toolkit has set its own
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
