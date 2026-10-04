"""Find roster saves in an RPCS3 (or copied PS3) savedata folder and write new ones.

A roster save is a folder <TITLEID>02NN (BLES02153 = Europe, BLUS31540 = North America) with
ICON0.PNG, PARAM.SFO and SYS-DATA. The updater never changes an existing folder: every update
goes into a new one with the next free number.

The window asks for RPCS3 itself (find_rpcs3); the command line also takes a save folder
directly (find_savedata).
"""
import datetime
import glob
import hashlib
import os
import re
import shutil

from .sfo import Sfo
from .tdb import ROSTER_MAGIC

SLOT_NAME = re.compile(r'^([A-Z]{4}\d{5})02(\d{2})$')
ANY_SAVE = re.compile(r'^[A-Z]{4}\d{9}$')     # profile, hockey card and other saves of the game
TOOL_NAME = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}|^R\d{6}-\d{4}$')   # names this tool gives its saves
FILES = ('ICON0.PNG', 'PARAM.SFO', 'SYS-DATA')


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

    def label(self):
        return f"{self.name}   ({self.folder}, saved {self.modified:%Y-%m-%d %H:%M})"


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
    """An RPCS3 installation and the save folder NHL Legacy uses in it."""

    def __init__(self, exe, savedata, user):
        self.exe = exe
        self.folder = os.path.dirname(exe)
        self.savedata = savedata
        self.user = user
        self.dev_hdd0 = _dev_hdd0(self.folder)

    def game_folder(self, title_id):
        """The game's own folder on RPCS3's hard disk (its update and any loose files):
        dev_hdd0/game/<TITLEID>/USRDIR. It may not exist yet."""
        return os.path.join(self.dev_hdd0, 'game', title_id, 'USRDIR')

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
    """Resolve the RPCS3 program (rpcs3.exe, the folder holding it, or a folder inside that one,
    such as a save folder remembered by version 0.1) to its NHL Legacy saves.

    Raises Rpcs3Error with a message for the user when it is not RPCS3 or has no roster yet."""
    path = os.path.abspath(os.path.expanduser((path or '').strip().strip('"')))
    exe = path
    if os.path.isdir(path):
        folder, exe = path, None
        while exe is None:
            exe = next((os.path.join(folder, n) for n in ('rpcs3.exe', 'rpcs3')
                        if os.path.isfile(os.path.join(folder, n))), None)
            if os.path.dirname(folder) == folder:
                break
            folder = os.path.dirname(folder)
        exe = exe or os.path.join(path, 'rpcs3.exe')
    if os.path.basename(exe).lower() not in ('rpcs3.exe', 'rpcs3') or not os.path.isfile(exe):
        raise Rpcs3Error("That is not RPCS3. Pick the file rpcs3.exe in your RPCS3 folder.")
    root = os.path.dirname(exe)
    home = os.path.join(_dev_hdd0(root), 'home')
    users = sorted(u for u in os.listdir(home) if re.fullmatch(r'\d{8}', u)) if os.path.isdir(home) else []
    newest = {}
    for user in users:
        rosters = list_rosters(os.path.join(home, user, 'savedata'))
        if rosters:
            newest[user] = rosters[0].modified
    if not newest:
        raise Rpcs3Error("RPCS3 was found, but NHL Legacy has no roster saved in it yet. Save a roster once in "
                         "the game (Roster Management > Save Roster), then try again.")
    active = _active_user(root)
    user = active if active in newest else max(newest, key=newest.get)
    return Rpcs3(exe, os.path.join(home, user, 'savedata'), user)


def running_rpcs3():
    """Full path of a running rpcs3.exe, or None (Windows only; never raises)."""
    if os.name != 'nt':
        return None
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
    for name in os.listdir(savedata):
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


def install(savedata, source, sys_data, name):
    """Write `sys_data` as a new roster save next to `source` (a Slot). Returns the new Slot.

    The icon and PARAM.SFO are taken from the source save; only the folder name and the roster
    name change. The folder appears complete or not at all."""
    name = clean_name(name)
    folder = next_free(savedata, source.title_id)
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
        shutil.copy2(os.path.join(source.path, 'ICON0.PNG'), os.path.join(tmp, 'ICON0.PNG'))
        sfo = Sfo.load(os.path.join(source.path, 'PARAM.SFO'))
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
