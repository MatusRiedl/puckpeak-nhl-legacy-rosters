"""The window: say where RPCS3 is, pick a roster, switch on what to update, press one button."""
import datetime
import json
import os
from collections import Counter
import queue
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox

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
from .stock import StockError
from .widgets import Banner, Card, Choice, GhostButton, PrimaryButton, RosterRow, SwitchRow, configure_if_changed, flag_image

SETTINGS = 'settings.json'
PHOTOS = 'photos'           # the "Photos and logos" switch in the remembered settings
EDITS = 'edits'             # the "My edits" switch
SAVE_BOTH = 'save_both'     # "Save for: EU + NA" (remembered; a single version follows the roster picked)
BOTH = "EU + NA"
SAVE_MODE = 'save_mode'     # how an update is saved (remembered): IN_PLACE or AS_NEW
IN_PLACE, AS_NEW = 'update', 'new'
UPDATE_TAB, EDITOR_TAB = "Update", "Roster editor"
MIN_HEIGHT = 640
SHORT_SCREEN = 900          # screens shorter than this (window units) show the result lines scrolling
BANNER_LINES_SHORT = 64     # ... in this much height (about three lines)
BANNER_LINES_MIN = 40       # the least height the result's lines get when the window has no more room
DETAILS_HEIGHT = 150
ROSTER_MIN = 150            # the roster list (step 2) never gets less than this (window units), result shown or not
SITE = "https://www.puckpeak.com"
SITE_LABEL = "www.puckpeak.com"
TAGLINE = "NHL & hockey analytics like never before"
HOW_TO_LOAD ="In the game: Roster Management > Load Roster, pick it, then save the roster once so it stays active."
HOW_TO_LOAD_IN_PLACE = ("In the game: start it. If this is not the roster in use, Roster Management > Load Roster, pick it, "
                        "then save the roster once.")


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
    if 'custom copies' in problem:
        return "Cannot be used: its teams are laid out differently from the community roster."
    return "Cannot be used: " + problem.split('. ')[0].rstrip('.') + "."


# the game's own roster (savedata.DiscSlot), as its row in the list says it
BIN_NAME = "Recycle Bin" if savedata.WINDOWS else "Trash"
DISC_NOTE = "From your game disc: the 2014-15 players, brought up to today"


class App:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.queue = queue.Queue()
        self.rpcs3 = None           # savedata.Rpcs3 once the program has been found
        self.versions = []          # the versions of the game that RPCS3 has (title ids)
        self.save_pick = BOTH if self.settings.get(SAVE_BOTH) else None   # "Save for", when chosen
        self.save_mode = AS_NEW if self.settings.get(SAVE_MODE) == AS_NEW else IN_PLACE   # the owner's default: update
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
        self.scanning = False       # the rosters are being read (in the background)
        self.checked = {}           # (SYS-DATA path, size, time) -> None or why it cannot be used
        self._status = None         # what the status line shows: (text, colour)
        self._bar_colour = None
        try:
            self.pack = datasource.load_pack(offline=True)
        except datasource.Offline:
            self.pack = {}

        root.title(f"Puck Peak  -  Legacy Roster Updater {__version__}")
        # as tall as the content likes, but never taller than the screen (768-line laptops)
        room = T.screen_height(root) - 90
        root.geometry(f"1000x{max(MIN_HEIGHT, min(780, room))}")
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
        body.rowconfigure(1, weight=1, minsize=round(ROSTER_MIN * T.scaling(root)))
        self.body = body
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
        self.set_rpcs3(self.settings.get('rpcs3') or self.settings.get('folder') or savedata.running_rpcs3()
                       or savedata.default_rpcs3(), quiet=True)
        self.tick()
        self.poll()

    # --- building the window ----------------------------------------------------------------
    def _header(self):
        head = ctk.CTkFrame(self.root, fg_color='transparent')
        head.pack(fill='x', pady=(12, 0))
        logo = self.logo = tk.Label(head, image=T.logo(self.root), bg=T.BG, bd=0, cursor='hand2')
        logo.pack()
        logo.bind('<Button-1>', lambda _e: open_site())
        link = ctk.CTkLabel(head, text=f"{TAGLINE}   ·   {SITE_LABEL}", font=T.font(14, 'semibold'),
                            text_color=T.ACCENT, cursor='hand2')
        link.pack(pady=(0, 2))
        self.site_link, self.compact = link, False
        link.bind('<Button-1>', lambda _e: open_site())
        link.bind('<Enter>', lambda _e: link.configure(font=T.font(14, 'semibold', underline=True)))
        link.bind('<Leave>', lambda _e: link.configure(font=T.font(14, 'semibold')))
        line = self.title_line = ctk.CTkFrame(head, fg_color='transparent')
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
        self.find = PrimaryButton(row, "Find rpcs3.exe" if savedata.WINDOWS else "Find RPCS3", self.browse, width=150,
                                  height=40)
        self.rpcs3_note = ctk.CTkLabel(card.body, text="", font=T.font(13), text_color=T.MUTED, anchor='w',
                                       justify='left', wraplength=470)
        self.rpcs3_note.pack(fill='x', pady=(8, 0))
        # no RPCS3 here (CrossOver, Wine, saves copied from elsewhere): the saves themselves will do
        other = ctk.CTkLabel(card.body, text="No RPCS3 on this computer? Pick a folder with roster saves instead.",
                             font=T.font(13, 'semibold'), text_color=T.ACCENT, anchor='w', cursor='hand2')
        other.pack(fill='x', pady=(4, 0))
        other.bind('<Button-1>', lambda _e: self.browse_saves())
        other.bind('<Enter>', lambda _e: other.configure(font=T.font(13, 'semibold', underline=True)))
        other.bind('<Leave>', lambda _e: other.configure(font=T.font(13, 'semibold')))
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
                 pipeline.NATIONAL: self._dated(sources.get('iihf')),
                 pipeline.SCHEDULE: "The real games and dates for Season mode, 30 teams. A test: not played yet"}
        remembered = self.settings.get('steps', {})
        available = pipeline.steps_for(self.pack)
        later = [name.split(' (')[0] for name in pipeline.planned(self.pack)]
        if later:
            ctk.CTkLabel(card.body, text="Coming later:  " + "  ·  ".join(later), font=T.font(12),
                         text_color=T.FAINT, anchor='w', justify='left', wraplength=380
                         ).pack(side='bottom', fill='x', pady=(4, 0))
        # shown only while photos and logos are installed
        self.remove_art = GhostButton(card.body, "Restore the game's own pictures", self.remove_photos, height=28)
        # the list scrolls: on a small screen, or once more leagues are available than fit
        rows = ctk.CTkScrollableFrame(card.body, fg_color='transparent', height=96,
                                      scrollbar_button_color=T.BORDER_STRONG, scrollbar_button_hover_color=T.FAINT)
        rows.pack(fill='both', expand=True)
        self.steps, self.switches = {}, []
        for step in available:
            var = tk.BooleanVar(value=remembered.get(step, step in pipeline.default_steps(self.pack)))
            self.steps[step] = var
            row = SwitchRow(rows, pipeline.STEP_LABELS[step], notes.get(step) or self._dated(sources.get(step)),
                            var, self.refresh_state, extra=pipeline.left_out_note(self.pack, step))
            row.pack(fill='x', pady=(0, 5), padx=(1, 10))
            self.switches.append(row)
        bundled = PhotoPack.open()
        self.photos = tk.BooleanVar(value=remembered.get(PHOTOS, bundled is not None))
        note = (f"{len(bundled):,} photos and logos inside this program ({bundled.built}); new players' "
                "are downloaded" if bundled else "Current photos and club logos (downloaded), and the clubs' real names")
        row = SwitchRow(rows, "Photos, logos and team names", note, self.photos, self.refresh_state,
                        extra="RPCS3 must be closed. The game's own pictures are kept and can be put back.")
        row.pack(fill='x', pady=(0, 5), padx=(1, 10))
        self.switches.append(row)
        self.photos_row = row               # needs RPCS3: off for a plain save folder (savedata.SaveFolder)
        self.use_edits = tk.BooleanVar(value=remembered.get(EDITS, True))
        row = SwitchRow(rows, "My edits", "Your changes from the Roster editor, applied after the update",
                        self.use_edits, self.refresh_state,
                        extra="Kept on this PC, so the next download does not undo them.")
        row.pack(fill='x', pady=(0, 5), padx=(1, 10))
        self.switches.append(row)
        return card

    def _card_name(self, master):
        card = Card(master, 4, "Save")
        self.mode_choice = Choice(card.body, [(IN_PLACE, "Update this roster", None), (AS_NEW, "Save as a new roster", None)],
                                  self.pick_save_mode)
        self.mode_choice.pack(anchor='w', pady=(0, 8))
        row = ctk.CTkFrame(card.body, fg_color='transparent')
        row.pack(fill='x')
        row.columnconfigure(0, weight=1)
        self.name = tk.StringVar(value=savedata.default_name())
        self.name_entry = ctk.CTkEntry(row, textvariable=self.name, height=42, corner_radius=10, fg_color=T.CELL,
                                       border_color=T.BORDER, border_width=1, text_color=T.STRONG, font=T.font(15))
        self.name_entry.grid(row=0, column=0, sticky='ew')
        self.name_entry.bind('<Key>', lambda _e: setattr(self, 'name_edited', True))
        # shown only when RPCS3 has both versions of the game (refresh_state)
        self.save_for_label = ctk.CTkLabel(row, text="Save for", font=T.font(13), text_color=T.MUTED)
        self.save_for = Choice(row, [('EU', 'EU', flag_image('EU')), ('NA', 'NA', flag_image('NA')),
                                     (BOTH, BOTH, flag_image(('EU', 'NA')))], self.pick_save_for)
        self.go = PrimaryButton(row, "Update roster", self.start, width=190)
        configure_if_changed(self.go, text="Update roster")
        self.go.grid(row=0, column=3, padx=(12, 0))
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
    def say(self, *texts):
        """Lines from the engine: into the details, onto the status line, into the progress bar. Many
        at once (everything that came in since the last look) cost one redraw, not one each."""
        if not texts:
            return
        self.details.configure(state='normal')
        self.details.insert('end', ''.join(t + '\n' for t in texts))
        self.details.see('end')
        self.details.configure(state='disabled')
        last = next((t for t in reversed(texts) if t), None)
        if self.busy and last:
            for text in texts:
                value = fraction(text, self.at, photos=self.photos_running) if text else None
                if value is not None:
                    self.at = value
            self.set_bar(self.at)
            self.set_status(f"{round(self.at * 100)}%   {last}", T.BODY)

    def set_status(self, text, colour=T.MUTED):
        """The line at the bottom (set only here, and only when it changes)."""
        if self._status != (text, colour):
            self._status = (text, colour)
            self.status.configure(text=text, text_color=colour)

    def clear_details(self):
        self.details.configure(state='normal')
        self.details.delete('1.0', 'end')
        self.details.configure(state='disabled')

    def selected_slot(self):
        return next((s for s in self.slots if s.folder == self.selected), None)

    def in_place(self, slot=None):
        """Is the roster picked updated in place? (The game's own roster is no save: it is always a new roster.)"""
        slot = slot or self.selected_slot()
        return self.save_mode == IN_PLACE and slot is not None and not getattr(slot, 'disc', False)

    def pick_save_mode(self, value):
        self.save_mode = value
        self.settings[SAVE_MODE] = value
        save_settings(self.settings)
        self.name_edited = False
        self.refresh_state()

    def tick(self):
        """Keep the suggested name at the current time until the user types their own."""
        if not self.name_edited and not self.busy and not self.in_place():
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
        colour = T.ACCENT if value > 0 else T.CELL      # no stub at zero
        if colour != self._bar_colour:
            self._bar_colour = colour
            self.bar.configure(progress_color=colour)
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

    def show_banner(self, good, title, lines, buttons, items=()):
        """Show the result box. One already showing (the last result, dimmed during the update) gets
        the new content, and the window changes its height once, by the difference."""
        scale = T.scaling(self.root)
        shown = self.banner.winfo_ismapped()
        before = round(self.banner.winfo_reqheight() / scale) + 10 if shown else 0
        self.banner.show(good, title, lines, buttons, items)
        # a short screen (a 768-line laptop) has no room for every line: they scroll there
        self.banner.fit(BANNER_LINES_SHORT if T.screen_height(self.root) < SHORT_SCREEN else None)
        if not shown:
            self.banner.grid()
        self.root.update_idletasks()
        delta = round(self.banner.winfo_reqheight() / scale) + 10 - before
        if delta:
            got = self.resize(delta)
            self.banner_grown += got
            if got < delta:             # a maximised window or a short screen: the big logo folds away
                self.compact_header(True)
        self.fit_banner()

    def fit_banner(self):
        """The result's lines get only the height the steps leave free (they scroll in it), so the
        rosters and every step stay in view (owner, 0.8.0: in a maximised window the result squeezed
        the roster list away)."""
        if not self.banner.winfo_ismapped():
            return
        for _ in range(3):              # the box's own size changes the layout around it: settle in a few steps
            self.root.update_idletasks()
            over = (self.body.winfo_reqheight() - self.body.winfo_height()) / T.scaling(self.root)
            if over <= 1 or self.banner.lines_height <= BANNER_LINES_MIN:
                break
            self.banner.fit(max(BANNER_LINES_MIN, self.banner.lines_height - over))

    def compact_header(self, on):
        """Fold the big Puck Peak logo and its link line away (on) or show them again."""
        if on == self.compact:
            return
        self.compact = on
        if on:
            self.logo.pack_forget()
            self.site_link.pack_forget()
        else:
            self.logo.pack(before=self.title_line)
            self.site_link.pack(pady=(0, 2), before=self.title_line)

    def hide_banner(self):
        if self.banner.winfo_ismapped():
            self.banner.grid_remove()
            self.resize(-self.banner_grown)
        self.banner_grown = 0
        self.compact_header(False)

    # --- RPCS3 and its rosters ------------------------------------------------------------------
    def browse(self):
        start = self.rpcs3.folder if self.rpcs3 else os.path.expanduser('~')
        if savedata.WINDOWS:
            path = filedialog.askopenfilename(parent=self.root, title="Where is rpcs3.exe?", initialdir=start,
                                              filetypes=[("RPCS3", "rpcs3.exe"), ("Programs", "*.exe")])
        else:       # Linux, Mac: RPCS3 keeps its data in a folder of its own, which is what the program needs
            path = filedialog.askdirectory(parent=self.root, initialdir=start, mustexist=True,
                                           title="Where is RPCS3's folder? (" + ", ".join(savedata.data_folders()) + ")")
        if path:
            self.set_rpcs3(os.path.normpath(path))

    def browse_saves(self):
        """Pick a folder with roster saves (or one roster save) instead of RPCS3."""
        start = self.rpcs3.savedata if self.rpcs3 else os.path.expanduser('~')
        path = filedialog.askdirectory(parent=self.root, initialdir=start, mustexist=True,
                                       title="Pick the folder with your NHL Legacy roster saves (or one roster save)")
        if path:
            self.set_rpcs3(os.path.normpath(path))

    def set_rpcs3(self, path, quiet=False):
        """Find the saves behind `path` (RPCS3 or its folder) and list the rosters. Reading the
        saves takes a moment each, so it happens in the background; the window stays as it is
        meanwhile, and saves already read (same file, size and time) are not read again."""
        self.scanning = True
        if path and not self.slots:
            configure_if_changed(self.rpcs3_note, text="Looking for your rosters...", text_color=T.MUTED)
        self.refresh_state()
        checked = dict(self.checked)

        def scan():
            found, slots, usable, versions, problem, picked = None, [], {}, [], None, None
            if path:
                try:
                    found = savedata.find_rpcs3(path)
                except (savedata.Rpcs3Error, OSError) as err:
                    try:                    # not RPCS3: a folder with roster saves will do (savedata.SaveFolder)
                        found, picked = savedata.open_saves(path)
                    except (FileNotFoundError, OSError):
                        problem = str(err) + " Or pick a folder with roster saves (the link below)."
            if found:
                slots = savedata.list_rosters(found.savedata)
                versions = found.games()
                for s in found.disc_slots():        # the game's own roster: always usable, read when used
                    usable[s.folder] = None
                for s in slots:
                    try:
                        st = os.stat(s.sys_data)
                        key = (s.sys_data, st.st_size, st.st_mtime_ns)
                    except OSError:
                        key = None
                    if key not in checked:
                        try:
                            layout.check_base(Roster(s.sys_data))
                            checked[key] = None
                        except (layout.LayoutError, ValueError, KeyError, OSError) as err:
                            checked[key] = str(err)
                    usable[s.folder] = checked[key]
                slots = slots + found.disc_slots()
            running = savedata.running_rpcs3() is not None if found else False
            self.queue.put(('ui', lambda: self._scanned(found, slots, usable, versions, problem, quiet, running,
                                                        checked, picked)))
        threading.Thread(target=scan, daemon=True).start()

    def _scanned(self, found, slots, usable, versions, problem, quiet, running, checked, picked=None):
        """The rosters read by set_rpcs3, shown (on the window's thread). `picked`: the roster save
        the player pointed at directly, selected."""
        self.scanning = False
        if picked:
            self.selected = picked
        self.checked = checked
        self.rpcs3, self.slots, self.usable, self.versions = found, slots, usable, versions
        if self.rpcs3:
            self.settings['rpcs3'] = self.rpcs3.where
            self.settings.pop('folder', None)
            save_settings(self.settings)
            if self.path_full != self.rpcs3.where:
                self.show_path(self.rpcs3.where, T.TEXT)
            configure_if_changed(self.rpcs3_note, text=self.found_text() + (" RPCS3 is running." if running else ""),
                                 text_color=T.GREEN)
            if self.find.winfo_manager():
                self.find.grid_remove()
            if not self.change.winfo_manager():
                self.change.grid(row=0, column=1, padx=(10, 0))
        else:
            self.show_path("Not set yet", T.FAINT)
            configure_if_changed(
                self.rpcs3_note,
                text=problem if problem and not quiet else
                savedata.PICK_RPCS3 + " The program finds your saves from there.",
                text_color=T.RED if problem and not quiet else T.MUTED)
            if self.change.winfo_manager():
                self.change.grid_remove()
            if not self.find.winfo_manager():
                self.find.grid(row=0, column=1, padx=(10, 0))
        self.list_rosters()

    def found_text(self):
        """'Found 9 rosters of NHL Legacy: 8 EU, 1 NA.' and a word on a version without rosters."""
        saves = [s for s in self.slots if not getattr(s, 'disc', False)]
        if self.rpcs3 is not None and self.rpcs3.plain:
            n = len(saves)
            return (f"Found {n} roster{'s' if n != 1 else ''} of NHL Legacy in this folder. Without RPCS3 the new roster "
                    "is saved next to them; photos and the game's own roster need RPCS3.")
        if not saves:
            return ("No roster is saved in RPCS3 yet. Start from the game's own roster (listed below): it is "
                    "made from your game disc and brought up to today.")
        n = len(saves)
        count = Counter(s.region for s in saves)
        parts = ", ".join(f"{k} {r}" for r, k in sorted(count.items(), key=lambda kv: (kv[0] != 'EU', kv[0])))
        text = f"Found {n} roster{'s' if n != 1 else ''} of NHL Legacy" + (f": {parts}." if parts else ".")
        empty = [savedata.region(t) for t in self.versions if not count[savedata.region(t)]]
        if empty:
            text += (f" Your {empty[0]} game has no roster yet: \"Save for\" below can make one from an "
                     f"{'NA' if empty[0] == 'EU' else 'EU'} roster.")
        return text

    def save_targets(self, slot=None):
        """The versions of the game (title ids) the new roster is saved for."""
        slot = slot or self.selected_slot()
        if slot is None:
            return []
        if self.in_place(slot):
            return [slot.title_id]
        if len(self.versions) < 2 or self.save_pick in (None, slot.region):
            return [slot.title_id]
        if self.save_pick == BOTH:
            return sorted(set(self.versions) | {slot.title_id}, key=lambda t: (t != slot.title_id, t))
        return [savedata.title_of(self.save_pick)]

    def pick_save_for(self, value):
        self.save_pick = value
        self.settings[SAVE_BOTH] = value == BOTH
        save_settings(self.settings)
        self.refresh_state()

    def list_rosters(self):
        """One row per roster. Rows that are still the same stay as they are (rebuilding the list
        made it flash after every update); only new or changed rosters get a new row."""
        if not self.slots:
            for row in self.rows.values():
                row.destroy()
            self.rows = {}
            if self.roster_list.winfo_manager():
                self.roster_list.pack_forget()
            if not self.roster_empty.winfo_manager():
                self.roster_empty.pack(fill='both', expand=True, pady=24)
            self.selected = None
            self.refresh_state()
            return
        if self.roster_empty.winfo_manager():
            self.roster_empty.pack_forget()
        if not self.roster_list.winfo_manager():
            self.roster_list.pack(fill='both', expand=True)
        wanted = {}
        for s in self.slots:
            problem = self.usable[s.folder]
            if getattr(s, 'disc', False):
                wanted[s.folder] = (s.name, DISC_NOTE, ("start fresh", 'muted'), None, s.region, False)
                continue
            wanted[s.folder] = (s.name, f"{s.folder}  |  {friendly_date(s.modified)}",
                                ("made here", 'made') if s.tool_made and problem is None else None,
                                short_reason(problem) if problem else None, s.region, True)
        for folder in [f for f, row in self.rows.items() if wanted.get(f) != row.shows]:
            self.rows.pop(folder).destroy()
        order = [s.folder for s in self.slots]
        for k, folder in enumerate(order):
            if folder in self.rows:
                continue
            title, note, chip, problem, region, actions = wanted[folder]
            row = RosterRow(self.roster_list, title, note, chip=chip, problem=problem,
                            command=lambda f=folder: self.select(f), region=region,
                            on_open=(lambda f=folder: self.open_save(f)) if actions else None,
                            on_delete=(lambda f=folder: self.ask_delete(f)) if actions else None)
            row.shows = wanted[folder]
            after = next((self.rows[f] for f in order[k + 1:] if f in self.rows), None)
            row.pack(fill='x', pady=(0, 5), padx=(1, 10), **({'before': after} if after else {}))
            self.rows[folder] = row
        keep = self.selected if self.selected in self.rows and self.usable.get(self.selected) is None else None
        first = next((s.folder for s in self.slots if self.usable[s.folder] is None and not getattr(s, 'disc', False)),
                     next((s.folder for s in self.slots if self.usable[s.folder] is None), None))
        self.select(keep or first)
        self.root.after(50, self.reveal_selected)

    def slot_of(self, folder):
        return next((s for s in self.slots if s.folder == folder), None)

    def open_save(self, folder):
        """Show one roster save's own folder in the file manager."""
        slot = self.slot_of(folder)
        if slot is not None and os.path.isdir(slot.path):
            savedata.open_path(slot.path)

    def ask_delete(self, folder):
        """Ask in the result box before a roster save goes to the Recycle Bin."""
        slot = self.slot_of(folder)
        if slot is None or getattr(slot, 'disc', False) or self.busy or self.scanning:
            return
        if savedata.running_rpcs3():
            self.show_banner(False, "Close RPCS3 first", ["A roster can only be removed while the game is closed."], [])
            return
        self.show_banner(
            False, f"Move \"{slot.name}\" to the {BIN_NAME}?",
            [f"{slot.region} game, folder {slot.folder}, saved {friendly_date(slot.modified)}.",
             f"You can take it out of the {BIN_NAME} again. Your other rosters are not changed."],
            [(f"Move to the {BIN_NAME}", lambda: self.delete_save(folder)), ("Keep it", self.hide_banner)])

    def delete_save(self, folder):
        slot = self.slot_of(folder)
        if slot is None or getattr(slot, 'disc', False) or self.busy or self.scanning or self.rpcs3 is None:
            return
        if getattr(self.editor, 'busy', False):
            self.show_banner(False, "The roster was not removed",
                             ["The Roster editor is working. Try again in a moment."], [])
            return
        try:
            savedata.trash_save(self.rpcs3.savedata, folder)
        except savedata.DeleteError as err:
            self.show_banner(False, "The roster was not removed", [str(err)], [])
            return
        if self.editor.source and self.editor.source[1] == folder:
            self.editor.source = None               # an update may give the same folder name to a new roster
        self.slots = [s for s in self.slots if s.folder != folder]
        if self.selected == folder:
            self.selected = None
        self.say(f"Moved the roster \"{slot.name}\" ({folder}) to the {BIN_NAME}.")
        self.show_banner(True, f"\"{slot.name}\" is in the {BIN_NAME}",
                         [f"The {slot.region} roster in folder {folder} was removed from the game's saves. "
                          f"Take it out of the {BIN_NAME} to get it back."], [])
        self.list_rosters()
        self.set_rpcs3(self.rpcs3.where, quiet=True)

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
        if folder != self.selected and self.save_pick != BOTH:
            self.save_pick = None           # a single version follows the roster picked
        if folder != self.selected and self.save_mode == IN_PLACE:
            self.name_edited = False        # the name box shows the roster picked
        self.selected = folder
        for name, row in self.rows.items():
            row.select(name == folder)
        self.refresh_state()

    def refresh_state(self):
        """Bring every control in line with the state. Runs on every click, so it only touches what
        actually changes (each change redraws a widget)."""
        slot = self.selected_slot()
        ready = slot is not None and not self.busy and not self.scanning
        for row in self.rows.values():
            row.enable_delete(not self.busy and not self.scanning)
        in_place = self.in_place(slot)
        self.mode_choice.set(IN_PLACE if in_place else AS_NEW if slot is not None else self.save_mode)
        self.mode_choice.enable(not self.busy)
        if slot is not None and len(self.versions) >= 2 and not in_place:
            if not self.save_for.winfo_manager():
                self.save_for_label.grid(row=0, column=1, padx=(12, 6))
                self.save_for.grid(row=0, column=2)
            self.save_for.set(self.save_pick or slot.region)
            self.save_for.enable(not self.busy)
        elif self.save_for.winfo_manager():
            self.save_for_label.grid_remove()
            self.save_for.grid_remove()
        if in_place:
            if not self.name_edited and self.name.get() != slot.name:
                self.name.set(slot.name)
            closed = " Make sure RPCS3 is closed." if self.rpcs3.plain else " RPCS3 must be closed."
            configure_if_changed(self.name_note, text=(
                f"\"{slot.name}\" ({slot.folder}, {slot.region}) gets the newest data; the name stays unless you change "
                f"it. The old roster is first copied to the program's backups folder (the last {savedata.KEEP_BACKUPS} "
                f"are kept).{closed}"))
        elif slot is not None:
            where = ", ".join(f"folder {savedata.next_free(self.rpcs3.savedata, t)} for the {savedata.region(t)} game"
                              for t in self.save_targets(slot))
            why = (" The game's own roster is always saved as a new roster." if getattr(slot, 'disc', False) and
                   self.save_mode == IN_PLACE else "")
            configure_if_changed(self.name_note, text=f"Saved as a new roster next to the others ({where}). "
                                                      f"\"{slot.name}\" and your other rosters are not changed.{why}")
        else:
            configure_if_changed(self.name_note, text="This is the name you will see in the game's Load Roster list.")
        any_step = any(v.get() for v in self.steps.values())
        self.go.enable(ready and any_step)
        if not self.busy:
            configure_if_changed(self.go, text="Update roster" if in_place else "Make new roster")
        if not self.busy and not self.banner.winfo_ismapped():
            self.set_status("Looking for your rosters..." if self.scanning else
                            "Ready." if ready and any_step else
                            "Start with step 1: find RPCS3." if self.rpcs3 is None else
                            "Switch on at least one thing to update." if slot is not None else
                            "None of the rosters found can be updated.")
        plain = self.rpcs3 is not None and self.rpcs3.plain
        for row in self.switches:
            row.enable(not self.busy and not (plain and row is self.photos_row))
        configure_if_changed(self.name_entry, state='normal' if not self.busy else 'disabled')
        configure_if_changed(self.change, state='normal' if not self.busy else 'disabled')
        self.settings['steps'] = {k: v.get() for k, v in self.steps.items()}
        self.settings['steps'][PHOTOS] = self.photos.get()
        self.settings['steps'][EDITS] = self.use_edits.get()
        if art_installed():
            if not self.remove_art.winfo_manager():
                self.remove_art.pack(side='bottom', anchor='w', pady=(6, 0))
            configure_if_changed(self.remove_art, state='normal' if not self.busy else 'disabled')
        elif self.remove_art.winfo_manager():
            self.remove_art.pack_forget()

    # --- the update ------------------------------------------------------------------------------
    def start(self):
        slot = self.selected_slot()
        steps = [s for s in self.steps if self.steps[s].get()]
        if slot is None or self.busy or self.scanning or not steps:
            return
        save_settings(self.settings)
        in_place = self.in_place(slot)
        if in_place and savedata.running_rpcs3():
            self.show_banner(False, "Close RPCS3 first", ["A roster can only be updated while the game is closed."], [])
            return
        if in_place and getattr(self.editor, 'busy', False):
            self.show_banner(False, "The roster was not updated", ["The Roster editor is working. Try again in a moment."], [])
            return
        if in_place:        # a rename only when the player changed the name
            name = self.name.get().strip() if self.name_edited and self.name.get().strip() != slot.name else None
        else:
            name = self.name.get().strip() if self.name_edited else savedata.default_name()
        self.busy, self.at, self.last_report = True, 0.0, None
        if self.banner.winfo_ismapped():     # the last result stays, greyed, so the window keeps its size
            self.banner.dim("Updating... (the last result is shown below until the new one is ready)")
        self.set_bar(0)
        self.refresh_state()
        configure_if_changed(self.go, text="Updating...")
        self.set_status("0%   Starting...", T.BODY)
        self.clear_details()
        art = self.rpcs3 if self.photos.get() and not self.rpcs3.plain else None
        self.photos_running = art is not None
        mine = (my_edits.load(), my_edits.load_teams()) if self.use_edits.get() else (None, None)
        threading.Thread(target=self.work, args=(self.rpcs3.savedata, slot, steps, name, art, mine,
                                                 self.save_targets(slot), in_place), daemon=True).start()

    def work(self, folder, slot, steps, name, art=None, mine=(None, None), targets=None, in_place=False):
        try:
            result = pipeline.update(folder, slot.folder, steps, name, lambda msg: self.queue.put(('say', msg)),
                                     art_rpcs3=art, my_edits=mine[0] or None, team_edits=mine[1] or None,
                                     targets=targets, disc=slot if getattr(slot, 'disc', False) else None,
                                     in_place=in_place)
            self.queue.put(('done', (result, savedata.running_rpcs3() is not None)))
        except (layout.LayoutError, datasource.Offline, FileNotFoundError, ArtError, StockError,
                savedata.InPlaceError) as err:
            self.queue.put(('error', str(err)))
        except Exception as err:      # anything unexpected: keep the details for a bug report
            path = datasource.app_dir('logs', 'error.log')
            with open(path, 'a', encoding='utf-8') as f:
                f.write(traceback.format_exc() + '\n')
            self.queue.put(('error', f"Something went wrong: {err}\nThe details were saved to {path}"))

    def poll(self):
        said = []           # the engine's lines since the last look: shown together
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == 'say':
                    said.append(payload)
                    continue
                self.say(*said)
                said = []
                if kind == 'error':
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
        self.say(*said)
        self.root.after(100, self.poll)

    def finish(self):
        self.busy = False
        self.set_rpcs3(self.rpcs3.where if self.rpcs3 else None, quiet=True)

    def failed(self, title, lines):
        self.set_bar(0)
        self.set_status("Nothing was saved.", T.RED)
        self.show_banner(False, title, lines,
                         [("Show details", self.toggle_details)] if not self.details_open else [])

    def report(self, result, rpcs3_running):
        self.last_report = result.report_path
        items = result.build.lines()
        self.say("", "What changed:", *(f"   {title}: {text}" for title, text in items))
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
        how = HOW_TO_LOAD_IN_PLACE if result.in_place else HOW_TO_LOAD
        self.say(f"Done. {how}")
        self.name_edited = False
        self.set_bar(1)
        buttons = [("List of changes", self.show_report), ("Open save folder", self.show_folder)]
        if result.in_place and result.backup:
            buttons.insert(1, ("Open backup folder", lambda: savedata.open_path(result.backup)))
        if not rpcs3_running and not self.rpcs3.plain:
            buttons.append(("Start RPCS3", self.start_rpcs3))
        name = result.slot.name
        if result.in_place:
            self.editor.source = None       # the editor shows what the file is now
            where = ("The roster is already the same as the new one: nothing was changed." if result.unchanged
                     else f"Updated: {result.saved_where()}.")
            lines = [where] + ([f"The old roster is kept in {result.backup}"] if result.backup else []) \
                + ([art] if art else []) + [how]
            title = f"Already up to date: \"{name}\"" if result.unchanged else f"Updated \"{name}\""
            self.set_status(f"Done: {'already up to date' if result.unchanged else 'updated'} \"{name}\".", T.GREEN)
        else:
            where = f"New save: {result.saved_where()}."
            lines = [where] + ([art] if art else []) + [how]
            title = f"Saved as \"{name}\""
            self.set_status(f"Done: saved as \"{name}\".", T.GREEN)
        self.say(where)
        self.show_banner(True, title, lines, buttons, items=items or [("Result", "Nothing needed changing.")])
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
        self.say(*messages)
        self.show_banner(True, "The game's own pictures are back",
                         messages + ["Your rosters are not changed."], [])
        self.refresh_state()

    def show_folder(self):
        if self.rpcs3:
            savedata.open_path(self.rpcs3.savedata)

    def show_report(self):
        if self.last_report and os.path.exists(self.last_report):
            savedata.open_path(self.last_report)

    def start_rpcs3(self):
        if self.rpcs3 and not savedata.running_rpcs3():
            self.rpcs3.start()


def main():
    ctk.set_appearance_mode('dark')
    root = ctk.CTk(fg_color=T.BG)
    if T.missing_files():
        root.withdraw()
        messagebox.showerror(
            "Legacy Roster Updater",
            "Some of this program's files are missing from the system's temporary folder. An antivirus "
            "or a cleaning program may have removed them.\n\n"
            "Close this message and start the program again. If it keeps happening, "
            "allow NHLLegacyRosterUpdater in your antivirus.", parent=root)
        root.destroy()
        return
    T.load_fonts(root)
    icon = os.path.join(T.DATA, 'app.ico')
    if os.name == 'nt' and os.path.exists(icon):
        root.after(250, lambda: root.iconbitmap(icon))      # after the toolkit has set its own
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
