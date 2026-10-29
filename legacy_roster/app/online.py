"""The "Play online" tab without a window toolkit (Multiplayer.txt; docs/notes/multiplayer.md, S1 results): the player's
online account, the one-press setup, a lobby of two by code, the launch of RPCS3 into the game, and what RPCS3's log says.

Nothing of the player's RPCS3 is changed except through patchinstall (the online entry of the game patch, with the backups
that has) and the roster install (a save of the app's own, "Puck Peak Online ..."; the host's roster is copied into it when
he makes a lobby, the friend's when she joins: pressing Make a lobby / Join is the player's yes, and update_in_place keeps a
backup copy). The roster is the host's: it travels through the lobby server (lobby.py), and both players must have the same
roster CRC and the same game patch before they can be Ready. Online play needs the game patch (owner, 2026-10-25): Set up
online puts it in (after a question) with the online entry. The RPCS3 build is read from its log and told to the friend; a
build older than onlinecfg.MIN_RPCS3 is refused, a different one only gets a note. The game is started with the app's own config
file (onlinecfg.write_config); the player's config files are only read. The lobby calls go to the server (lobby.py)
and may run while RPCS3 runs; copying a roster needs RPCS3 closed.

The pairing in the game (S1): the host presses Create Game Session, the guest Browse Available Game Sessions and Join.
`steps` says which, by role. The tab is a follower of the team list only to know when it shows (`follow` / `hide`).
"""
import datetime
import os
import socket
import struct
import subprocess
import threading
import time
import urllib.parse

from .. import datasource, gamepatch, lobby, onlinecfg, patchinstall, savedata
from ..roster import Roster
from ..stock import StockError
from . import jobs

SLICE = 'online'
POLL = 2.0                              # seconds between asking the server while a lobby is open
STALL_AFTER = 90                        # seconds signed in, with the session still not made or joined, after which the steps are shown to press by hand
START_GRACE = 180                       # seconds after a launch in which the start entry is left ticked (RPCS3 needs time to appear)
LIST_POLL = 5.0                         # seconds between asking for the public lobbies while the tab shows and none is open
ROSTER_NAME = "Puck Peak Online"
NO_RPCS3 = "Pick RPCS3 in Setup first."
NO_ACCOUNT = ("Make your online account once in RPCS3: Configuration > RPCN > Account > Create account. Pick a name and a "
              "password, type your e-mail, then paste the token from the e-mail. Come back here and press Check again.")
CLOSE_RPCS3 = "Close RPCS3 first: the online setup can only be changed while the game is closed."
CLOSE_TO_COPY = "Close RPCS3 so your friend's roster can be copied."
CLOSE_TO_BRING = "Close RPCS3 so your roster can be copied for the lobby."
PICK_ROSTER = "Pick the roster you want to play with in Setup first."
OWN_ROSTER = ("The game's own roster cannot be shared as it is. Press Update in the Update tab once (it makes a roster of your own, "
              "your game's roster stays as it is), then pick that roster in Setup.")
LOBBY_CLOSED = "Your friend left, so the lobby closed. Make a new one, or join another code."
GAME_DIFFERS = "Plays {theirs}; you have {mine}. Different games may lose step during the match."
GAME_NOTE = "{friend} plays {theirs}, you play {mine}. Different games may lose step during the match: the same region and version is safest."
PATCH_DIFFERS = "Plays with game patch {theirs}; you have {mine}. Update the program to the newest version."
PATCH_HINT = "You and your friend have different game patch versions. Update the program to the newest version, then press Ready."
PATCH_NEEDED = "Online play needs the game patch. Press Set up online."
GUEST_UNPATCHED = "Your friend's roster is for the patched game, and your game is not patched. Patch it in Game patch."
GUEST_PATCHED = ("Your friend's roster is for the game without the patch, and online play needs the patch. Your friend: update "
                 "the roster in the program with the game patch in, then make a new lobby.")
GUEST_RIGHTS = ("Your friend's roster was made for another version of the game patch than yours. Both of you: update the "
                "program, press Patch again in Game patch, then make a new lobby.")
GUEST_INCOMPLETE = "Your game patch is missing a part. Press Patch again in Game patch."
GUEST_STALE = "Your game patch is for another version of the game. Press Patch again in Game patch."
PATCH_ASK = ["Online play needs the game patch: 32 teams and the year 2026. This puts it into RPCS3 (every version of the game "
             "you have) with the online part.",
             "While it is patched, the game shows rosters made without the patch as damaged. Update a roster in the Update tab "
             "to make it fit again.",
             "Unpatch (Game patch tab) puts the game back as it was. RPCS3 must be closed."]
BUILD_OLD = ("Your RPCS3 (build {mine}) is older than online play supports (build {need}). Update it in RPCS3: Help > Check for "
             "Updates, then press Check again.")
BUILD_DIFFERS = "{friend}'s RPCS3 is build {theirs}, yours is build {mine}. If the game drops out, update the older one."
BUILD_UNKNOWN = "The program cannot see your RPCS3 version yet. Start RPCS3 once and press Check again."
LOAD_ROSTER = ("The online roster \"{name}\" loads by itself when the game starts. If you see another roster, load it: "
               "Customize > Save/Load/Delete > Load > Rosters > \"{name}\".")
BY_ITSELF = ("Nothing to press: the game starts, signs in and takes you to Select Teams with your friend. Pick your team and side. "
             "The first start after a game or RPCS3 update can take up to half an hour while RPCS3 prepares the game: wait, it is not stuck.")
STALLED = "Is the game still on a menu? Then press these yourself:"
STEPS_ALL = ("Press X on the welcome screen, if there is one.", "Play > Online > Online Versus Play.",
             "Move to \"Ranked Online Play Now Search\" and press X.")
STEPS_HOST = ("Choose Create Game Session and press X.", "Press X on the settings screen and wait for your friend.")
STEPS_GUEST = ("Choose Browse Available Game Sessions and press X.", "Pick your friend's session and press X to join.")
PROGRESS = {'offline': "Not in the game yet", 'in_game': "In the game", 'signed_in': "Signed in", 'hosting': "Waiting for a friend",
            'browsing': "Looking for the session", 'joined': "Joined", 'playing': "Playing", 'gone': "Left"}
COUNTDOWN = 3


class OnlineController:
    def __init__(self, host, update, poll=POLL, autopoll=True, list_poll=LIST_POLL):
        self.host, self.update = host, update
        self.lock = threading.RLock()
        self.poll_every, self.autopoll, self.list_every = poll, autopoll, list_poll
        self.shown = False
        self.busy = None                # what runs now ("Setting up..."), None when nothing
        self.note = None                # {'text', 'tone'}: the last result
        self.checked = False            # looked at the PC at least once
        self.account = None             # the RPCN name in RPCS3's rpcn.yml
        self.title = None               # the game version the lobby is played with (title id)
        self.state = {}                 # patchinstall.state()[title]
        self.build = None               # the RPCS3 build number from its log (None: not known)
        self.roster = None              # {'name', 'folder', 'crc'} of the installed online roster, None without one
        self.brought = None             # the name of the roster the host brought to his lobby
        self.copying = None             # "Getting your friend's roster...", None when nothing is copied
        self.copy_crc = None            # the host's roster CRC the guest's copy was tried for (not tried again for it)
        self._sent_me = None            # the (patch, game) last sent to the server with update_me
        self.server = None              # True / False / None: the lobby server answered at the last look
        self.lobby = None               # the server's lobby as last seen
        self.code = None                # its code
        self.launched = None            # the code the game was started for
        self.log = None                 # onlinecfg.log_state of the running game's log
        self._tail = None               # onlinecfg.LogTail of this start's log
        self.auto = False               # the game can start by itself into the lobby's search (looked up in refresh)
        self.started_at = 0.0           # time.time() of the launch: only a log written after it says anything about this start
        self.signed_at = None           # time.time() when the log first showed the sign-in of this start
        self.by_itself = False          # the game was started with the online start entry ticked (it is unticked after the boot)
        self.countdown = None
        self._timer = None
        self.public = True              # the next lobby made is listed for everybody (0.65: public unless the host picks private)
        self.open_lobbies = []          # the public lobbies waiting for a friend, as the server listed them
        self.open_error = None          # why the list could not be read (None when it could)
        self._list_timer = None

    def changed(self):
        self.host.changed(SLICE)

    # --- the tab shows or rests ----------------------------------------------------------------------------------
    def follow(self, team=None):
        with self.lock:
            self.shown = True
        self.refresh()
        self._arm_list(0.3)

    def hide(self):
        with self.lock:
            self.shown = False
        self._stop_list_timer()

    def roster_changed(self):
        pass

    def closing(self):
        """The window closes: leave an open lobby (best effort) and stop asking the server."""
        self._stop_timer()
        self._stop_list_timer()
        self._clear_start()
        code, who = self.code, self.account
        if code and who:
            try:
                lobby.leave(code, who)
            except lobby.LobbyError:
                pass
        return True

    # --- what the PC and the server say ---------------------------------------------------------------------------
    def rpcs3(self):
        rpcs3 = getattr(self.update, 'rpcs3', None)
        return None if rpcs3 is None or getattr(rpcs3, 'plain', False) else rpcs3

    def refresh(self):
        """Look again: the account, the patch, the online roster and the server (in the background)."""
        with self.lock:
            if self.busy:
                return
            rpcs3 = self.rpcs3()
            versions = list(getattr(self.update, 'versions', []) or [])
            self.busy = "Looking..."
        self.changed()

        def work():
            self._clear_start()
            found = {'account': None, 'title': None, 'state': {}, 'roster': None, 'server': None, 'build': None, 'auto': False}
            if rpcs3 is None:
                return found
            found['account'] = onlinecfg.account(rpcs3)
            found['build'] = onlinecfg.rpcs3_build(rpcs3)
            states = patchinstall.state(rpcs3)
            titles = [t for t in versions if t in states] or [t for t in states if rpcs3.game_disc(t)]
            ready = [t for t in titles if states[t]['online']]
            title = (ready or titles or [None])[0]
            found['title'], found['state'] = title, states.get(title, {})
            if title:
                found['roster'] = self._installed(rpcs3, title)
                found['auto'] = patchinstall.auto_start(rpcs3, title)
            found['server'] = self._server_up()
            return found

        def done(found):
            with self.lock:
                self.busy = None
                self.checked = True
                for key, value in found.items():
                    setattr(self, key, value)
            self.changed()
            self._sync_me()

        def failed(message):
            with self.lock:
                self.busy = None
                self.checked = True
                self.note = {'text': message, 'tone': 'bad'}
            self.changed()

        jobs.run(work, done, failed, expected=(OSError, patchinstall.PatchError))

    def _installed(self, rpcs3, title):
        """The online roster in the save folder: {'name', 'folder', 'crc', 'patch_roster': made for the game patch, 'rights': the
        bits of its player rights} (None for what cannot be read), or None without one."""
        for slot in savedata.list_rosters(rpcs3.savedata):
            if slot.title_id == title and slot.name.startswith(ROSTER_NAME):
                found = {'name': slot.name, 'folder': slot.folder, 'crc': None, 'patch_roster': None, 'rights': None}
                try:
                    with open(slot.sys_data, 'rb') as f:
                        data = f.read()
                    found['crc'] = onlinecfg.roster_crc(data)
                    R = Roster(data)
                    found['patch_roster'], found['rights'] = gamepatch.is_patch_roster(R), R.P.field(gamepatch.RIGHTS).bits
                except (OSError, ValueError, KeyError, IndexError, struct.error, AttributeError):
                    pass
                return found
        return None

    @staticmethod
    def _server_up():
        """Does the lobby server answer (any answer, also "no such lobby", counts)?"""
        try:
            lobby.status('AAAAAA', 'check')
        except lobby.Unreachable:
            return False
        except lobby.LobbyError:
            return True
        return True

    # --- the setup -------------------------------------------------------------------------------------------------
    def marks(self):
        """The player's own marks: the online entry is on, the game is patched, both ('ready': a lobby can be made or joined).
        The roster and the patch version are the lobby's business."""
        online = bool(self.state.get('online') and not self.state.get('stale'))
        patched = bool(self.state.get('patched') and not self.state.get('stale'))
        return {'online': online, 'patched': patched, 'ready': online and patched,
                'game': 'open' if savedata.running_rpcs3() else 'closed'}

    def build_problem(self):
        """Why this RPCS3 is too old for online play (None when it is fine or not known)."""
        if self.build is not None and self.build < onlinecfg.MIN_RPCS3:
            return BUILD_OLD.format(mine=self.build, need=onlinecfg.MIN_RPCS3)
        return None

    def build_note(self):
        """{'text', 'tone'} about the RPCS3 builds of the two players (None: nothing to say)."""
        if self.build is None:
            return {'text': BUILD_UNKNOWN, 'tone': 'warn'}
        friend = next((m for m in (self.lobby or {}).get('members', []) if m['name'] != self.account), None)
        theirs = str((friend or {}).get('rpcs3') or '')
        if theirs and theirs != str(self.build):
            return {'text': BUILD_DIFFERS.format(friend=friend['name'], theirs=theirs, mine=self.build), 'tone': 'warn'}
        return None

    def game_note(self):
        """{'text', 'tone'} when the two players run another region or game version (a warning: they can still play)."""
        friend = next((m for m in (self.lobby or {}).get('members', []) if m['name'] != self.account), None)
        theirs, mine = str((friend or {}).get('version') or ''), self.game_word()
        if theirs and theirs != mine:
            return {'text': GAME_NOTE.format(friend=friend['name'], theirs=theirs, mine=mine), 'tone': 'warn'}
        return None

    def guest_problem(self):
        """Why this guest's game cannot load the host's roster copied to this PC, or None (also for the host, and before the copy
        is here). The lobby only compares patch versions; this compares the roster itself with the game as RPCS3 has it now, so a
        guest who patches or unpatches in the lobby is checked again. Stricter than UpdateController.misfit: player rights that
        cannot be read do not pass."""
        me, theirs, mine = self._member(), (self.lobby or {}).get('roster'), self.roster
        if me is None or me.get('role') != 'guest' or not theirs or not mine \
                or str(mine.get('crc') or '').lower() != str(theirs.get('crc') or '').lower() or mine.get('patch_roster') is None:
            return None
        if self.state.get('stale'):
            return GUEST_STALE
        patched, made = bool(self.state.get('patched')), mine['patch_roster']
        if made and not patched:
            return GUEST_UNPATCHED
        if patched and not made:
            return GUEST_PATCHED
        if made:
            game, own = self.state.get('rights'), mine.get('rights')
            if not game:
                return GUEST_INCOMPLETE
            if game != own:
                return GUEST_RIGHTS
        return None

    def patch_word(self):
        """The patch as the lobby compares it: the patch version, or "none" without the 32-team patch."""
        return (self.state.get('version') or 'patched') if self.state.get('patched') else 'none'

    def setup(self):
        """The "Set up online" button: the game patch (after a question) with the online entry, and the app's config. The
        roster comes with the lobby."""
        with self.lock:
            rpcs3 = self.rpcs3()
            if self.busy or rpcs3 is None:
                return
            if savedata.running_rpcs3():
                self.note = {'text': CLOSE_RPCS3, 'tone': 'bad'}
                self.changed()
                return
            if not self.account:
                self.note = {'text': NO_ACCOUNT, 'tone': 'bad'}
                self.changed()
                return
            patch = not self.marks()['patched']
        if patch:
            self.update.ask("Patch the game for online play?", PATCH_ASK,
                            [("Patch the game", 'yes', 'primary'), ("Cancel", 'no', 'plain')], {'yes': self._setup})
            return
        self._setup()

    def _setup(self):
        with self.lock:
            rpcs3 = self.rpcs3()
            if self.busy or rpcs3 is None:
                return
            titles, title = list(self.update.versions), self.title or (self.update.versions or [None])[0]
            patch = not self.marks()['patched']
            intro, login = getattr(self.update, 'skip_intro', True), getattr(self.update, 'no_login', False)
            self.busy = "Setting up online play..." if not patch else "Patching the game and setting up online play..."
            self.note = None
        self.changed()

        def work():
            if patch:       # no question about the picked roster afterwards: the online save holds the host's roster
                patchinstall.install_patch(rpcs3, titles, intro=intro, login=login)
            patchinstall.set_online(rpcs3, titles, True)
            patchinstall.set_switches(rpcs3, titles, True, login)       # the intro skip: the lobby's start needs the quick boot
            onlinecfg.write_config(rpcs3, title, self._address())
            return True

        def done(_):
            with self.lock:
                self.busy = None
                self.note = {'text': "Ready to play online.", 'tone': 'good'}
            rescan = getattr(self.update, 'set_rpcs3', None)
            if patch and rescan:        # the Update tab marks the rosters the patched game cannot load
                rescan(rpcs3.where, quiet=True)
            self.refresh()

        def failed(message):
            with self.lock:
                self.busy = None
                self.note = {'text': message, 'tone': 'bad'}
            self.changed()

        jobs.run(work, done, failed, expected=(patchinstall.PatchError, datasource.Offline, StockError, OSError, ValueError))

    def _put_roster(self, rpcs3, title, data):
        """Install `data` as the online roster of `title`: a new save, or in place over the one that is there (backup first)."""
        have = self.roster
        slots = savedata.list_rosters(rpcs3.savedata)
        if have:
            slot = next(s for s in slots if s.folder == have['folder'])
            savedata.update_in_place(rpcs3.savedata, slot, data, name=slot.name, expected=None)
            return
        source = next((s for s in slots if s.title_id == title), None) or next(iter(slots), None)
        if source is None:
            raise OSError("Save a roster in the game once first, so there is a save to copy the pictures from.")
        savedata.install(rpcs3.savedata, source, data, f"{ROSTER_NAME} {datetime.date.today():%Y-%m-%d}", title_id=title)

    @staticmethod
    def _address():
        """The IP address of the game server now (RPCS3's IP swap list takes an address, not a name)."""
        return socket.gethostbyname(urllib.parse.urlsplit(lobby.api_url()).hostname)

    # --- the lobby -------------------------------------------------------------------------------------------------
    def _me(self):
        """(name, roster CRC, patch, game version, RPCS3 build) as the lobby wants them from a guest."""
        return (self.account, (self.roster or {}).get('crc') or '', self.patch_word(), self.game_word(),
                self._build_text())

    def game_word(self):
        """The game as the lobby compares it: the region and the version ("EU 01.00", "NA 01.01"). Two games of another region or
        version did not stay in step in the lab (a 1.01 against a 1.00 never finished loading, a NA against an EU one lost step
        in the first period), so the server lets only the same word play together."""
        region = 'NA' if str(self.title or '').startswith('BLUS') else 'EU'
        return f"{region} {self.state.get('game') or '01.00'}"

    def _build_text(self):
        return '' if self.build is None else str(self.build)

    def bring(self):
        """(the roster the host would bring, why he cannot bring it): the one picked in Setup."""
        slot = getattr(self.update, 'selected_slot', lambda: None)()
        if slot is None:
            return None, PICK_ROSTER
        if getattr(slot, 'disc', False):
            return slot.name, OWN_ROSTER
        why = (getattr(self.update, 'usable', {}) or {}).get(slot.folder) or self.update.misfit(slot)
        return slot.name, (str(why) if why else None)

    def set_public(self, on):
        with self.lock:
            self.public = bool(on)
        self.changed()

    def create(self, public=None):
        """Make a lobby with the roster picked in Setup: it is copied to the app's own online save, the lobby is opened with its
        CRC and the roster goes up to the server for the friend. A public lobby is also in everybody's list."""
        with self.lock:
            if public is not None:
                self.public = bool(public)
            rpcs3 = self.rpcs3()
            if self.busy or rpcs3 is None or not self.account or self.code:
                return
            if not self.marks()['ready']:
                self.note = {'text': PATCH_NEEDED if self.marks()['online'] else "Set up online first.", 'tone': 'bad'}
                self.changed()
                return
            old = self.build_problem()
            if old:
                self.note = {'text': old, 'tone': 'bad'}
                self.changed()
                return
            name, why = self.bring()
            slot = self.update.selected_slot()
            if why:
                self.note = {'text': why, 'tone': 'bad'}
                self.changed()
                return
            if savedata.running_rpcs3():
                self.note = {'text': CLOSE_TO_BRING, 'tone': 'bad'}
                self.changed()
                return
            title, account, patch = self.title, self.account, self.patch_word()
            game, listed, build = self.game_word(), self.public, self._build_text()
            same = bool(self.roster and slot.folder == self.roster['folder'])
            self.busy = "Sending your roster..."
            self.note = None
        self.changed()

        def work():
            with open(slot.sys_data, 'rb') as f:
                data = f.read()
            crc = onlinecfg.roster_crc(data)
            if not same:
                self._put_roster(rpcs3, title, data)
            installed = self._installed(rpcs3, title)
            answer = lobby.create(account, crc, patch, game, public=listed, roster_name=name, rpcs3=build)
            try:
                return lobby.put_roster(answer['code'], account, data), installed
            except lobby.LobbyError:
                try:
                    lobby.leave(answer['code'], account)
                except lobby.LobbyError:
                    pass
                raise

        def done(result):
            answer, installed = result
            with self.lock:
                self.busy = None
                self.roster, self.brought, self.copy_crc = installed, name, None
            self._take(answer)

        def failed(message):
            with self.lock:
                self.busy = None
                self.note = {'text': message, 'tone': 'bad'}
            self.changed()

        jobs.run(work, done, failed, expected=(lobby.LobbyError, savedata.RosterFull, savedata.InPlaceError, OSError, ValueError))

    def join(self, text):
        code = lobby.clean_code(text)
        if code is None:
            with self.lock:
                self.note = {'text': "A lobby code is six letters, like KDMQRS.", 'tone': 'bad'}
            self.changed()
            return
        self._lobby_call(lambda who: lobby.join(code, *who))

    def ready(self, on=True):
        with self.lock:
            code, name = self.code, self.account
            problem = self.guest_problem() if on else None
            if problem:
                self.note = {'text': problem, 'tone': 'bad'}
        if problem:
            self.changed()
            return
        if code:
            self._lobby_call(lambda who: lobby.ready(code, name, on))

    def leave(self):
        with self.lock:
            code, name = self.code, self.account
            self.lobby = self.code = self.launched = self.log = self.countdown = None
            self.brought = self.copy_crc = self._sent_me = None
        self._stop_timer()
        self._clear_start()
        self.changed()
        self._arm_list(0.3)
        if code and name:
            jobs.run(lambda: lobby.leave(code, name), None, None, expected=(lobby.LobbyError,))

    def _lobby_call(self, call):
        with self.lock:
            if self.busy or not self.account:
                return
            if not self.marks()['ready']:
                self.note = {'text': PATCH_NEEDED if self.marks()['online'] else "Set up online first.", 'tone': 'bad'}
                self.changed()
                return
            old = self.build_problem()
            if old:
                self.note = {'text': old, 'tone': 'bad'}
                self.changed()
                return
            who = self._me()
            self.busy = "Asking the server..."
        self.changed()

        def done(answer):
            with self.lock:
                self.busy = None
                self.note = None
            self._take(answer)

        def failed(message):
            with self.lock:
                self.busy = None
                self.note = {'text': message, 'tone': 'bad'}
            self.changed()

        jobs.run(lambda: call(who), done, failed, expected=(lobby.LobbyError,))

    def _take(self, answer):
        """The server's lobby `answer`: keep it, start the game when it says "starting", get the host's roster when this
        PC lacks it, tell the server about a changed patch, ask again soon."""
        with self.lock:
            if answer.get('state') == 'expired':
                self.lobby = self.code = self.launched = self.brought = None
                self.note = {'text': LOBBY_CLOSED, 'tone': 'bad'}
                self._arm_list(0.3)
            else:
                self.lobby, self.code = answer, answer.get('code')
            self.server = True
        self.changed()
        if answer.get('state') == 'starting':
            self._start_game()
        self._sync_roster()
        self._sync_me()
        self._arm()

    def _member(self):
        """This player's member entry of the lobby as last seen (None outside a lobby)."""
        return next((m for m in (self.lobby or {}).get('members', []) if m['name'] == self.account), None)

    def _sync_roster(self):
        """A guest whose online roster is not the host's: download it, check it, install it, tell the server."""
        with self.lock:
            me, roster = self._member(), (self.lobby or {}).get('roster')
            if me is None or me['role'] != 'guest' or not roster or self.lobby.get('state') not in ('open', 'starting'):
                return
            want = str(roster['crc']).lower()
            if str((self.roster or {}).get('crc') or '').lower() == want or self.copying or self.copy_crc == want:
                return
            rpcs3, title, code, name = self.rpcs3(), self.title, self.code, self.account
            if rpcs3 is None or title is None:
                return
            if savedata.running_rpcs3():
                self.note = {'text': CLOSE_TO_COPY, 'tone': 'bad'}
                self.changed()
                return
            self.copying, self.copy_crc, self.note = "Getting your friend's roster...", want, None
            patch, game, build = self.patch_word(), self.game_word(), self._build_text()
        self.changed()

        def work():
            data = lobby.get_roster(code, name)
            try:
                crc = onlinecfg.roster_check(data)
            except ValueError as err:
                raise ValueError(f"The roster your friend sent is not a roster the game can read ({err}). It was not used.") from err
            if crc.lower() != want:
                raise ValueError("The roster did not arrive correctly. Leave the lobby and join again.")
            self._put_roster(rpcs3, title, data)
            return lobby.update_me(code, name, crc, patch, game, build), self._installed(rpcs3, title)

        def done(result):
            answer, installed = result
            with self.lock:
                self.copying, self.roster = None, installed
            self._take(answer)

        def failed(message):
            with self.lock:
                self.copying = None
                self.note = {'text': message, 'tone': 'bad'}
            self.changed()

        jobs.run(work, done, failed, expected=(lobby.LobbyError, savedata.RosterFull, savedata.InPlaceError, OSError, ValueError))

    def _sync_me(self):
        """The patch changed since the server last heard (the player patched or unpatched): tell it, so the lobby compares anew."""
        with self.lock:
            me = self._member()
            if me is None or self.busy or self.copying or self.lobby.get('state') not in ('open', 'starting'):
                return
            mine = (self.patch_word(), self.game_word(), self._build_text())
            if (me.get('patch'), me.get('version'), me.get('rpcs3') or '') == mine or self._sent_me == mine:
                return
            self._sent_me = mine
            code, name, crc = self.code, self.account, (self.roster or {}).get('crc') or ''

        def failed(message):
            with self.lock:
                self._sent_me = None
                self.note = {'text': message, 'tone': 'bad'}
            self.changed()

        jobs.run(lambda: lobby.update_me(code, name, crc, *mine), self._take, failed, expected=(lobby.LobbyError,))

    def poll_once(self):
        """Ask the server about the open lobby (and read the game's log): called every POLL seconds while a lobby is open."""
        with self.lock:
            code, name = self.code, self.account
            launched = self.launched
        if not code:
            return
        try:
            self._take(lobby.status(code, name))
        except lobby.Unreachable:
            with self.lock:
                self.server = False
            self.changed()
            self._arm()
        except lobby.LobbyError as err:
            with self.lock:
                self.lobby = self.code = None
                self.note = {'text': str(err), 'tone': 'bad'}
            self.changed()
            self._arm_list(0.3)
        if launched:
            self._read_log()

    def _arm(self):
        if not self.autopoll:
            return
        with self.lock:
            if not self.code or self._timer is not None:
                return
            self._timer = threading.Timer(self.poll_every, self._tick)
            self._timer.daemon = True
            self._timer.start()

    def _tick(self):
        with self.lock:
            self._timer = None
        self.poll_once()

    # --- the public lobbies ---------------------------------------------------------------------------------------
    def list_once(self):
        """Ask the server for the public lobbies (only where a lobby could be joined now: the tab shows, nothing is open)."""
        with self.lock:
            if not self.shown or self.code or self.busy or self.view() != 'ready':
                return
        try:
            found = lobby.lobbies()
            error = None
        except lobby.Unreachable:
            found, error = None, "Puck Peak's online server is not reachable right now."
        except lobby.LobbyError as err:
            found, error = None, str(err)
        with self.lock:
            if found is not None:
                self.open_lobbies = found
            self.open_error = error
        self.changed()

    def refresh_list(self):
        """The Refresh button: ask now, in the background."""
        jobs.run(self.list_once, None, None, expected=())

    def _arm_list(self, delay=None):
        if not self.autopoll:
            return
        with self.lock:
            if not self.shown or self._list_timer is not None:
                return
            self._list_timer = threading.Timer(self.list_every if delay is None else delay, self._list_tick)
            self._list_timer.daemon = True
            self._list_timer.start()

    def _list_tick(self):
        with self.lock:
            self._list_timer = None
        self.list_once()
        self._arm_list()

    def _stop_list_timer(self):
        with self.lock:
            timer, self._list_timer = self._list_timer, None
        if timer is not None:
            timer.cancel()

    def rows(self):
        """The public lobbies as the tab lists them: each with `joinable` and, when it cannot be joined, `why` (another game patch
        version: update the program; another region or game version)."""
        mine = self.patch_word()
        out = []
        for row in self.open_lobbies:
            item = dict(row)
            item['joinable'], item['why'] = True, None
            if row.get('patch') and row['patch'] != mine:
                item['joinable'] = False
                item['why'] = PATCH_DIFFERS.format(theirs=row['patch'], mine=mine)
            elif row.get('version') and row['version'] != self.game_word():      # a warning only: the lobby can be joined
                item['warn'] = GAME_DIFFERS.format(theirs=row['version'], mine=self.game_word())
            out.append(item)
        return out

    def _stop_timer(self):
        with self.lock:
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    # --- the game ----------------------------------------------------------------------------------------------------
    def _start_game(self):
        """Both are Ready: start RPCS3 into the game (not again for the same lobby, and not when a game is open)."""
        with self.lock:
            code, rpcs3, title = self.code, self.rpcs3(), self.title
            if self.launched == code or rpcs3 is None or title is None:
                return
            problem = self.guest_problem()
            if problem:
                self.note = {'text': problem, 'tone': 'bad'}
            else:
                self.launched = code
        if problem:
            self.changed()
            if code:
                self._lobby_call(lambda who: lobby.ready(code, who[0], False))
            return
        if savedata.running_rpcs3():
            with self.lock:
                self.note = {'text': "Your game is open. Press nothing here; we follow it.", 'tone': 'good'}
            self.changed()
            return
        try:
            if self.roster:
                savedata.boot_first(rpcs3.savedata, self.roster['folder'])      # the game loads it by itself at boot
            config = onlinecfg.write_config(rpcs3, title, self._address())
            self.by_itself = patchinstall.auto_start(rpcs3, title)
            if self.by_itself:      # for this start only; _read_log unticks it as soon as the game has booted
                patchinstall.set_online_start(rpcs3, [title], True)
            self.started_at, self.signed_at, self._tail = time.time(), None, None
            args = onlinecfg.launch_args(rpcs3, title, config)
            if args is None and not rpcs3.command():
                raise OSError("The program does not know how to start RPCS3. In Setup, pick the RPCS3 program itself (not only its folder).")
            if args is None:
                raise OSError("RPCS3 does not say where your copy of the game is. Start the game once from RPCS3's list.")
            flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
            savedata.launch(args, cwd=rpcs3.launch_dir(), close_fds=True, creationflags=flags)
        except (OSError, patchinstall.PatchError) as err:
            self._untick_start()
            with self.lock:
                self.launched = None
                self.note = {'text': f"The game could not be started: {err}", 'tone': 'bad'}
            self.changed()

    def _read_log(self):
        rpcs3 = self.rpcs3()
        if rpcs3 is None:
            return
        path = onlinecfg.log_path(rpcs3)
        try:
            if os.path.getmtime(path) < self.started_at:       # the last session's log says nothing about this start
                return
            if self._tail is None or self._tail.path != path:
                self._tail = onlinecfg.LogTail(path)
            log = self._tail.read()
        except OSError:
            return
        with self.lock:
            self.log = log
            if log['name'] and self.signed_at is None:
                self.signed_at = time.time()
        if log['name'] or log['bound']:     # the game has started and read its patches
            self._untick_start()
        self.changed()

    def _clear_start(self):
        """Whatever happened to the last start (the program closed, a crash), the online start entry must not stay ticked: untick it
        in every version when RPCS3 is not running (the next normal boot would dive into a search)."""
        rpcs3 = self.rpcs3()
        if rpcs3 is None or savedata.running_rpcs3():
            return
        if self.by_itself and time.time() - self.started_at < START_GRACE:     # RPCS3 is just starting: the game has yet to read it
            return
        try:
            patchinstall.set_online_start(rpcs3, list(self.update.versions), False)
            self.by_itself = False
        except (OSError, patchinstall.PatchError):
            pass

    def _untick_start(self):
        """The online start entry is for one start only: untick it (RPCS3 must be closed; if it is not, the next try does it)."""
        rpcs3, title = self.rpcs3(), self.title
        if rpcs3 is None or title is None or not getattr(self, 'by_itself', False):
            return
        try:
            patchinstall.set_online_start(rpcs3, [title], False)
            self.by_itself = False
        except (OSError, patchinstall.PatchError):
            pass

    # --- what the page shows -------------------------------------------------------------------------------------------
    def by_itself_possible(self):
        """Will the game take both players to Select Teams with no key (game version 1.00 or the update 1.01, with the start entry and the screens)?"""
        return self.auto

    def stalled(self):
        """The game has been signed in for a while and its player still has no session (no host, no guest, not playing): whatever
        the reason, the steps are then shown to press by hand (a game that went by itself never gets here)."""
        me = self._member()
        return bool(self.launched and self.signed_at is not None and time.time() - self.signed_at > STALL_AFTER
                    and me and me.get('progress') in (None, 'offline', 'in_game', 'signed_in'))

    def steps(self, role):
        """The things to press in the game, by role (the host creates the session, the guest joins it)."""
        load = [LOAD_ROSTER.format(name=self.roster['name'])] if self.roster else []
        by_hand = list(STEPS_ALL) + list(STEPS_HOST if role == 'host' else STEPS_GUEST)
        if self.by_itself_possible():
            return load + [BY_ITSELF] + ([STALLED] + by_hand if self.stalled() else [])
        return load + by_hand

    def view(self):
        """The tab's state word: no-rpcs3 | no-account | not-set-up | ready | in-lobby | starting | in-game | failed."""
        if self.rpcs3() is None:
            return 'no-rpcs3'
        if not self.account:
            return 'no-account'
        if not self.marks()['ready']:
            return 'not-set-up'
        if not self.lobby:
            return 'ready'
        if self.log and (self.log['refused'] or self.log['fatal'] or self.log['old'] or not self.log['signaling']):
            return 'failed'
        if self.launched:
            return 'in-game'
        return 'starting' if self.lobby.get('state') == 'starting' else 'in-lobby'

    def why(self):
        """What went wrong in the game, in the player's words (None when nothing)."""
        log = self.log
        if not log or not self.launched:
            return None
        if log['fatal']:
            return "RPCS3 stopped. Close it and press Ready again."
        if log['old']:
            return "Your RPCS3 is too old for the online server. Update RPCS3 (rpcs3.net, Download), then start again."
        if log['refused']:
            return "Sign-in failed: check your account in RPCS3 (Configuration > RPCN)."
        if not log['signaling']:
            return "RPCN did not answer. Check your internet connection and your firewall, then start again."
        return None

    def hint(self):
        """What to do when the lobby says the patches differ, this PC lost its patch, or the host's roster does not fit this game
        (None otherwise)."""
        me = self._member()
        problem = self.guest_problem()
        if problem:
            return problem
        if me and not self.marks()['patched']:
            return PATCH_NEEDED
        return PATCH_HINT if me and not me.get('patch_ok', True) else None

    def snapshot(self):
        with self.lock:
            role = (self._member() or {}).get('role')
            bring, bring_why = self.bring()
            return {'state': self.view(), 'account': self.account, 'title': self.title, 'busy': self.busy or self.copying,
                    'note': self.note, 'checked': self.checked, 'server': self.server, 'marks': self.marks(),
                    'roster': self.roster['name'] if self.roster else None, 'brought': self.brought,
                    'bring': bring, 'bring_why': bring_why, 'patch': self.patch_word(), 'hint': self.hint(),
                    'guest_problem': self.guest_problem(),
                    'build': self.build, 'build_note': self.build_note(), 'game_note': self.game_note(), 'build_old': self.build_problem(),
                    'lobby': self.lobby, 'code': self.code, 'role': role, 'steps': self.steps(role) if role else [],
                    'public': self.public, 'open': self.rows(), 'open_error': self.open_error,
                    'progress': PROGRESS, 'why': self.why(), 'no_account': NO_ACCOUNT, 'launched': bool(self.launched)}
