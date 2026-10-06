"""Find roster saves in an RPCS3 (or copied PS3) savedata folder and write new ones.

A roster save is a folder <TITLEID>02NN (BLES02153 = Europe, BLUS31540 = North America) with
ICON0.PNG, PARAM.SFO and SYS-DATA. The updater never changes an existing folder: every update
goes into a new one with the next free number.

The two versions read the same SYS-DATA (the community shares one file for both); their
PARAM.SFO differs only in TITLE and the folder name. So a roster can be saved for the other
version too (install(title_id=...)).

The window asks for RPCS3 itself (find_rpcs3); the command line also takes a save folder
directly (find_savedata).

Where RPCS3 keeps its data depends on the system: on Windows next to rpcs3.exe; on Linux in
~/.config/rpcs3 (the Flatpak: ~/.var/app/net.rpcs3.RPCS3/config/rpcs3), on a Mac in
~/Library/Application Support/rpcs3 (data_folders()). The program itself may be rpcs3.exe, the
rpcs3 program or AppImage, or RPCS3.app; the player may also point at the data folder.
"""
import datetime
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys

from .sfo import FMT_INT, FMT_SPECIAL, FMT_STRING, Sfo
from .tdb import ROSTER_MAGIC

SLOT_NAME = re.compile(r'^([A-Z]{4}\d{5})02(\d{2})$')
ANY_SAVE = re.compile(r'^[A-Z]{4}\d{9}$')     # profile, hockey card and other saves of the game
TOOL_NAME = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}|^R\d{6}-\d{4}$')   # names this tool gives its saves
FILES = ('ICON0.PNG', 'PARAM.SFO', 'SYS-DATA')
# the game's versions: title id -> what the window calls it, and the TITLE of their saves' PARAM.SFO
GAMES = {'BLES02153': 'EU', 'BLUS31540': 'NA'}
TITLES = {'BLES02153': "NHL™ Legacy Edition", 'BLUS31540': "NHL® Legacy Edition"}
WINDOWS, MAC = os.name == 'nt', sys.platform == 'darwin'
# what the player is asked to pick, in his system's words
PICK_RPCS3 = ("Pick the file rpcs3.exe in your RPCS3 folder." if WINDOWS else
              "Pick RPCS3.app, or RPCS3's folder (~/Library/Application Support/rpcs3)." if MAC else
              "Pick the rpcs3 program or AppImage, or RPCS3's folder (~/.config/rpcs3).")


def data_folders():
    """Where an installed RPCS3 keeps its data on this system (none on Windows: next to the program)."""
    home = os.path.expanduser('~')
    if WINDOWS:
        return []
    if MAC:
        return [os.path.join(home, 'Library', 'Application Support', 'rpcs3')]
    config = os.environ.get('XDG_CONFIG_HOME') or os.path.join(home, '.config')
    return [os.path.join(config, 'rpcs3'), os.path.join(home, '.var', 'app', 'net.rpcs3.RPCS3', 'config', 'rpcs3')]


def is_program(path):
    """rpcs3.exe, the rpcs3 program, an RPCS3 AppImage or RPCS3.app."""
    name = os.path.basename(os.path.normpath(path)).lower()
    if os.path.isdir(path):
        return name.endswith('.app') and 'rpcs3' in name
    return os.path.isfile(path) and (name in ('rpcs3.exe', 'rpcs3') or (name.endswith('.appimage') and 'rpcs3' in name))


def has_data(folder):
    """Does RPCS3 keep its data in this folder (its virtual hard disk or its config is there)?"""
    return any(os.path.exists(os.path.join(folder, n)) for n in ('dev_hdd0', os.path.join('config', 'vfs.yml'), 'vfs.yml'))


def default_rpcs3():
    """An installed RPCS3's data folder in the usual place, if there is one (Linux, Mac), else None."""
    return next((f for f in data_folders() if has_data(f)), None)


def region(title_id):
    """'EU', 'NA', or the title id itself for anything else."""
    return GAMES.get(title_id, title_id)


def title_of(region_name):
    """The title id of 'EU' or 'NA' (None when unknown)."""
    return next((t for t, r in GAMES.items() if r == (region_name or '').upper()), None)


class Slot:
    def __init__(self, path):
        self.path = path
        self.folder = os.path.basename(path)
        m = SLOT_NAME.match(self.folder)
        self.title_id, self.number = m.group(1), int(m.group(2))
        self.sys_data = os.path.join(path, 'SYS-DATA')
        self.modified = datetime.datetime.fromtimestamp(os.path.getmtime(self.sys_data))
        try:
            self.name = Sfo.load(os.path.join(path, 'PARAM.SFO')).get('SUB_TITLE', '') or self.folder
        except (OSError, ValueError):
            self.name = self.folder

    @property
    def tool_made(self):
        return bool(TOOL_NAME.match(self.name))

    @property
    def region(self):
        return region(self.title_id)

    def label(self):
        return f"{self.name}   ({self.folder}, {self.region}, saved {self.modified:%Y-%m-%d %H:%M})"


class DiscSlot:
    """The game's own roster, on the disc of one version of the game: listed with the roster
    saves, so a player without any roster can start from it (stock.py). It is no save folder;
    `read()` makes the roster from the disc."""
    disc = True
    tool_made = False

    def __init__(self, title_id, disc_path):
        self.title_id, self.path = title_id, disc_path
        self.folder = f"{title_id} game"
        self.name = "The game's own roster"
        self.number = None
        self.sys_data = None
        try:
            self.modified = datetime.datetime.fromtimestamp(os.path.getmtime(disc_path))
        except OSError:
            self.modified = datetime.datetime.now()

    @property
    def region(self):
        return region(self.title_id)

    def label(self):
        return f"{self.name}   (your {self.region} game disc)"

    def read(self):
        from . import stock
        return stock.from_disc(self.path)


def read_roster(slot):
    """The SYS-DATA bytes of a roster save, or of the game's own roster for a DiscSlot."""
    if getattr(slot, 'disc', False):
        return slot.read()
    with open(slot.sys_data, 'rb') as f:
        return f.read()


def roster_sfo(title_id, folder, name):
    """The PARAM.SFO of a roster save, made from scratch (the game's own key set and sizes), for a
    version of the game that has no save to copy one from."""
    text = lambda value: value.encode('utf-8') + b'\0'
    number = lambda value: value.to_bytes(4, 'little')
    return Sfo.new([
        ('*ICON0.PNG', FMT_INT, number(0), 4), ('*SYS-DATA', FMT_INT, number(1), 4),
        ('ACCOUNT_ID', FMT_SPECIAL, b'0' * 16, 16), ('ATTRIBUTE', FMT_INT, number(0), 4),
        ('CATEGORY', FMT_STRING, text('SD'), 4), ('DETAIL', FMT_STRING, text('Rosters'), 1024),
        ('PARAMS', FMT_STRING, text(''), 1024), ('PARAMS2', FMT_STRING, text(''), 12),
        ('PARENTAL_LEVEL', FMT_INT, number(0), 4), ('RPCS3_BLIST', FMT_STRING, text('ICON0.PNG/SYS-DATA'), 20),
        ('SAVEDATA_DIRECTORY', FMT_STRING, text(folder), 32), ('SAVEDATA_LIST_PARAM', FMT_STRING, text('000'), 8),
        ('SUB_TITLE', FMT_STRING, text(name), 128), ('TITLE', FMT_STRING, text(TITLES[title_id]), 128)])


def is_roster_folder(path):
    if not SLOT_NAME.match(os.path.basename(path)):
        return False
    try:
        with open(os.path.join(path, 'SYS-DATA'), 'rb') as f:
            return f.read(len(ROSTER_MAGIC)) == ROSTER_MAGIC and os.path.exists(os.path.join(path, 'PARAM.SFO'))
    except OSError:
        return False


def find_savedata(path):
    """Resolve what the user pointed at to (savedata folder, preselected slot folder or None).

    Accepts a roster folder, the savedata folder, or anything above it (RPCS3 folder, dev_hdd0,
    home, a user folder)."""
    path = os.path.abspath(os.path.expanduser(path.strip().strip('"')))
    if os.path.isfile(path):
        path = os.path.dirname(path)
    if is_roster_folder(path):
        return os.path.dirname(path), os.path.basename(path)
    if ANY_SAVE.match(os.path.basename(path)) and os.path.isdir(os.path.dirname(path)):
        path = os.path.dirname(path)       # a save folder of another kind (profile, hockey card)
    if list_rosters(path):
        return path, None
    for pattern in ('savedata', os.path.join('*', 'savedata'), os.path.join('home', '*', 'savedata'),
                    os.path.join('dev_hdd0', 'home', '*', 'savedata')):
        for cand in sorted(glob.glob(os.path.join(glob.escape(path), pattern))):
            if list_rosters(cand):
                return cand, None
    raise FileNotFoundError(
        "No NHL Legacy roster save was found there. Pick your RPCS3 folder, or the folder "
        "dev_hdd0\\home\\00000001\\savedata inside it. A roster must have been saved in the game at least once.")


class Rpcs3Error(FileNotFoundError):
    """What the user pointed at is not a usable RPCS3 (the message says why, in plain words)."""


class Rpcs3:
    """An RPCS3 installation and the save folder NHL Legacy uses in it. `exe` is the program (None
    when the player pointed at the data folder), `root` the folder with RPCS3's data (default: the
    program's folder, as on Windows)."""
    plain = False                       # SaveFolder: roster saves without RPCS3

    def __init__(self, exe, savedata, user, root=None):
        self.exe = exe
        self.folder = root or os.path.dirname(exe)
        self.where = exe or self.folder     # what the window shows and remembers
        self.savedata = savedata
        self.user = user
        self.dev_hdd0 = _dev_hdd0(self.folder)

    def start(self):
        """Start RPCS3 (the program the player picked, else the one installed on this system)."""
        exe = self.exe or shutil.which('rpcs3')
        if exe and exe.lower().endswith('.app'):
            subprocess.Popen(['open', '-a', exe])
        elif exe:
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
        elif MAC:
            subprocess.Popen(['open', '-a', 'RPCS3'])

    def game_folder(self, title_id):
        """The game's own folder on RPCS3's hard disk (its update and any loose files):
        dev_hdd0/game/<TITLEID>/USRDIR. It may not exist yet."""
        return os.path.join(self.dev_hdd0, 'game', title_id, 'USRDIR')

    def games(self):
        """The versions of NHL Legacy this RPCS3 has (title ids, Europe first): listed in its games
        list, or with saves in the save folder."""
        saved = {name[:9] for name in (os.listdir(self.savedata) if os.path.isdir(self.savedata) else [])
                 if ANY_SAVE.match(name)}
        return [t for t in GAMES if t in saved or self.game_disc(t)]

    def disc_slots(self):
        """The game's own roster of each version RPCS3 has the disc of (DiscSlot), Europe first."""
        return [DiscSlot(t, self.game_disc(t)) for t in GAMES if self.game_disc(t)]

    def game_disc(self, title_id):
        """Where RPCS3 has the game itself: a disc image or a folder (config/games.yml), or None."""
        for cfg in (os.path.join(self.folder, 'config', 'games.yml'), os.path.join(self.folder, 'games.yml')):
            if not os.path.isfile(cfg):
                continue
            with open(cfg, encoding='utf-8-sig', errors='replace') as f:
                for line in f:
                    key, sep, value = line.rstrip('\r\n').partition(': ')
                    if sep and key.strip().strip('"') == title_id:
                        path = value.strip().strip('"').replace('$(EmulatorDir)', self.folder + os.sep)
                        path = os.path.normpath(path if os.path.isabs(path) else os.path.join(self.folder, path))
                        return path if os.path.exists(path) else None
        return None


class SaveFolder(Rpcs3):
    """Roster saves without RPCS3: a savedata folder (or one roster save) the player picks himself,
    for example when the program runs in CrossOver or Wine and RPCS3 is the Mac or Linux one, or the
    saves were copied from somewhere else (testers, 0.8.0). Updating works the same and the new
    roster goes next to the others; the game's own roster and the photos need RPCS3 (its games list
    and game folder), so they are not offered."""
    plain = True

    def __init__(self, savedata):
        self.exe, self.user, self.dev_hdd0 = None, None, None
        self.folder = self.where = self.savedata = savedata

    def game_folder(self, title_id):
        return None

    def game_disc(self, title_id):
        return None

    def start(self):
        pass


def open_saves(path):
    """(SaveFolder, roster folder pointed at or None) for a folder with roster saves, a roster save,
    or a file in one. FileNotFoundError (with what to do) when there are none."""
    folder, preselected = find_savedata(path)
    return SaveFolder(folder), preselected


def _dev_hdd0(root):
    """RPCS3's virtual hard disk: next to the program unless config/vfs.yml moves it."""
    for cfg in (os.path.join(root, 'config', 'vfs.yml'), os.path.join(root, 'vfs.yml')):
        if not os.path.isfile(cfg):
            continue
        entries = {}
        with open(cfg, encoding='utf-8-sig', errors='replace') as f:
            for line in f:
                key, sep, value = line.rstrip('\r\n').partition(': ')
                if sep and not key.startswith((' ', '\t')):
                    entries[key.strip().strip('"')] = value.strip().strip('"')
        hdd0 = entries.get('/dev_hdd0/')
        if hdd0:
            emulator_dir = entries.get('$(EmulatorDir)') or root + os.sep
            hdd0 = hdd0.replace('$(EmulatorDir)', emulator_dir)
            return os.path.normpath(hdd0 if os.path.isabs(hdd0) else os.path.join(root, hdd0))
    return os.path.join(root, 'dev_hdd0')


def _active_user(root):
    """The user RPCS3 is set to (None when it does not say; then 00000001 is its default)."""
    for name in ('persistent_settings.dat', 'CurrentSettings.ini'):
        path = os.path.join(root, 'GuiConfigs', name)
        if not os.path.isfile(path):
            continue
        section = ''
        with open(path, encoding='utf-8-sig', errors='replace') as f:
            for line in f:
                line = line.strip()
                if line.startswith('['):
                    section = line.strip('[]').lower()
                elif section == 'users' and line.lower().startswith('active_user='):
                    return line.split('=', 1)[1].strip().strip('"')
    return None


def find_rpcs3(path):
    """Resolve RPCS3 to its NHL Legacy saves. `path`: the program (rpcs3.exe, rpcs3, an AppImage,
    RPCS3.app), the folder holding it or a folder inside that one (such as a save folder remembered
    by version 0.1), or RPCS3's data folder (~/.config/rpcs3 on Linux).

    Raises Rpcs3Error with a message for the user when it is not RPCS3 or has no roster yet."""
    path = os.path.abspath(os.path.expanduser((path or '').strip().strip('"')))
    exe = root = None
    if is_program(path):
        exe = path
    elif os.path.isdir(path):
        folder = path
        while True:
            exe = next((os.path.join(folder, n) for n in ('rpcs3.exe', 'rpcs3') if is_program(os.path.join(folder, n))),
                       None)
            if exe or (not WINDOWS and has_data(folder)):     # Windows: the data is always next to rpcs3.exe
                root = None if exe else folder
                break
            if os.path.dirname(folder) == folder:
                break
            folder = os.path.dirname(folder)
    if exe is None and root is None:
        raise Rpcs3Error("That is not RPCS3. " + PICK_RPCS3)
    if root is None:            # the program: its data is next to it (Windows, a portable copy), else in the usual place
        places = [os.path.dirname(os.path.normpath(exe))] + data_folders()
        root = next((p for p in places if has_data(p)), places[0])
    home = os.path.join(_dev_hdd0(root), 'home')
    users = sorted(u for u in os.listdir(home) if re.fullmatch(r'\d{8}', u)) if os.path.isdir(home) else []
    newest = {}
    for user in users:
        rosters = list_rosters(os.path.join(home, user, 'savedata'))
        if rosters:
            newest[user] = rosters[0].modified
    active = _active_user(root)
    if not newest:
        # no roster yet: still usable when RPCS3 has the game, which carries its own roster
        user = active or (users[0] if users else '00000001')
        found = Rpcs3(exe, os.path.join(home, user, 'savedata'), user, root)
        if found.disc_slots():
            return found
        raise Rpcs3Error("RPCS3 was found, but it has no roster of NHL Legacy and does not list the game. Start the "
                         "game once from RPCS3's game list (or save a roster in the game), then try again.")
    user = active if active in newest else max(newest, key=newest.get)
    return Rpcs3(exe, os.path.join(home, user, 'savedata'), user, root)


def running_rpcs3():
    """Full path of a running RPCS3, or None (never raises)."""
    if not WINDOWS:
        return _running_posix()
    try:
        import ctypes
        from ctypes import wintypes
        k32, psapi = ctypes.WinDLL('kernel32'), ctypes.WinDLL('psapi')
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                   ctypes.POINTER(wintypes.DWORD)]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        pids = (wintypes.DWORD * 8192)()
        used = wintypes.DWORD()
        if not psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(used)):
            return None
        for pid in pids[:used.value // ctypes.sizeof(wintypes.DWORD)]:
            handle = k32.OpenProcess(0x1000, False, pid)       # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                continue
            try:
                name = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(len(name))
                if (k32.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size))
                        and os.path.basename(name.value).lower() == 'rpcs3.exe'):
                    return name.value
            finally:
                k32.CloseHandle(handle)
    except (OSError, AttributeError):
        pass
    return None


def _running_posix(proc='/proc'):
    """A running RPCS3 on Linux (`proc`: /proc) or a Mac (ps)."""
    is_rpcs3 = lambda cmd: (os.path.basename(cmd).lower() == 'rpcs3'
                            or ('rpcs3' in cmd.lower() and cmd.lower().endswith('.appimage')))
    try:
        if os.path.isdir(proc):
            for pid in sorted(os.listdir(proc)):
                if not pid.isdigit():
                    continue
                try:
                    with open(os.path.join(proc, pid, 'cmdline'), 'rb') as f:
                        cmd = f.read().split(b'\0')[0].decode('utf-8', 'replace')
                except OSError:
                    continue
                if cmd and is_rpcs3(cmd):
                    return cmd
            return None
        out = subprocess.run(['ps', '-axo', 'comm='], capture_output=True, text=True, timeout=5).stdout
        return next((line.strip() for line in out.splitlines() if is_rpcs3(line.strip())), None)
    except (OSError, subprocess.SubprocessError):
        return None


def open_path(path):
    """Open a folder or a file with the system's own program (Explorer, Finder, the file manager)."""
    if WINDOWS:
        os.startfile(path)
    else:
        subprocess.Popen(['open' if MAC else 'xdg-open', path])


class DeleteError(RuntimeError):
    """A roster save could not be removed (the message says why and what to do, in plain words)."""


class InPlaceError(RuntimeError):
    """A roster save could not be updated in place (the message says why and what to do, in plain words)."""


KEEP_BACKUPS = 10        # backups of one roster the program keeps (its own copies only)


def update_in_place(savedata, slot, sys_data, name=None, expected=None, backup_root=None):
    """Replace the roster of an existing roster save with `sys_data`: the same folder, icon and PARAM.SFO
    (only SUB_TITLE changes, and only when `name` is given and differs). Returns (the Slot, the folder of
    the backup copy or None, whether anything was written).

    The old save is copied to `backup_root` first (the program's own folder: the game lists every folder
    in the save folder that starts like a roster save, so a copy cannot stay there), the new SYS-DATA is
    written next to the save folder and moved over the old one. Refused while RPCS3 runs, for anything
    that is not a roster save directly in `savedata`, and when the roster is no longer what `expected`
    (the bytes read when the update started) says: someone else changed it. Bytes that are the same as
    the roster already has write nothing."""
    folder = getattr(slot, 'folder', '')
    path = os.path.join(savedata, folder)
    if getattr(slot, 'disc', False) or not SLOT_NAME.match(folder) or not is_roster_folder(path)             or os.path.islink(path) or os.path.realpath(os.path.dirname(path)) != os.path.realpath(savedata):
        raise InPlaceError("That is not a roster save, so it was not changed.")
    if running_rpcs3():
        raise InPlaceError("Close RPCS3 first: a roster can only be updated while the game is closed.")
    target = os.path.join(path, 'SYS-DATA')
    with open(target, 'rb') as f:
        current = f.read()
    if expected is not None and current != expected:
        raise InPlaceError("The roster was changed while the update was running, so it was not touched. Try again.")
    sfo = Sfo.load(os.path.join(path, 'PARAM.SFO'))
    new_name = clean_name(name) if name else None
    renamed = new_name is not None and new_name != (sfo.get('SUB_TITLE', '') or '')
    if current == sys_data and not renamed:
        return Slot(path), None, False
    backup = None
    if backup_root:
        backup = os.path.join(backup_root, f"{folder}_{datetime.datetime.now():%Y%m%d-%H%M%S}")
        n = 1
        while os.path.exists(backup):
            n += 1
            backup = f"{backup.rsplit('_', 1)[0]}_{datetime.datetime.now():%Y%m%d-%H%M%S}-{n}"
        try:
            os.makedirs(backup)
            for part in FILES:
                shutil.copy2(os.path.join(path, part), os.path.join(backup, part))
            with open(os.path.join(backup, 'SYS-DATA'), 'rb') as f:
                if f.read() != current:
                    raise OSError("the backup did not copy correctly")
        except OSError as err:
            shutil.rmtree(backup, ignore_errors=True)
            raise InPlaceError(f"The old roster could not be copied to the backup folder ({err.strerror or err}), "
                               "so it was not changed.") from err
    side = os.path.join(os.path.dirname(os.path.abspath(savedata)), f".roster-updater-{folder}.new")
    try:
        if current != sys_data:
            with open(side, 'wb') as f:
                f.write(sys_data)
                f.flush()
                os.fsync(f.fileno())
            with open(side, 'rb') as f:
                if f.read() != sys_data:
                    raise OSError("the new roster did not write correctly")
            os.replace(side, target)
        if renamed:
            sfo.set_str('SUB_TITLE', new_name)
            sfo.save(side)
            os.replace(side, os.path.join(path, 'PARAM.SFO'))
        os.utime(path)                  # the game lists the newest folder first
    except OSError as err:
        if os.path.exists(side):
            os.remove(side)
        raise InPlaceError(f"The roster could not be updated ({err.strerror or err}); the old one is still there.") from err
    if backup_root:
        _prune_backups(backup_root, folder)
    return Slot(path), backup, True


def _prune_backups(root, folder):
    """Keep the newest KEEP_BACKUPS backups of one roster (the program's own copies only)."""
    mine = sorted((d for d in os.listdir(root) if d.startswith(folder + '_') and os.path.isdir(os.path.join(root, d))),
                  reverse=True)
    for old in mine[KEEP_BACKUPS:]:
        shutil.rmtree(os.path.join(root, old), ignore_errors=True)


def _recycle(path):
    """Move a folder to the Recycle Bin / Trash. Raises DeleteError when the system has none we can
    use: nothing is ever erased for good."""
    if WINDOWS:
        import ctypes
        from ctypes import wintypes

        class FileOp(ctypes.Structure):          # SHFILEOPSTRUCTW
            _fields_ = [('hwnd', wintypes.HWND), ('func', wintypes.UINT), ('src', wintypes.LPCWSTR),
                        ('dst', wintypes.LPCWSTR), ('flags', ctypes.c_ushort), ('aborted', wintypes.BOOL),
                        ('mappings', ctypes.c_void_p), ('title', wintypes.LPCWSTR)]
        FO_DELETE, FOF_ALLOWUNDO, FOF_WANTNUKEWARNING = 3, 0x40, 0x4000
        source = ctypes.create_unicode_buffer(os.path.abspath(path) + '\0\0')    # the list ends with two zeros
        op = FileOp(None, FO_DELETE, ctypes.cast(source, wintypes.LPCWSTR), None,
                    FOF_ALLOWUNDO | FOF_WANTNUKEWARNING, False, None, None)
        if ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) or op.aborted:
            raise DeleteError("Windows could not move the roster to the Recycle Bin, so it was not removed.")
    elif MAC:
        trash = os.path.expanduser('~/.Trash')
        target, n = os.path.join(trash, os.path.basename(path)), 1
        while os.path.exists(target):
            n += 1
            target = os.path.join(trash, f"{os.path.basename(path)} {n}")
        try:
            shutil.move(path, target)
        except OSError as err:
            raise DeleteError(f"The roster could not be moved to the Trash ({err.strerror or err}).") from err
    else:
        gio = shutil.which('gio')
        if gio is None or subprocess.run([gio, 'trash', path], capture_output=True).returncode:
            raise DeleteError("This computer has no Trash the program can use (the command gio), so the roster was "
                              "not removed. Delete its folder in your file manager instead.")


def trash_save(savedata, folder):
    """Move a roster save (a folder like BLES021530203 in `savedata`) to the Recycle Bin. Only a real
    roster save directly inside the save folder, and never while RPCS3 runs. Nothing else is touched."""
    path = os.path.join(savedata, folder)
    if not SLOT_NAME.match(folder) or not is_roster_folder(path) or os.path.islink(path) \
            or os.path.realpath(os.path.dirname(path)) != os.path.realpath(savedata):
        raise DeleteError("That is not a roster save, so it was not removed.")
    if running_rpcs3():
        raise DeleteError("Close RPCS3 first: a roster can only be removed while the game is closed.")
    _recycle(path)
    if os.path.exists(path):
        raise DeleteError("The roster is still there, so it was not removed.")


def list_rosters(savedata):
    """Roster saves in a savedata folder, newest first."""
    if not os.path.isdir(savedata):
        return []
    slots = []
    for name in os.listdir(savedata):
        path = os.path.join(savedata, name)
        if is_roster_folder(path):
            slots.append(Slot(path))
    return sorted(slots, key=lambda s: s.modified, reverse=True)


def next_free(savedata, title_id):
    """Folder name for a new roster save: the number after the highest one in use."""
    used = set()
    for name in (os.listdir(savedata) if os.path.isdir(savedata) else []):
        m = SLOT_NAME.match(name)
        if m and m.group(1) == title_id:
            used.add(int(m.group(2)))
    n = max(used, default=-1) + 1
    if n > 99:
        free = [k for k in range(100) if k not in used]
        if not free:
            raise RuntimeError("all 100 roster save slots are in use; delete an old roster in the game first")
        n = free[0]
    return f"{title_id}02{n:02d}"


def default_name(now=None):
    """The in-game name of a new roster: the date and time it was built."""
    return f"{now or datetime.datetime.now():%Y-%m-%d %H:%M}"


def clean_name(name):
    """Keep a roster name to characters every game font has, and to a sane length."""
    name = re.sub(r'[^A-Za-z0-9 .:_\-+()]', '', name).strip()
    return name[:40] or default_name()


def _model_for(savedata, source, title_id):
    """(icon: path or bytes, Sfo) a new save of version `title_id` is made from: the source's for
    its own version; for the other one, that version's newest roster save, else the source's with
    the TITLE that version's saves carry (any save of it in the folder, else TITLES). The game's
    own roster (a DiscSlot) has no save files: any roster save of the folder serves, else the
    PARAM.SFO is made from scratch and the icon comes from the player's disc."""
    if title_id == source.title_id and not getattr(source, 'disc', False):
        return os.path.join(source.path, 'ICON0.PNG'), Sfo.load(os.path.join(source.path, 'PARAM.SFO'))
    rosters = list_rosters(savedata)
    own = [s for s in rosters if s.title_id == title_id]
    if own:
        return os.path.join(own[0].path, 'ICON0.PNG'), Sfo.load(os.path.join(own[0].path, 'PARAM.SFO'))
    if getattr(source, 'disc', False):
        if not rosters:
            from . import stock
            return stock.disc_icon(source.path), roster_sfo(title_id, f"{title_id}0200", "roster")
        source = rosters[0]
    sfo = Sfo.load(os.path.join(source.path, 'PARAM.SFO'))
    title = TITLES.get(title_id)
    for name in sorted(os.listdir(savedata)):
        if name.startswith(title_id) and ANY_SAVE.match(name):
            try:
                title = Sfo.load(os.path.join(savedata, name, 'PARAM.SFO')).get('TITLE') or title
                break
            except (OSError, ValueError):
                continue
    if title and 'TITLE' in sfo.entries:
        sfo.set_str('TITLE', title)
    return os.path.join(source.path, 'ICON0.PNG'), sfo


def install(savedata, source, sys_data, name, title_id=None):
    """Write `sys_data` as a new roster save next to `source` (a Slot, or a DiscSlot: the game's own
    roster). Returns the new Slot.

    The icon and PARAM.SFO are taken from the source save; only the folder name and the roster
    name change. With `title_id` of the other version of the game (EU / NA), the save goes into
    that version's folders instead (see _model_for). The folder appears complete or not at all."""
    name = clean_name(name)
    title_id = title_id or source.title_id
    os.makedirs(savedata, exist_ok=True)       # a user who never saved anything has no save folder yet
    icon, sfo = _model_for(savedata, source, title_id)
    folder = next_free(savedata, title_id)
    target = os.path.join(savedata, folder)
    # built next to the savedata folder, then moved in: the game never sees a half-written save
    tmp = os.path.join(os.path.dirname(os.path.abspath(savedata)), f".roster-updater-{folder}")
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    try:
        os.makedirs(tmp)
    except OSError:
        tmp = target + '.tmp'
        os.makedirs(tmp)
    try:
        if isinstance(icon, bytes):
            with open(os.path.join(tmp, 'ICON0.PNG'), 'wb') as f:
                f.write(icon)
        else:
            shutil.copy2(icon, os.path.join(tmp, 'ICON0.PNG'))
        sfo.set_str('SAVEDATA_DIRECTORY', folder)
        sfo.set_str('SUB_TITLE', name)
        sfo.save(os.path.join(tmp, 'PARAM.SFO'))
        with open(os.path.join(tmp, 'SYS-DATA'), 'wb') as f:
            f.write(sys_data)
        with open(os.path.join(tmp, 'SYS-DATA'), 'rb') as f:
            if hashlib.sha1(f.read()).digest() != hashlib.sha1(sys_data).digest():
                raise OSError("the new save did not write correctly")
        os.rename(tmp, target)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return Slot(target)
