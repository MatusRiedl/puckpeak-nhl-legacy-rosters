"""The Update tab without a window toolkit: say where RPCS3 is, pick a roster, switch on what to
update, press one button. `snapshot()` is everything the tab shows, as plain data; the methods are
its buttons. The same rules as the old window (gui.App), which this replaces."""
import os
import threading
import time

from .. import __version__, datasource, layout, pipeline, restore, savedata
from .. import edits as my_edits
from ..art.install import ArtError, installed as art_installed, remove as remove_art
from ..art.photopack import PhotoPack
from ..gui_state import is_current_scan
from ..progress import fraction
from ..roster import Roster
from ..stock import StockError
from . import jobs, selfupdate, settings as S, texts as X

SLICE = 'update'
_UNSET = object()


def _load_pack():
    try:
        return datasource.load_pack(offline=True)
    except datasource.Offline:
        return {}


class UpdateController:
    def __init__(self, host, settings=None, pack=None, photo_pack=_UNSET):
        self.host = host
        self.lock = threading.RLock()
        self.settings = S.load() if settings is None else settings
        self.pack = _load_pack() if pack is None else pack
        self.editor = None          # the Roster editor's controller, once there is one (it shares the save mode)
        self.rpcs3 = None           # savedata.Rpcs3 once the program has been found
        self.versions = []          # the versions of the game that RPCS3 has (title ids)
        self.slots = []
        self.usable = {}            # roster folder -> None when usable, else the reason it is not
        self.selected = None        # roster folder to start from
        self.problem = None         # why the path picked is not RPCS3 (shown in red)
        self.running = False        # RPCS3 runs (seen at the last scan)
        self.busy = False
        self.quitting = False       # the new version runs: this window must close, whatever it was doing
        self.scanning = False
        self.checked = {}           # (SYS-DATA path, size, time) -> None or why it cannot be used
        self._scan_id = 0
        self.at = 0.0               # progress of the running update, 0..1
        self.photos_running = False
        self.save_pick = S.BOTH if self.settings.get(S.SAVE_BOTH) else None
        self.save_mode = S.AS_NEW if self.settings.get(S.SAVE_MODE) == S.AS_NEW else S.IN_PLACE
        self.name = savedata.default_name()
        self.name_edited = False
        self.export_mode = bool(self.settings.get(S.EXPORT_ONLY))
        picked = self.settings.get(S.EXPORT_FILE)
        self.export_file = picked if picked and os.path.isfile(picked) else None
        self.export_problem = None
        self.result = None          # the result box (dict), or None
        self.status = None          # (text, tone) while busy or while a result shows; else worked out
        self.dialog = None
        self._answers = {}
        self.last_report = self._backup = self._export_folder = self._update_page = None
        self.art_installed = art_installed()

        remembered = self.settings.get('steps', {})
        self.step_keys = pipeline.steps_for(self.pack)
        defaults = pipeline.default_steps(self.pack)
        self.steps = {k: bool(remembered.get(k, k in defaults)) for k in self.step_keys}
        bundled = PhotoPack.open() if photo_pack is _UNSET else photo_pack
        self.photos = bool(remembered.get(S.PHOTOS, bundled is not None))
        self.use_edits = bool(remembered.get(S.EDITS, True))
        self.photos_note = (f"{len(bundled):,} photos and logos inside this program ({bundled.built}); new players' "
                            "are downloaded" if bundled else
                            "Current photos and club logos (downloaded), and the clubs' real names")
        self.marks = {}             # row key -> its part of restore.py ("Restore" pressed)

    # --- start --------------------------------------------------------------------------------------
    def start_up(self):
        """Find RPCS3 where it was last time (or where it runs / usually is)."""
        self.set_rpcs3(self.settings.get('rpcs3') or self.settings.get('folder') or savedata.running_rpcs3()
                       or savedata.default_rpcs3(), quiet=True)

    def changed(self):
        self.host.changed(SLICE)

    # --- a newer version of the program -----------------------------------------------------------------
    def check_for_update(self, force=False):
        """Look at GitHub in the background (at most every 12 hours, unless the player switched it off or
        `force`); a newer version is offered in a question. Never in the way: offline means silence."""
        with self.lock:
            if not force and not selfupdate.due(self.settings):
                return
        threading.Thread(target=self._look_for_update, args=(force,), daemon=True).start()

    def _look_for_update(self, force):
        release = selfupdate.latest()
        with self.lock:
            self.settings['update_checked'] = time.time()
            S.save(self.settings)
            if release is None and force:
                self.ask("You have the newest version", [f"Version {__version__} is the latest one."
                         " If you are offline, or GitHub did not answer, try again in a moment."],
                         [("OK", 'ok', 'primary')], {})
                return
            if release is None or (not force and self.settings.get('update_skipped') == release.text):
                return
            if self.busy or self.dialog:
                return                      # not in the middle of work; the next start asks again
            self._offer_update(release)

    def _offer_update(self, release):
        notes = [line.strip(' #*-') for line in release.notes.splitlines() if line.strip(' #*-')][:4]
        lines = [f"You have version {__version__}."] + notes
        if release.can_install() and selfupdate.can_replace():
            buttons = [("Update now", 'now', 'primary'), ("Later", 'later', 'plain'), ("Skip this version", 'skip', 'ghost')]
            lines.append("The program downloads the new version, restarts and keeps all your settings and rosters.")
            answers = {'now': lambda: self.install_update(release)}
        else:
            buttons = [("Open the download page", 'page', 'primary'), ("Later", 'later', 'plain'),
                       ("Skip this version", 'skip', 'ghost')]
            answers = {'page': lambda: self.host.open_url(release.page)}
        answers['skip'] = lambda: self._skip_update(release)
        self.ask(f"Version {release.text} is out", lines, buttons, answers)

    def _skip_update(self, release):
        with self.lock:
            self.settings['update_skipped'] = release.text
            S.save(self.settings)

    def install_update(self, release):
        with self.lock:
            if self.busy:
                return
            self.busy, self.at = True, 0.0
            self.status = ("Downloading the new version...", 'body')
            self.changed()

        def progress(value):
            with self.lock:
                self.at = value
                self.status = (f"{round(value * 100)}%   Downloading version {release.text}", 'body')
                self.changed()

        def work():
            try:
                selfupdate.install(release, progress)
            except Exception as err:
                with self.lock:
                    self.busy, self.at, self.status = False, 0.0, None
                    self.show_result(False, "The update did not work", [
                        str(err) if isinstance(err, ValueError) else "The new version could not be downloaded or put in place.",
                        "Nothing was changed: this version still works. You can download the new one from the release page."],
                        [("Open the download page", 'update_page')])
                    self._update_page = release.page
                return
            with self.lock:
                self.quitting, self.busy = True, False
            self.host.quit()

        threading.Thread(target=work, daemon=True).start()

    def set_check_updates(self, on):
        with self.lock:
            self.settings['check_updates'] = bool(on)
            S.save(self.settings)
            self.changed()

    def save_settings(self):
        self.settings['steps'] = dict(self.steps)
        self.settings['steps'][S.PHOTOS] = self.photos
        self.settings['steps'][S.EDITS] = self.use_edits
        S.save(self.settings)

    def tick(self):
        """Every 15 seconds: the suggested name keeps the current time until the player types their own."""
        with self.lock:
            if not self.name_edited and not self.busy and not self.in_place() and not self.export_mode:
                name = savedata.default_name()
                if name != self.name:
                    self.name = name
                    self.changed()

    # --- helpers ------------------------------------------------------------------------------------
    def say(self, *texts):
        """Lines from the engine: into the details, onto the status line, into the progress bar."""
        if not texts:
            return
        self.host.log(*texts)
        with self.lock:
            last = next((t for t in reversed(texts) if t), None)
            if self.busy and last:
                for text in texts:
                    value = fraction(text, self.at, photos=self.photos_running) if text else None
                    if value is not None:
                        self.at = value
                self.status = (f"{round(self.at * 100)}%   {last}", 'body')
                self.changed()

    def selected_slot(self):
        return next((s for s in self.slots if s.folder == self.selected), None)

    def slot_of(self, folder):
        return next((s for s in self.slots if s.folder == folder), None)

    def in_place(self, slot=None):
        """Is the roster picked updated in place? (The game's own roster is no save: always a new roster.)"""
        slot = slot or self.selected_slot()
        return self.save_mode == S.IN_PLACE and slot is not None and not getattr(slot, 'disc', False)

    def save_targets(self, slot=None):
        """The versions of the game (title ids) the new roster is saved for."""
        slot = slot or self.selected_slot()
        if slot is None:
            return []
        if self.in_place(slot):
            return [slot.title_id]
        if len(self.versions) < 2 or self.save_pick in (None, slot.region):
            return [slot.title_id]
        if self.save_pick == S.BOTH:
            return sorted(set(self.versions) | {slot.title_id}, key=lambda t: (t != slot.title_id, t))
        return [savedata.title_of(self.save_pick)]

    def editor_busy(self):
        return bool(self.editor is not None and getattr(self.editor, 'busy', False))

    def show_result(self, good, title, lines, buttons=(), items=()):
        self.result = {'good': good, 'title': title, 'lines': list(lines), 'items': [list(i) for i in items],
                       'buttons': [{'label': label, 'action': action} for label, action in buttons], 'dim': None}
        self.changed()

    def hide_result(self):
        with self.lock:
            self.result = None
            self.status = None if not self.busy else self.status
            self.changed()

    def ask(self, title, lines, buttons, answers):
        """A question in the page (Delete, Restore default...). `buttons`: (label, answer, style);
        `answers`: answer -> what to do."""
        ident = (self.dialog or {}).get('id', 0) + 1
        self.dialog = {'id': ident, 'title': title, 'lines': list(lines),
                       'buttons': [{'label': label, 'answer': answer, 'style': style} for label, answer, style in buttons]}
        self._answers = answers
        self.changed()

    def answer(self, ident, answer):
        with self.lock:
            if not self.dialog or self.dialog['id'] != ident:
                return
            todo = self._answers.get(answer)
            self.dialog, self._answers = None, {}
            self.changed()
        if todo:
            todo()

    # --- RPCS3 and its rosters ------------------------------------------------------------------------
    def pick_rpcs3(self):
        with self.lock:
            if self.busy or self.export_mode:
                return
            start = self.rpcs3.folder if self.rpcs3 else os.path.expanduser('~')
        if savedata.WINDOWS:
            path = self.host.ask_open("Where is rpcs3.exe?", ['RPCS3 (rpcs3.exe)', 'Programs (*.exe)'], start)
        else:       # Linux, Mac: RPCS3 keeps its data in a folder of its own, which is what the program needs
            path = self.host.ask_folder("Where is RPCS3's folder? (" + ", ".join(savedata.data_folders()) + ")", start)
        if path:
            self.set_rpcs3(os.path.normpath(path))

    def set_rpcs3(self, path, quiet=False):
        """Find the saves behind `path` (RPCS3 or its folder) and list the rosters, in the background;
        saves already read (same file, size and time) are not read again."""
        with self.lock:
            self._scan_id += 1
            scan_id = self._scan_id
            self.scanning = True
            checked = dict(self.checked)
            games = self.settings.get('games')
            self.changed()

        def scan():
            found, slots, usable, versions, problem, picked = None, [], {}, [], None, None
            if path:
                try:
                    found = savedata.find_rpcs3(path, games=games)
                except savedata.NoGameError as err:         # RPCS3 itself is fine: it only needs the game
                    found = err.rpcs3
                except (savedata.Rpcs3Error, OSError) as err:
                    try:                    # not RPCS3: a folder with roster saves will do (savedata.SaveFolder)
                        found, picked = savedata.open_saves(path)
                    except (FileNotFoundError, OSError):
                        problem = str(err)
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
            self._scanned(found, slots, usable, versions, problem, quiet, running, checked, picked, scan_id)

        jobs.run(scan, failed=lambda message: self._scan_failed(message, scan_id))

    def _scan_failed(self, message, scan_id):
        with self.lock:
            if not is_current_scan(scan_id, self._scan_id):
                return
            self.scanning = False
            self.problem = message
            self.changed()

    def _scanned(self, found, slots, usable, versions, problem, quiet, running, checked, picked, scan_id):
        with self.lock:
            if not is_current_scan(scan_id, self._scan_id):
                return
            self.scanning = False
            if picked:
                self.selected = picked
            self.checked = checked
            self.rpcs3, self.slots, self.usable, self.versions = found, slots, usable, versions
            self.problem = problem if problem and not quiet else None
            self.running = running
            if found:
                self.settings['rpcs3'] = found.where
                self.settings.pop('folder', None)
                S.save(self.settings)
            self.art_installed = art_installed()
            keep = self.selected if self.slot_of(self.selected) and self.usable.get(self.selected) is None else None
            first = next((s.folder for s in slots if usable[s.folder] is None and not getattr(s, 'disc', False)),
                         next((s.folder for s in slots if usable[s.folder] is None), None))
            self._select(keep or first)
            self.changed()

    def pick_game(self, folder=False):
        """The player points at the game (RPCS3 does not list it): the program keeps the place and looks again."""
        with self.lock:
            if not self.rpcs3 or self.busy:
                return
        start = os.path.expanduser('~')
        if folder:
            path = self.host.ask_folder("Pick the folder of your NHL Legacy game (it holds PS3_GAME)", start)
        else:
            path = self.host.ask_open("Pick your NHL Legacy game", ['Game disc image (*.iso)', 'All files (*.*)'], start)
        if not path:
            return
        title = savedata.game_title_id(os.path.normpath(path))
        with self.lock:
            if title not in savedata.GAMES:
                self.show_result(False, "Not NHL Legacy", ["That is not a copy of NHL Legacy Edition. Pick the game's "
                                                           ".iso file, or the folder that holds its PS3_GAME folder."])
                return
            self.settings.setdefault('games', {})[title] = os.path.normpath(path)
            S.save(self.settings)
            where = self.rpcs3.where
        self.set_rpcs3(where)

    def select(self, folder):
        with self.lock:
            if self.busy or self.slot_of(folder) is None or self.usable.get(folder) is not None:
                return
            self._select(folder)
            self.changed()

    def _select(self, folder):
        previous = self.selected
        if folder != previous and self.save_pick != S.BOTH:
            self.save_pick = None           # a single version follows the roster picked
        if folder != previous and self.save_mode == S.IN_PLACE:
            self.name_edited = False        # the name box shows the roster picked
        self.selected = folder
        slot = self.selected_slot()
        if folder != previous and getattr(slot, 'disc', False) and not self.name_edited:
            self.name = savedata.default_name()
        if self.in_place(slot) and not self.name_edited:
            self.name = slot.name

    def open_roster_folder(self, folder):
        slot = self.slot_of(folder)
        if slot is not None and not getattr(slot, 'disc', False) and os.path.isdir(slot.path):
            self.host.open_path(slot.path)

    def ask_delete(self, folder):
        """Ask before a roster save goes to the Recycle Bin."""
        with self.lock:
            slot = self.slot_of(folder)
            if slot is None or getattr(slot, 'disc', False) or self.busy or self.scanning:
                return
            if savedata.running_rpcs3():
                self.show_result(False, "Close RPCS3 first", ["A roster can only be removed while the game is closed."])
                return
            self.ask(f"Move \"{slot.name}\" to the {X.BIN_NAME}?",
                     [f"{slot.region} game, folder {slot.folder}, saved {X.friendly_date(slot.modified)}.",
                      f"You can take it out of the {X.BIN_NAME} again. Your other rosters are not changed."],
                     [(f"Move to the {X.BIN_NAME}", 'yes', 'danger'), ("Keep it", 'no', 'plain')],
                     {'yes': lambda: self.delete_save(folder)})

    def delete_save(self, folder):
        with self.lock:
            slot = self.slot_of(folder)
            if slot is None or getattr(slot, 'disc', False) or self.busy or self.scanning or self.rpcs3 is None:
                return
            if self.editor_busy():
                self.show_result(False, "The roster was not removed", ["The Roster editor is working. Try again in a moment."])
                return
            try:
                savedata.trash_save(self.rpcs3.savedata, folder)
            except savedata.DeleteError as err:
                self.show_result(False, "The roster was not removed", [str(err)])
                return
            if self.editor is not None and getattr(self.editor, 'source', None) and self.editor.source[1] == folder:
                self.editor.source = None       # an update may give the same folder name to a new roster
            self.slots = [s for s in self.slots if s.folder != folder]
            if self.selected == folder:
                self.selected = None
            where = self.rpcs3.where
            self.show_result(True, f"\"{slot.name}\" is in the {X.BIN_NAME}",
                             [f"The {slot.region} roster in folder {folder} was removed from the game's saves. "
                              f"Take it out of the {X.BIN_NAME} to get it back."])
        self.say(f"Moved the roster \"{slot.name}\" ({folder}) to the {X.BIN_NAME}.")
        self.set_rpcs3(where, quiet=True)

    # --- what to update, how to save ------------------------------------------------------------------
    def set_step(self, key, on):
        with self.lock:
            if self.busy:
                return
            on = bool(on)
            if key in self.steps:
                self.steps[key] = on
            elif key == S.PHOTOS:
                if on and (self.export_mode or self.rpcs3 is not None and self.rpcs3.plain):
                    return
                self.photos = on
            elif key == S.EDITS:
                self.use_edits = on
            else:
                return
            if on:
                self.marks.pop(key, None)       # a switch turned on again cancels its "Restore"
            self.save_settings()
            self.changed()

    def toggle_restore(self, key):
        """A row's Restore button: that part is put back as the game had it in the next save (again: undo)."""
        with self.lock:
            if self.busy or self.scanning or self.export_mode:
                return
            if key in self.marks:
                del self.marks[key]
            elif key in self.steps or key == S.PHOTOS:
                self.marks[key] = (restore.CALENDAR if key == pipeline.SCHEDULE else
                                   restore.PICTURES if key == S.PHOTOS else restore.ROSTERS)
                if key == S.PHOTOS:
                    self.photos = False
                else:
                    self.steps[key] = False
                self.save_settings()
            self.changed()

    def set_save_mode(self, mode):
        with self.lock:
            if self.busy or mode not in (S.IN_PLACE, S.AS_NEW):
                return
            self.save_mode = mode
            self.settings[S.SAVE_MODE] = mode
            S.save(self.settings)
            self.name_edited = False
            slot = self.selected_slot()
            self.name = slot.name if self.in_place(slot) else savedata.default_name()
            self.changed()
        if self.editor is not None:
            self.editor.changed()

    def set_save_for(self, value):
        with self.lock:
            if self.busy or value not in ('EU', 'NA', S.BOTH):
                return
            self.save_pick = value
            self.settings[S.SAVE_BOTH] = value == S.BOTH
            S.save(self.settings)
            self.changed()

    def set_name(self, text):
        with self.lock:
            if self.busy or self.export_mode:
                return
            self.name = str(text)
            self.name_edited = True
            self.changed()

    # --- the update ---------------------------------------------------------------------------------
    def restore_default(self):
        """The big button: everything back as the game had it, after a question."""
        with self.lock:
            slot = self.selected_slot()
            if slot is None or self.busy or self.scanning or self.export_mode:
                return
            where = (f"\"{slot.name}\" is replaced (its old version is copied to the backups folder first)"
                     if self.in_place(slot) else "A new roster is saved next to your others; nothing you have is replaced")
            self.ask("Restore default",
                     ["This puts back the game's own rosters, calendar, pictures, team names and jerseys.",
                      f"{where}. RPCS3 must be closed."],
                     [("Restore default", 'yes', 'primary'), ("Cancel", 'no', 'plain')],
                     {'yes': lambda: self.start(everything=True)})

    def start(self, everything=False):
        with self.lock:
            if self.export_mode:
                self._start_export()
                return
            slot = self.selected_slot()
            steps = [] if everything else [s for s in self.step_keys if self.steps[s]]
            parts = set(restore.ALL_PARTS) if everything else set(self.marks.values())
            if slot is None or self.busy or self.scanning or not (steps or parts) or self.rpcs3 is None:
                return
            self.save_settings()
            in_place = self.in_place(slot)
            if in_place and savedata.running_rpcs3():
                self.show_result(False, "Close RPCS3 first", ["A roster can only be updated while the game is closed."])
                return
            if in_place and self.editor_busy():
                self.show_result(False, "The roster was not updated", ["The Roster editor is working. Try again in a moment."])
                return
            if in_place:        # a rename only when the player changed the name
                name = self.name.strip() if self.name_edited and self.name.strip() != slot.name else None
            else:
                name = self.name.strip() if self.name_edited and self.name.strip() else savedata.default_name()
            self._begin("Updating... (the last result is shown until the new one is ready)")
            art = self.rpcs3 if self.photos and not self.rpcs3.plain and not everything else None
            self.photos_running = art is not None
            mine = (my_edits.load(), my_edits.load_teams()) if self.use_edits and not everything else (None, None)
            rpcs3, targets = self.rpcs3, self.save_targets(slot)

        def work():
            default = restore.default_slot(rpcs3, slot.title_id) if parts else None
            result = pipeline.update(rpcs3.savedata, slot.folder, steps, name, self.say,
                                     art_rpcs3=art, my_edits=mine[0] or None, team_edits=mine[1] or None,
                                     targets=targets, disc=slot if getattr(slot, 'disc', False) else None,
                                     in_place=in_place, restore_parts=parts, default=default)
            return result, savedata.running_rpcs3() is not None

        jobs.run(work, done=lambda r: self._done(*r), failed=self._failed,
                 expected=(layout.LayoutError, datasource.Offline, FileNotFoundError, ArtError, StockError,
                           savedata.InPlaceError))

    def _begin(self, dim_title):
        self.busy, self.at, self.last_report = True, 0.0, None
        if self.result:                 # the last result stays, greyed, until the new one is ready
            self.result['dim'] = dim_title
        self.status = ("0%   Starting...", 'body')
        self.host.log_clear()
        self.changed()

    def _finish(self):
        with self.lock:
            self.busy = False
            where = self.rpcs3.where if self.rpcs3 else None
        if not self.export_mode:
            self.set_rpcs3(where, quiet=True)

    def _failed(self, message):
        self._finish()
        self.say(message)
        with self.lock:
            self._fail("Nothing was saved", [message, "Your existing rosters are untouched."])

    def _fail(self, title, lines):
        self.at = 0.0
        self.status = ("Nothing was saved.", 'bad')
        self.show_result(False, title, lines, [("Show details", 'details')])

    def _done(self, result, rpcs3_running):
        self._finish()
        items = result.build.lines() + [("Restored", text) for text in result.restored]
        self.say("", "What changed:", *(f"   {title}: {text}" for title, text in items))
        with self.lock:
            self.last_report = result.report_path
            if result.exported and result.slot is not None:
                self._export_folder = os.path.dirname(result.exported)
                self.at = 1.0
                self.status = ("Done: SYS-DATA exported.", 'good')
                self.show_result(True, "SYS-DATA exported",
                                 [f"New file: {result.exported}", X.HOW_TO_USE_EXPORT, "No pictures are in it: they need RPCS3."],
                                 [("Open the folder", 'export_folder'), ("List of changes", 'report')],
                                 items=items or [("Result", "Nothing needed changing.")])
                said = [f"Done. {X.HOW_TO_USE_EXPORT}"]
            elif result.slot is None:
                problems = result.build.problems
                self._fail("The new roster failed the safety checks, so nothing was saved",
                           problems[:3] + ["Your existing rosters are untouched."])
                said = ["   - " + p for p in problems[:15]]
            else:
                said = self._saved(result, rpcs3_running, items)
        self.say(*said)

    def _saved(self, result, rpcs3_running, items):
        """The result box of a saved roster; returns the lines for the details."""
        said = []
        thin = result.build.info.get('thinner_ahl_teams') or []
        if thin:
            said.append(f"Note: {len(thin)} AHL teams lost players to NHL rosters and are short-handed. "
                        "Switch on \"AHL rosters\" to fill them with their real players.")
        art = result.art_line()
        if art:
            said.append(art)
        how = X.HOW_TO_LOAD_IN_PLACE if result.in_place else X.HOW_TO_LOAD
        said.append(f"Done. {how}")
        self.name_edited = False
        self.at = 1.0
        buttons = [("List of changes", 'report'), ("Open save folder", 'save_folder')]
        self._backup = result.backup if result.in_place else None
        if self._backup:
            buttons.insert(1, ("Open backup folder", 'backup'))
        if not rpcs3_running and self.rpcs3 is not None and not self.rpcs3.plain:
            buttons.append(("Start RPCS3", 'start_rpcs3'))
        name = result.slot.name
        if result.in_place:
            if self.editor is not None:
                self.editor.source = None       # the editor shows what the file is now
            where = ("The roster is already the same as the new one: nothing was changed." if result.unchanged
                     else f"Updated: {result.saved_where()}.")
            lines = [where] + ([f"The old roster is kept in {result.backup}"] if result.backup else []) \
                + list(result.restored) + ([art] if art else []) + [how]
            title = f"Already up to date: \"{name}\"" if result.unchanged else f"Updated \"{name}\""
            self.status = (f"Done: {'already up to date' if result.unchanged else 'updated'} \"{name}\".", 'good')
        else:
            where = f"New save: {result.saved_where()}."
            lines = [where] + list(result.restored) + ([art] if art else []) + [how]
            title = f"Saved as \"{name}\""
            self.status = (f"Done: saved as \"{name}\".", 'good')
        said.append(where)
        self.show_result(True, title, lines, buttons, items=items or [("Result", "Nothing needed changing.")])
        return said

    def result_action(self, action):
        if action == 'report':
            if self.last_report and os.path.exists(self.last_report):
                self.host.open_path(self.last_report)
        elif action == 'save_folder':
            if self.rpcs3:
                self.host.open_path(self.rpcs3.savedata)
        elif action == 'backup':
            if self._backup:
                self.host.open_path(self._backup)
        elif action == 'export_folder':
            if self._export_folder:
                self.host.open_path(self._export_folder)
        elif action == 'start_rpcs3':
            self.start_rpcs3()
        elif action == 'update_page':
            if self._update_page:
                self.host.open_url(self._update_page)
        elif action == 'details':
            self.host.send('details', {'open': True})
        elif action == 'close':
            self.hide_result()

    def start_rpcs3(self):
        if self.rpcs3 and not self.rpcs3.plain and not savedata.running_rpcs3():
            self.rpcs3.start()

    def remove_photos(self):
        """Put back every game file the photos and logos replaced."""
        with self.lock:
            if self.busy:
                return
            messages = []
            try:
                remove_art(say=messages.append)
            except ArtError as err:
                self.show_result(False, "The photos and logos are still there", [str(err)])
                return
            self.art_installed = art_installed()
            self.show_result(True, "The game's own pictures are back", messages + ["Your rosters are not changed."])
        self.say(*messages)

    def closing(self):
        """May the window close now? Not while a roster is being written."""
        with self.lock:
            if not self.busy or self.quitting:
                return True
            self.ask("Please wait", ["A roster is being made right now. Close the window when it is done, so no "
                                     "half-written roster is left behind."], [("OK", 'ok', 'primary')], {})
            return False

    # --- "Export only SYS-DATA roster" (no RPCS3 on this PC) ----------------------------------------
    def set_export_only(self, on):
        with self.lock:
            if self.busy:
                return
            self.export_mode = bool(on)
            self.settings[S.EXPORT_ONLY] = self.export_mode
            S.save(self.settings)
            self.result = None
            self.status = None
            if not self.export_mode:
                self.name_edited = False
                self.name = savedata.default_name()
            where = self.rpcs3.where if self.rpcs3 else self.settings.get('rpcs3')
            self.changed()
        if not on:
            self.set_rpcs3(where, quiet=True)

    def pick_export_file(self):
        with self.lock:
            if self.busy:
                return
            start = os.path.dirname(self.export_file) if self.export_file else os.path.expanduser('~')
        path = self.host.ask_open("Pick the roster file (SYS-DATA)", ['Roster file (SYS-DATA)', 'All files (*.*)'], start)
        if not path:
            return
        self.use_export_file(os.path.normpath(path))

    def use_export_file(self, path):
        try:
            layout.check_base(Roster(path))
            from .. import stock
            if stock.is_stock(Roster(path)):
                raise layout.LayoutError("that is the game's own roster, which needs your game disc: pick the community "
                                         "roster's SYS-DATA")
            problem = None
        except (layout.LayoutError, ValueError, KeyError, OSError) as err:
            problem = "That file cannot be used: " + X.short_reason(str(err))[len("Cannot be used: "):]
        with self.lock:
            if problem:
                self.export_file, self.export_problem = None, problem
            else:
                self.export_file, self.export_problem = path, None
                self.settings[S.EXPORT_FILE] = path
                S.save(self.settings)
            self.changed()

    def _start_export(self):
        steps = [s for s in self.step_keys if self.steps[s]]
        if self.export_file is None or self.busy or not steps:
            return
        self.save_settings()
        self._begin("Working... (the last result is shown until the new one is ready)")
        self.photos_running = False
        mine = (my_edits.load(), my_edits.load_teams()) if self.use_edits else (None, None)
        file = self.export_file

        def work():
            return pipeline.export_sysdata(file, steps, None, self.say, my_edits=mine[0] or None,
                                           team_edits=mine[1] or None), False

        jobs.run(work, done=lambda r: self._done(*r), failed=self._failed,
                 expected=(layout.LayoutError, datasource.Offline, FileNotFoundError, OSError))

    # --- what the tab shows -------------------------------------------------------------------------
    def snapshot(self):
        with self.lock:
            slot = self.selected_slot()
            export = self.export_mode
            ready = (self.export_file is not None and not self.busy) if export else \
                (slot is not None and not self.busy and not self.scanning)
            any_step = any(self.steps.values()) or (bool(self.marks) and not export)
            in_place = self.in_place(slot) and not export
            plain = self.rpcs3 is not None and self.rpcs3.plain
            return {
                'busy': self.busy, 'scanning': self.scanning,
                'rpcs3': self._rpcs3_view(export, plain),
                'export': {'on': export, 'file': self.export_file,
                           'text': self.export_problem or (f"Roster file: {self.export_file}" if self.export_file else X.EXPORT_PICK),
                           'tone': 'bad' if self.export_problem else 'good' if self.export_file else 'muted'},
                'fresh': [] if export else [{'folder': s.folder, 'label': f"New from {s.region} disc", 'region': s.region}
                                            for s in self.slots if getattr(s, 'disc', False)],
                'empty': None if self.slots else ("Looking for your rosters..." if self.scanning else
                                                  "Pick RPCS3 first. Your rosters will be listed here."),
                'rosters': [] if export else [self._roster_view(s) for s in self.slots],
                'selected': self.selected,
                'steps': self._steps_view(export, plain),
                'later': ("Coming later:  " + "  ·  ".join(n.split(' (')[0] for n in pipeline.planned(self.pack))
                          if pipeline.planned(self.pack) else None),
                'restore_pictures': {'shown': bool(self.art_installed) and not export, 'enabled': not self.busy},
                'restore_all': {'shown': not export, 'enabled': ready and not export},
                'save': self._save_view(slot, export, in_place, ready, any_step),
                'result': self.result,
                'status': self._status_view(slot, export, ready, any_step),
                'progress': {'value': round(self.at, 4), 'active': self.busy,
                             'indeterminate': self.scanning and not self.busy},
                'dialog': self.dialog,
                'check_updates': self.settings.get('check_updates', True) is not False,
            }

    def _rpcs3_view(self, export, plain):
        if export:
            note, tone = X.EXPORT_RPCS3, 'muted'
        elif self.rpcs3 is None:
            if self.scanning:
                note, tone = "Looking for your rosters...", 'muted'
            elif self.problem:
                note, tone = self.problem, 'bad'
            else:
                note, tone = savedata.PICK_RPCS3 + " The program finds your saves from there.", 'muted'
        elif self.scanning and not self.slots:
            note, tone = "Looking for your rosters...", 'muted'
        else:
            note, tone = X.rpcs3_note(self.rpcs3, self.slots), 'info'
        needs_game = bool(self.rpcs3 and not self.rpcs3.plain and not self.rpcs3.disc_slots()) and not export
        return {'path': self.rpcs3.where if self.rpcs3 else None, 'note': {'text': note, 'tone': tone} if note else None,
                'running': self.running and self.rpcs3 is not None and not plain and not export,
                'needs_game': needs_game, 'find_label': "Find rpcs3.exe" if savedata.WINDOWS else "Find RPCS3",
                'enabled': not self.busy and not export}

    def _roster_view(self, s):
        problem = self.usable.get(s.folder)
        disc = getattr(s, 'disc', False)
        return {'folder': s.folder, 'name': s.name, 'region': s.region,
                'meta': X.DISC_NOTE if disc else f"{s.folder}  |  {X.friendly_date(s.modified)}",
                'chip': {'text': "start fresh", 'kind': 'muted'} if disc else
                        {'text': "made here", 'kind': 'made'} if s.tool_made and problem is None else None,
                'problem': X.short_reason(problem) if problem else None,
                'actions': not disc, 'usable': problem is None, 'selected': s.folder == self.selected,
                'delete_enabled': not self.busy and not self.scanning}

    def _steps_view(self, export, plain):
        sources = self.pack.get('sources', {})
        notes = {pipeline.NHL: X.NHL_NOTE,
                 pipeline.RATINGS: X.dated(sources.get('ea_ratings')),
                 pipeline.NATIONAL: X.dated(sources.get('iihf')),
                 pipeline.SCHEDULE: X.SCHEDULE_NOTE}
        restorable = not export and not self.busy and not self.scanning
        rows = [{'key': k, 'title': pipeline.STEP_LABELS[k], 'sub': notes.get(k) or X.dated(sources.get(k)),
                 'warn': pipeline.left_out_note(self.pack, k), 'hint': None, 'on': self.steps[k],
                 'enabled': not self.busy, 'restore': not export, 'restore_enabled': restorable,
                 'restoring': k in self.marks}
                for k in self.step_keys]
        photos_ok = not export and not plain
        rows.append({'key': S.PHOTOS, 'title': "Photos, logos and team names", 'sub': self.photos_note, 'warn': None,
                     'hint': X.PHOTOS_HINT, 'on': self.photos and photos_ok, 'enabled': not self.busy and photos_ok,
                     'restore': photos_ok, 'restore_enabled': restorable, 'restoring': S.PHOTOS in self.marks})
        rows.append({'key': S.EDITS, 'title': "My edits", 'sub': "Your changes from the Roster editor, applied after the update",
                     'warn': None, 'hint': X.EDITS_HINT, 'on': self.use_edits, 'enabled': not self.busy,
                     'restore': False, 'restore_enabled': False, 'restoring': False})
        return rows

    def _save_view(self, slot, export, in_place, ready, any_step):
        if export:
            button = "Working..." if self.busy else "Make new roster"
        elif self.busy:
            button = "Updating..."
        elif self.marks:
            button = "Update and restore" if any(self.steps.values()) else "Restore"
        else:
            button = "Update roster" if in_place else "Make new roster"
        two = slot is not None and len(self.versions) >= 2 and not in_place and not export
        return {'mode': (S.IN_PLACE if in_place else S.AS_NEW if slot is not None else self.save_mode),
                'mode_shown': not export, 'mode_enabled': not self.busy,
                'name': X.NO_NAME if export else self.name, 'name_enabled': not self.busy and not export,
                'save_for': {'value': self.save_pick or slot.region, 'enabled': not self.busy,
                             'options': ['EU', 'NA', S.BOTH]} if two else None,
                'button': {'text': button, 'enabled': ready and any_step},
                'note': X.EXPORT_SAVE_NOTE if export else X.SAVE_NOTE}

    def _status_view(self, slot, export, ready, any_step):
        if self.busy or (self.result is not None and self.status):
            text, tone = self.status or ("Working...", 'body')
        elif export:
            text, tone = ("Ready." if ready and any_step else
                          "Pick the roster file (step 2)." if self.export_file is None else
                          "Switch on at least one thing to update."), 'muted'
        else:
            text, tone = ("Looking for your rosters..." if self.scanning else
                          "Ready." if ready and any_step else
                          "Start with step 1: find RPCS3." if self.rpcs3 is None else
                          "Switch on at least one thing to update." if slot is not None else
                          "None of the rosters found can be updated."), 'muted'
        return {'text': text, 'tone': tone}
