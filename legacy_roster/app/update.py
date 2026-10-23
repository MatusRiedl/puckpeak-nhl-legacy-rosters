"""The Update tab without a window toolkit: say where RPCS3 is, pick a roster, switch on what to
update, press one button. `snapshot()` is everything the tab shows, as plain data; the methods are
its buttons. The same rules as the old window (gui.App), which this replaces."""
import datetime
import os
import sys
import tempfile
import threading
import time

from .. import __version__, datasource, gamepatch, layout, packs, patchinstall, pipeline, restore, savedata
from .. import edits as my_edits
from ..art.install import ArtError, installed as art_installed, remove as remove_art
from ..gui_state import is_current_scan
from ..progress import fraction
from ..roster import Roster
from ..stock import StockError
from . import jobs, selfupdate, settings as S, texts as X

SLICE = 'update'


def _load_pack():
    try:
        return datasource.load_pack(offline=True)
    except datasource.Offline:
        return {}


def temporary(path):
    """Is `path` in the system's temp folder, in the program as players run it (the exe)? Such an RPCS3 is never
    used at start and never remembered: a test's pretend RPCS3 once landed in the owner's settings (2026-10-22), and
    Patch then failed on its pretend disc. Run from source (tests, tools/window_shot.py) a temp RPCS3 is fine."""
    if not path or not getattr(sys, 'frozen', False):
        return False
    temp = os.path.normcase(os.path.abspath(tempfile.gettempdir()))
    return os.path.normcase(os.path.abspath(path)).startswith(temp + os.sep)


class UpdateController:
    def __init__(self, host, settings=None, pack=None, photos=True):
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
        self.checked = {}           # (SYS-DATA path, size, time) -> (None or why it cannot be used, made for the patch,
                                    # its rights' bits)
        self.patch_rosters = set()  # roster folders made for the game patch
        self.roster_rights = {}     # roster folder -> the bits of its player rights (5; 6 on a roster for patch 0.23)
        self.patch_state = {}       # patchinstall.state of this RPCS3
        self._fit_check = False     # Patch / Unpatch done: after the next scan, ask to update a roster that no longer fits
        self._fit = None            # the roster folder that question's "Update it now" updates in place
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
        self.photos = bool(remembered.get(S.PHOTOS, photos))
        self.use_edits = bool(remembered.get(S.EDITS, True))
        self.skip_intro = bool(remembered.get(S.SKIP_INTRO, True))
        self.no_login = bool(remembered.get(S.NO_LOGIN, False))
        self.marks = {}             # row key -> its part of restore.py ("Restore" pressed)
        # the picture packs (packs.py), downloaded in the background while "Photos, logos and team names" is on
        self.fetch = 'ready' if all(packs.have(n) for n in packs.NAMES) else 'idle'     # running / failed
        self.fetch_at = 0.0         # 0..1 while running
        self.fetch_size = None      # bytes still to download, once the server said
        self._fetch_stop = threading.Event()
        self._fetching = False
        self.waiting = None         # Update pressed during the download: start(everything) once it is done
        self.pictures_short = False # the running update lacks a pack (offline): the result says so

    # --- start --------------------------------------------------------------------------------------
    def start_up(self):
        """Find RPCS3 where it was last time (or where it runs / usually is)."""
        last = self.settings.get('rpcs3') or self.settings.get('folder')
        self.set_rpcs3((None if temporary(last) else last) or savedata.running_rpcs3() or savedata.default_rpcs3(),
                       quiet=True)

    def changed(self):
        self.host.changed(SLICE)

    # --- a newer version of the program -----------------------------------------------------------------
    def check_for_update(self, force=False):
        """Look at GitHub in the background (at every start, unless the player switched it off; `force`: the button);
        a newer version is offered in a question. Never in the way: offline means silence."""
        with self.lock:
            if not force and not selfupdate.due(self.settings):
                return
        threading.Thread(target=self._look_for_update, args=(force,), daemon=True).start()

    def _look_for_update(self, force, wait=2.0):
        release = selfupdate.latest()
        with self.lock:
            if release is None and force:
                self.ask("You have the newest version", [f"Version {__version__} is the latest one."
                         " If you are offline, or GitHub did not answer, try again in a moment."],
                         [("OK", 'ok', 'primary')], {})
                return
            if release is None or (not force and self.settings.get('update_skipped') == release.text):
                return
        while True:                 # an update or another question first, then the offer (before, it was dropped)
            with self.lock:
                if self.quitting:
                    return
                if not (self.busy or self.dialog):
                    self._offer_update(release)
                    return
            time.sleep(wait)

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

    # --- the pictures of "Photos, logos and team names" (packs.py) ----------------------------------------
    def download_pictures(self):
        """While the switch is on: download what is missing or changed, in the background (at start, when the
        switch goes on, and before an update when the last try failed). The next update uses it."""
        with self.lock:
            if not self.photos or self._fetching:
                return
            self._fetching = True
            self._fetch_stop.clear()
        threading.Thread(target=self._download, daemon=True).start()

    def _download(self):
        why = None
        try:
            try:
                packs.prune()           # what an earlier run still had open
            except OSError:
                pass
            listed = packs.manifest()
            if listed is None:
                why = 'offline'
            else:
                names = packs.missing(listed)
                with self.lock:
                    self.fetch_size = packs.size_of(listed, names) or None
                    if names:
                        self.fetch, self.fetch_at = 'running', 0.0
                    self.changed()
                why = packs.sync(self._fetch_progress, self._fetch_stop.is_set, listed)[1]
        except packs.Cancelled:
            why = 'stopped'
        except Exception as err:        # a folder that cannot be written: logged, tried again later
            jobs.log_unexpected(err)
            why = str(err)
        if why not in (None, 'stopped'):
            self.host.log(f"The pictures were not downloaded ({why}). The program tries again.")
        with self.lock:
            self._fetching = False
            have = all(packs.have(n) for n in packs.NAMES)
            self.fetch = ('ready' if why is None or have else 'idle' if why == 'stopped' else 'failed')
            waiting, self.waiting = self.waiting, None
            if waiting is not None:
                self.busy, self.status = False, None
            self.changed()
        if waiting is not None:
            self.start(waiting, waited=True)

    def _fetch_progress(self, at):
        with self.lock:
            moved = int(at * 100) != int(self.fetch_at * 100)
            self.fetch_at = at
            if moved:
                if self.waiting is not None:
                    self.at, self.status = at, (X.PHOTOS_WAITING.format(pct=int(at * 100)), 'body')
                self.changed()

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
                self.status = (f"Downloading version {release.text}...", 'body')
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
        self.settings['steps'].update({S.SKIP_INTRO: self.skip_intro, S.NO_LOGIN: self.no_login})
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
                self.status = (last, 'body')
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
            found, slots, usable, versions, problem, picked, patchy, state = None, [], {}, [], None, None, set(), {}
            rights = {}
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
                            R = Roster(s.sys_data)
                            layout.check_base(R)
                            checked[key] = (None, gamepatch.is_patch_roster(R), R.P.field(gamepatch.RIGHTS).bits)
                        except (layout.LayoutError, ValueError, KeyError, OSError) as err:
                            checked[key] = (str(err), False, None)
                    usable[s.folder] = checked[key][0]
                    if checked[key][1]:
                        patchy.add(s.folder)
                    rights[s.folder] = checked[key][2]
                slots = slots + found.disc_slots()
                if not found.plain:
                    state = patchinstall.state(found)
            running = savedata.running_rpcs3() is not None if found else False
            self._scanned(found, slots, usable, versions, problem, quiet, running, checked, picked, scan_id, patchy, state,
                          rights)

        jobs.run(scan, failed=lambda message: self._scan_failed(message, scan_id))

    def _scan_failed(self, message, scan_id):
        with self.lock:
            if not is_current_scan(scan_id, self._scan_id):
                return
            self.scanning = False
            self.problem = message
            self.changed()

    def _scanned(self, found, slots, usable, versions, problem, quiet, running, checked, picked, scan_id, patchy=(),
                 state=None, rights=None):
        with self.lock:
            if not is_current_scan(scan_id, self._scan_id):
                return
            self.scanning = False
            if picked:
                self.selected = picked
            self.checked = checked
            self.rpcs3, self.slots, self.usable, self.versions = found, slots, usable, versions
            self.patch_rosters, self.patch_state = set(patchy), dict(state or {})
            self.roster_rights = dict(rights or {})
            self.problem = problem if problem and not quiet else None
            self.running = running
            if found and not temporary(found.where):
                self.settings['rpcs3'] = found.where
                self.settings.pop('folder', None)
                S.save(self.settings)
            self.art_installed = art_installed()
            keep = self.selected if self.slot_of(self.selected) and self.usable.get(self.selected) is None else None
            first = next((s.folder for s in slots if usable[s.folder] is None and not getattr(s, 'disc', False)),
                         next((s.folder for s in slots if usable[s.folder] is None), None))
            self._select(keep or first)
            if self._fit_check:
                self._fit_check = False
                self._ask_fit()
            self.changed()

    def misfit(self, s):
        """Why the game as RPCS3 has it now cannot load roster `s`, or None: a normal roster in a patched game, a
        roster made for the patch in a game without it (the game says the roster is damaged), a roster made for another
        version of the patch (its player rights have other bits than the game's db description: patch 0.23 gave them
        six)."""
        if s is None or getattr(s, 'disc', False) or self.rpcs3 is None or self.rpcs3.plain \
                or self.usable.get(s.folder) is not None:
            return None
        if self.patch_state.get(s.title_id, {}).get('stale'):
            return X.MISFIT_STALE
        patched, made = s.title_id in self._patched(), s.folder in self.patch_rosters
        if patched and made:
            game, own = self.patch_state.get(s.title_id, {}).get('rights'), self.roster_rights.get(s.folder)
            return X.MISFIT_VERSION if game and own and game != own else None
        return X.MISFIT_PATCHED if patched else X.MISFIT_UNPATCHED if made else None

    def _ask_fit(self):
        """After Patch / Unpatch: the roster picked no longer fits the game, so offer to update it now."""
        slot = self.selected_slot()
        why = self.misfit(slot)
        if why is None:
            return
        self.ask(f"Update \"{slot.name}\" now?", X.fit_ask(slot.name, why),
                 [("Update it now", 'yes', 'primary'), ("Later", 'no', 'plain')],
                 {'yes': lambda: self._update_fit(slot.folder)})

    def _update_fit(self, folder):
        with self.lock:
            if self.busy or self.selected != folder:
                return
            if not any(self.steps.values()):
                self.show_result(False, "Nothing to update", [X.FIT_NO_STEP])
                self.host.send('focus_tab', {'tab': 'update'})
                return
            self._fit = folder
        self.host.send('focus_tab', {'tab': 'update'})
        self.start()

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
                if on:
                    self.download_pictures()
                else:
                    self._fetch_stop.set()      # what is already on this PC stays, for the next time it is on
            elif key == S.EDITS:
                self.use_edits = on
            else:
                return
            if on:
                self.marks.pop(key, None)       # a switch turned on again cancels its "Restore"
            self.save_settings()
            self.changed()

    # --- step 2: the game patch -----------------------------------------------------------------------
    def patchable(self):
        """None when Patch / Unpatch can run now, else why not (shown on the card)."""
        if self.export_mode or self.rpcs3 is None or self.rpcs3.plain:
            return X.PATCH_NEEDS_RPCS3
        if not self.versions:
            return X.PATCH_NEEDS_GAME
        return None                     # RPCS3 running: Patch / Unpatch say so when pressed

    def patch(self):
        """Step 2's Patch button: the game patch into every version RPCS3 has (the first time after a question)."""
        with self.lock:
            if self.busy or self.scanning or self.rpcs3 is None or self.rpcs3.plain:
                return
            if savedata.running_rpcs3():
                self.running = True
                self.show_result(False, "Close RPCS3 first", ["The game can only be patched while RPCS3 is closed."])
                return
            if not self.settings.get(S.PATCH_ASKED):
                self.ask("32 teams and the year 2026", X.PATCH_ASK,
                         [("Patch the game", 'yes', 'primary'), ("Cancel", 'no', 'plain')], {'yes': self._patch_asked})
                return
        self._patch()

    def _patch_asked(self):
        with self.lock:
            self.settings[S.PATCH_ASKED] = True
            S.save(self.settings)
        self._patch()

    def _patch(self):
        with self.lock:
            if self.busy or self.rpcs3 is None or self.rpcs3.plain:
                return
            rpcs3, titles, intro, login = self.rpcs3, list(self.versions), self.skip_intro, self.no_login
            self._begin("Patching...")

        def work():
            messages = []
            done = patchinstall.install_patch(rpcs3, titles, intro=intro, login=login, say=messages.append)
            return done, messages

        def done(result):
            titles, messages = result
            with self.lock:
                self._fit_check = True
            self._finish()
            self.say(*messages)
            with self.lock:
                self.at = 1.0
                where = " and ".join(savedata.region(t) for t in titles)
                self.result = None          # step 2 says it: the rosters keep their room
                self.status = (X.patched_status(where), 'good')
                self.changed()

        jobs.run(work, done=done, failed=self._failed_patch_in,
                 expected=(patchinstall.PatchError, datasource.Offline, StockError, OSError))

    def _failed_patch_in(self, message):
        self._finish()
        self.say(message)
        with self.lock:
            self.at = 0.0
            self.status = ("The game is not patched.", 'bad')
            self.show_result(False, "The game was not patched", [message, "Nothing in RPCS3 was changed."])

    def set_patch_switch(self, key, on):
        """"Skip the intro" / "No pop ups at start": kept for the next Patch, and put into a patched game at once."""
        with self.lock:
            if self.busy or key not in (S.SKIP_INTRO, S.NO_LOGIN):
                return
            on = bool(on)
            patched = self._patched()
            if patched and savedata.running_rpcs3():
                self.running = True
                self.show_result(False, "Close RPCS3 first", ["The game patch can only be changed while RPCS3 is closed."])
                self.changed()
                return
            if key == S.SKIP_INTRO:
                self.skip_intro = on
            else:
                self.no_login = on
            self.save_settings()
            if patched:
                try:
                    patchinstall.set_switches(self.rpcs3, patched, self.skip_intro, self.no_login)
                    self.patch_state = patchinstall.state(self.rpcs3)
                except (patchinstall.PatchError, OSError) as err:
                    self.show_result(False, "The game patch was not changed", [str(err)])
            self.changed()

    def _patched(self):
        """The versions patched now (title ids)."""
        return [t for t, st in self.patch_state.items() if st.get('patched')]

    def unpatch(self):
        """Step 2's Unpatch button: the game patch out of RPCS3, after a question."""
        with self.lock:
            if self.busy or self.rpcs3 is None or self.rpcs3.plain:
                return
            if savedata.running_rpcs3():
                self.running = True
                self.show_result(False, "Close RPCS3 first", ["The game can only be unpatched while RPCS3 is closed."])
                return
            self.ask("Unpatch the game", X.UNPATCH_ASK, [("Unpatch", 'yes', 'primary'), ("Cancel", 'no', 'plain')],
                     {'yes': self._unpatch})

    def _unpatch(self):
        with self.lock:
            if self.busy or self.rpcs3 is None:
                return
            rpcs3 = self.rpcs3
            self._begin("Unpatching...")

        def work():
            messages = []
            patchinstall.remove(rpcs3, say=messages.append)
            return messages

        def done(messages):
            with self.lock:
                self._fit_check = True
            self._finish()
            self.say(*messages)
            with self.lock:
                self.at = 1.0
                self.result = None
                self.status = (X.UNPATCHED, 'good')
                self.changed()

        jobs.run(work, done=done, failed=self._failed_patch, expected=(patchinstall.PatchError,))

    def _failed_patch(self, message):
        self._finish()
        self.say(message)
        with self.lock:
            self.at = 0.0
            self.status = ("The game is still patched.", 'bad')
            self.show_result(False, "The game patch is still in", [message])

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
                     ["This puts back the game's own rosters, calendar, pictures, team names and jerseys, and takes "
                      "the game patch out.",
                      f"{where}. RPCS3 must be closed."],
                     [("Restore default", 'yes', 'primary'), ("Cancel", 'no', 'plain')],
                     {'yes': lambda: self.start(everything=True)})

    def start(self, everything=False, waited=False):
        with self.lock:
            if self.export_mode:
                self._start_export()
                return
            slot = self.selected_slot()
            fit, self._fit = slot is not None and self._fit == slot.folder, None    # "Update it now": in place
            steps = [] if everything else [s for s in self.step_keys if self.steps[s]]
            parts = set(restore.ALL_PARTS) if everything else set(self.marks.values())
            if slot is None or self.busy or self.scanning or not (steps or parts) or self.rpcs3 is None:
                return
            self.save_settings()
            in_place = fit or self.in_place(slot)
            if in_place and savedata.running_rpcs3():
                self.show_result(False, "Close RPCS3 first", ["A roster can only be updated while the game is closed."])
                return
            # the editor saving pictures writes the same lists of pictures as an update: one at a time
            if self.editor_busy() and (in_place or getattr(self.editor, 'saving_pictures', False)):
                self.show_result(False, "The roster was not updated", ["The Roster editor is working. Try again in a moment."])
                return
            if fit:
                name = None
            elif in_place:      # a rename only when the player changed the name
                name = self.name.strip() if self.name_edited and self.name.strip() != slot.name else None
            else:
                name = self.name.strip() if self.name_edited and self.name.strip() else savedata.default_name()
            art = self.rpcs3 if self.photos and not self.rpcs3.plain and not everything else None
            if art is not None and not waited and (self._fetching or self.fetch == 'failed'):
                self.waiting = everything           # the pictures first; a failed download is tried once more
                self._fit = slot.folder if fit else None
                self.busy, self.at = True, self.fetch_at
                self.status = (X.PHOTOS_WAITING.format(pct=int(self.fetch_at * 100)), 'body')
                self.changed()
                self.download_pictures()
                return
            self._begin("Updating... (the last result is shown until the new one is ready)")
            self.photos_running = art is not None
            self.pictures_short = art is not None and not all(packs.have(n) for n in packs.NAMES)
            mine = (my_edits.load(), my_edits.load_teams()) if self.use_edits and not everything else (None, None)
            rpcs3, targets = self.rpcs3, [slot.title_id] if fit else self.save_targets(slot)

        def work():
            default = restore.default_slot(rpcs3, slot.title_id) if parts else None
            result = pipeline.update(rpcs3.savedata, slot.folder, steps, name, self.say,
                                     art_rpcs3=art, my_edits=mine[0] or None, team_edits=mine[1] or None,
                                     targets=targets, disc=slot if getattr(slot, 'disc', False) else None,
                                     in_place=in_place, restore_parts=parts, default=default,
                                     rpcs3=None if rpcs3.plain else rpcs3)
            return result, savedata.running_rpcs3() is not None

        jobs.run(work, done=lambda r: self._done(*r), failed=self._failed,
                 expected=(layout.LayoutError, datasource.Offline, FileNotFoundError, ArtError, StockError,
                           savedata.InPlaceError, patchinstall.PatchError))

    def _begin(self, dim_title):
        self.busy, self.at, self.last_report = True, 0.0, None
        if self.result:                 # the last result stays, greyed, until the new one is ready
            self.result['dim'] = dim_title
        self.status = ("Starting...", 'body')
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
        if self.pictures_short:
            items.append(("Pictures", X.PHOTOS_SHORT))
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
        patched = result.patch_lines()
        said += patched
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
                + list(result.restored) + ([art] if art else []) + patched + [how]
            title = f"Already up to date: \"{name}\"" if result.unchanged else f"Updated \"{name}\""
            self.status = (f"Done: {'already up to date' if result.unchanged else 'updated'} \"{name}\".", 'good')
        else:
            where = f"New save: {result.saved_where()}."
            lines = [where] + list(result.restored) + ([art] if art else []) + patched + [how]
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
            if not self.busy or self.quitting or self.waiting is not None:
                return True             # a download cut short leaves a piece that the next start removes
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
            plain = self.rpcs3 is not None and self.rpcs3.plain
            any_step = any(self.steps.values()) or (bool(self.marks) and not export)
            in_place = self.in_place(slot) and not export
            room = {} if export else self._room()
            hidden = set().union(*(h for _, h in room.values())) if room else set()
            full = [t for t in self.save_targets(slot) if t in room and room[t][0] >= savedata.GAME_LISTS] \
                if slot is not None and not in_place and not export else []
            return {
                'busy': self.busy, 'scanning': self.scanning,
                'rpcs3': self._rpcs3_view(export),
                'patch': self._patch_view(),
                'export': {'on': export, 'file': self.export_file,
                           'text': self.export_problem or (f"Roster file: {self.export_file}" if self.export_file else X.EXPORT_PICK),
                           'tone': 'bad' if self.export_problem else 'good' if self.export_file else 'muted'},
                'fresh': [] if export else [{'folder': s.folder, 'label': f"New from {s.region} disc", 'region': s.region}
                                            for s in self.slots if getattr(s, 'disc', False)],
                'empty': None if self.slots else ("Looking for your rosters..." if self.scanning else
                                                  "Pick RPCS3 first. Your rosters will be listed here."),
                'rosters': [] if export else [self._roster_view(s, hidden) for s in self.slots],
                'room': self._room_view(room, export),
                'selected': self.selected,
                'steps': self._steps_view(export, plain),
                'later': ("Coming later:  " + "  ·  ".join(n.split(' (')[0] for n in pipeline.planned(self.pack))
                          if pipeline.planned(self.pack) else None),
                'restore_all': {'shown': not export, 'enabled': ready and not export},
                'save': self._save_view(slot, export, in_place, ready, any_step, full),
                'result': self.result,
                'status': self._status_view(slot, export, ready, any_step, full),
                'progress': {'value': round(self.at, 4), 'active': self.busy,
                             'indeterminate': self.scanning and not self.busy},
                'dialog': self.dialog,
                'check_updates': self.settings.get('check_updates', True) is not False,
                'downloads': self._downloads_view(),
            }

    def _downloads_view(self):
        """The Setup tab's Downloads card: the pictures (downloaded by themselves) and the player data."""
        running = self.fetch == 'running'
        pictures = (X.PHOTOS_RUNNING.format(pct=int(self.fetch_at * 100)) if running else
                    X.PHOTOS_READY if self.fetch == 'ready' else
                    X.PHOTOS_RETRY if self.fetch == 'failed' else X.photos_will(self.fetch_size))
        try:
            made = datetime.date.fromisoformat(str((self.pack or {}).get('generated') or '')[:10])
            made = f"{made.day} {made:%b %Y}"
        except ValueError:
            made = ''
        return [{'title': X.PHOTOS_TITLE, 'text': pictures, 'tone': 'good' if self.fetch == 'ready' else
                 'amber' if self.fetch == 'failed' else 'muted', 'bar': round(self.fetch_at, 3) if running else None},
                {'title': "Rosters, ratings, contracts and the calendar",
                 'text': f"Data from {made}" if made else "No data available",
                 'tone': 'good' if made else 'muted', 'bar': None}]

    def _rpcs3_view(self, export):
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
                'needs_game': needs_game, 'find_label': "Find rpcs3.exe" if savedata.WINDOWS else "Find RPCS3",
                'enabled': not self.busy and not export}

    def _patch_view(self):
        """Step 2: is the game patched, the two small switches, Patch / Unpatch."""
        why = self.patchable()
        patched = [t for t, st in self.patch_state.items() if st.get('patched') or st.get('stale')] \
            if why != X.PATCH_NEEDS_RPCS3 else []           # stale: patched before update 1.01 was known
        old = [t for t in patched if self.patch_state[t].get('version') != gamepatch.TEAMS_VERSION
               or self.patch_state[t].get('stale')]
        missing = [t for t in self.versions if t not in patched]
        free = not self.busy and not self.scanning and why is None
        if why == X.PATCH_NEEDS_RPCS3:
            state = {'text': why, 'tone': 'muted'}
        elif patched:
            state = {'text': X.patch_state(self.patch_state, old, missing), 'tone': 'amber' if old or missing else 'good'}
        else:
            state = {'text': X.NOT_PATCHED, 'tone': 'muted'}
        buttons = []
        if why != X.PATCH_NEEDS_RPCS3 and self.versions:
            if old:
                label = "Patch again"
            elif not patched:
                label = "Patch the game"
            elif missing:
                label = "Patch " + " and ".join(savedata.region(t) for t in missing) + " too"
            else:
                label = None
            if label:
                buttons.append({'label': label, 'call': 'patch', 'enabled': free, 'kind': 'gold'})
            if patched:
                buttons.append({'label': "Unpatch", 'call': 'unpatch', 'enabled': free, 'kind': 'gold-line'})
        switch = not self.busy and why != X.PATCH_NEEDS_RPCS3
        note = None if why == X.PATCH_NEEDS_RPCS3 else why
        return {'title': X.PATCH_TITLE, 'sub': X.PATCH_SUB, 'state': state,
                'note': note,
                'info': {'title': X.PATCH_INFO_TITLE,
                         'sections': [{'head': head, 'items': items} for head, items in X.PATCH_INFO]},
                'checks': [{'key': S.SKIP_INTRO, 'label': "Skip the intro", 'on': self.skip_intro, 'enabled': switch},
                           {'key': S.NO_LOGIN, 'label': "No pop ups at start", 'tip': X.NO_LOGIN_TIP,
                            'on': self.no_login, 'enabled': switch}],
                'buttons': buttons, 'patched': bool(patched), 'regions': self._patch_regions(patched, old)}

    def _patch_regions(self, patched, old):
        """The Game patch tab: one card per version of the game, patched or not, with its rosters."""
        out = []
        for t in self.versions:
            if self.patch_state.get(t, {}).get('stale'):
                state, tone = "The game has update 1.01, the patch is older: patch again", 'amber'
            elif t in old:
                state, tone = "Patched with an older patch: patch again", 'amber'
            elif t in patched:
                state, tone = "Patched: 32 teams, the year 2026", 'good'
            else:
                state, tone = "Not patched", 'muted'
            rosters = [{'name': s.name, 'tag': "32 teams" if s.folder in self.patch_rosters else None,
                        'misfit': self.misfit(s) is not None}
                       for s in self.slots if s.title_id == t and not getattr(s, 'disc', False)]
            out.append({'region': savedata.region(t), 'title': t, 'state': state, 'tone': tone, 'rosters': rosters})
        return out

    def _room(self):
        """{title id: (roster folders, folders the game does not list)} for the versions in view."""
        where = getattr(self.rpcs3, 'savedata', None)
        if not where:
            return {}
        titles = {s.title_id for s in self.slots} | set(self.versions)
        return {t: (savedata.roster_count(where, t), savedata.hidden_in_game(where, t)) for t in sorted(titles)}

    def _room_view(self, room, export):
        if export or not room:
            return None
        full = any(n >= savedata.GAME_LISTS for n, _ in room.values())
        most = savedata.GAME_LISTS
        counts = [{'region': savedata.region(t),
                   'text': f"{n} of {most}" + (" (full)" if n == most else f", {n - most} not in the game" if n > most else ""),
                   'tone': 'bad' if n >= most else 'amber' if n == most - 1 else 'good'}
                  for t, (n, _) in room.items()]
        near = any(c['tone'] != 'good' for c in counts)       # the note only when it matters (step 2 took the room)
        return {'counts': counts, 'text': X.ROOM_FULL_SHORT if full else X.ROOM_NOTE if near else None,
                'tip': X.ROOM_NOTE, 'tone': 'bad' if full else 'info'}

    def _roster_view(self, s, hidden=frozenset()):
        problem = self.usable.get(s.folder)
        disc = getattr(s, 'disc', False)
        return {'folder': s.folder, 'name': s.name, 'region': s.region,
                'meta': X.DISC_NOTE if disc else f"{s.folder}  |  {X.friendly_date(s.modified)}",
                'tag': "32 teams" if s.folder in self.patch_rosters else None,
                'chip': {'text': "start fresh", 'kind': 'muted'} if disc else
                        {'text': "not in the game", 'kind': 'hidden'} if s.folder in hidden else
                        {'text': "made here", 'kind': 'made'} if s.tool_made and problem is None else None,
                'problem': X.short_reason(problem) if problem else X.HIDDEN_IN_GAME if s.folder in hidden else None,
                'misfit': self.misfit(s),
                'actions': not disc, 'usable': problem is None, 'selected': s.folder == self.selected,
                'delete_enabled': not self.busy and not self.scanning}

    def _steps_view(self, export, plain):
        sources = self.pack.get('sources', {})
        notes = {pipeline.NHL: X.NHL_NOTE,
                 pipeline.RATINGS: X.dated(sources.get('ratings_list')),
                 pipeline.NATIONAL: X.dated(sources.get('iihf')),
                 pipeline.SCHEDULE: X.SCHEDULE_NOTE}
        restorable = not export and not self.busy and not self.scanning
        rows = [{'key': k, 'title': pipeline.STEP_LABELS[k], 'sub': notes.get(k) or X.dated(sources.get(k)),
                 'warn': pipeline.left_out_note(self.pack, k), 'hint': None, 'on': self.steps[k],
                 'enabled': not self.busy, 'restore': not export, 'restore_enabled': restorable,
                 'restoring': k in self.marks}
                for k in self.step_keys]
        rows.insert(0, self._photos_row(export, plain, restorable))
        rows.append({'key': S.EDITS, 'title': "My edits", 'sub': "Your changes from the Roster editor, applied after the update",
                     'warn': None, 'hint': X.EDITS_HINT, 'on': self.use_edits, 'enabled': not self.busy,
                     'restore': False, 'restore_enabled': False, 'restoring': False})
        return rows

    def _photos_row(self, export, plain, restorable):
        """First in the list and highlighted: its status says only that the pictures are downloaded automatically."""
        offered = not export and not plain
        on = self.photos and offered
        running = on and self.fetch == 'running'
        sub = (X.PHOTOS_EXPORT if export else X.PHOTOS_NEEDS_RPCS3 if plain else
               X.PHOTOS_OFF if not self.photos else
               X.PHOTOS_RUNNING.format(pct=int(self.fetch_at * 100)) if running else
               X.PHOTOS_READY if self.fetch == 'ready' else
               X.PHOTOS_RETRY if self.fetch == 'failed' else X.photos_will(self.fetch_size))
        return {'key': S.PHOTOS, 'title': X.PHOTOS_TITLE, 'sub': sub, 'warn': None, 'hint': X.PHOTOS_HINT,
                'on': on, 'enabled': not self.busy and offered, 'restore': offered, 'restore_enabled': restorable,
                'restoring': S.PHOTOS in self.marks, 'featured': True,
                'bar': round(self.fetch_at, 3) if running else None}

    def _save_view(self, slot, export, in_place, ready, any_step, full=()):
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
                'button': {'text': button, 'enabled': ready and any_step and not full},
                'note': X.EXPORT_SAVE_NOTE if export else X.SAVE_NOTE}

    def _status_view(self, slot, export, ready, any_step, full=()):
        if self.busy or (self.result is not None and self.status):
            text, tone = self.status or ("Working...", 'body')
        elif full:
            text, tone = f"{X.ROOM_FULL} ({' and '.join(savedata.region(t) for t in full)})", 'bad'
        elif export:
            text, tone = ("Ready." if ready and any_step else
                          "Pick the roster file (step 3)." if self.export_file is None else
                          "Switch on at least one thing to update."), 'muted'
        else:
            text, tone = ("Looking for your rosters..." if self.scanning else
                          "Ready." if ready and any_step else
                          "Start with step 1: find RPCS3." if self.rpcs3 is None else
                          "Switch on at least one thing to update." if slot is not None else
                          "None of the rosters found can be updated."), 'muted'
        return {'text': text, 'tone': tone}
