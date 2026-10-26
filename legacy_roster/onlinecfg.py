"""Online play from the app (Multiplayer.txt, docs/notes/multiplayer.md): the pieces that need neither the server nor a
running RPCS3, standard library only. The player's own RPCS3 files are only read:

    account(rpcs3)                  the RPCN name in config/rpcn.yml (never the password or the token)
    net_config(text, address)       a config.yml with the Net block set for our server, every other line as it was
    write_config(rpcs3, title, ip)  that config as the app's own file (online/config_<TITLE>.yml in the program's folder)
    launch_args(rpcs3, title, cfg)  rpcs3.exe --no-gui --config <cfg> <game>
    log_state(text)                 what RPCS3's log says about the online sign-in
    read_shared(path)               RPCS3's log, which RPCS3 keeps open
    rpcs3_build(rpcs3)              the build number of the RPCS3 that wrote the log (None: not known yet)
    roster_crc(data)                the CRC in a roster save's header (the official online roster is told by it)
"""
import os
import re
import struct

from . import datasource, tdb

HOST = 'gosredirector.ea.com'        # the address the game asks for; RPCS3's IP swap list sends it to our server
NET = {                              # the Net block's keys the app sets; every other key stays as the player has it
    'Internet enabled': 'Connected',
    'PSN status': 'RPCN',
    'UPNP Enabled': 'true',
}
SWAP = 'IP swap list'
MIN_RPCS3 = 20393                    # the oldest RPCS3 build the online lab played with (lab 1); older ones are told to update


def account(rpcs3):
    """The RPCN name (NPID) in RPCS3's config/rpcn.yml, or None (no file, no account yet). Only that line is read."""
    path = os.path.join(rpcs3.folder, 'config', 'rpcn.yml')
    try:
        with open(path, encoding='utf-8-sig', errors='replace') as f:
            for line in f:
                key, sep, value = line.rstrip('\r\n').partition(':')
                if sep and key.strip() == 'NPID':
                    return value.strip().strip('"\'') or None
    except OSError:
        pass
    return None


def base_config(rpcs3, title):
    """The text of the config RPCS3 would boot `title` with: its custom config when there is one, else config.yml ('' when
    there is neither)."""
    for path in (os.path.join(rpcs3.folder, 'config', 'custom_configs', f'config_{title}.yml'),
                 os.path.join(rpcs3.folder, 'custom_configs', f'config_{title}.yml'),
                 os.path.join(rpcs3.folder, 'config', 'config.yml'), os.path.join(rpcs3.folder, 'config.yml')):
        try:
            with open(path, encoding='utf-8-sig', errors='replace', newline='') as f:
                return f.read()
        except OSError:
            continue
    return ''


def _swaps(value, address):
    """The IP swap list `value` with HOST sent to `address`, other pairs kept (RPCS3 joins pairs with &&)."""
    pairs = [p.strip() for p in value.strip().strip('"\'').split('&&') if p.strip()]
    pairs = [p for p in pairs if p.partition('=')[0].strip().lower() != HOST]
    return ' && '.join(pairs + [f'{HOST}={address}'])


def net_config(text, address):
    """`text` (a config.yml) with its Net block set to play online on our server at `address`: Internet enabled, RPCN,
    UPnP on, HOST swapped for `address` (the player's other swaps stay). Every other line is as it was, line endings
    included; a missing Net block or key is added."""
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.rstrip() == 'Net:'), None)
    if start is None:
        lines += ['Net:'] + [f'  {k}: {v}' for k, v in NET.items()] + [f'  {SWAP}: {_swaps("", address)}']
        return newline.join(lines) + newline
    end = start + 1
    while end < len(lines) and (lines[end].startswith((' ', '\t')) or not lines[end].strip()):
        end += 1
    seen = set()
    for i in range(start + 1, end):
        key, sep, value = lines[i].strip().partition(':')
        if not sep:
            continue
        if key in NET:
            lines[i] = f'  {key}: {NET[key]}'
            seen.add(key)
        elif key == SWAP:
            lines[i] = f'  {SWAP}: {_swaps(value, address)}'
            seen.add(key)
    add = [f'  {k}: {v}' for k, v in NET.items() if k not in seen]
    if SWAP not in seen:
        add.append(f'  {SWAP}: {_swaps("", address)}')
    while end > start + 1 and not lines[end - 1].strip():       # new keys go after the block's last key
        end -= 1
    lines[end:end] = add
    return newline.join(lines) + (newline if text.endswith('\n') or not text else '')


def write_config(rpcs3, title, address):
    """Write the app's own config for booting `title` online (the player's config for the game with the Net block set) to
    online/config_<TITLE>.yml in the program's folder. Returns its path. The player's own files are not touched."""
    path = os.path.join(datasource.app_dir('online'), f'config_{title}.yml')
    text = net_config(base_config(rpcs3, title), address)
    with open(path + '.tmp', 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    os.replace(path + '.tmp', path)
    return path


def launch_args(rpcs3, title, config, fullscreen=False):
    """The command line that boots `title` from RPCS3 with the app's config `config`, or None when RPCS3 or the game is not
    found. The game is the disc RPCS3 lists (RPCS3 itself runs update 1.01 when it is installed)."""
    disc = rpcs3.game_disc(title)
    if not rpcs3.exe or not disc:
        return None
    return [rpcs3.exe, '--no-gui'] + (['--fullscreen'] if fullscreen else []) + ['--config', config, disc]


def read_shared(path, limit=None):
    """The text of `path` (RPCS3.log) read with full sharing: RPCS3 keeps it open and a plain open fails on Windows.
    `limit`: stop after about that many bytes (the start of the log is enough for the version line)."""
    if os.name != 'nt':
        with open(path, 'rb') as f:
            return f.read(limit).decode('utf-8', 'replace')
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                wintypes.DWORD, wintypes.HANDLE]
    k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                             wintypes.LPVOID]
    handle = k32.CreateFileW(path, 0x80000000, 7, None, 3, 0x80, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        raise OSError(ctypes.get_last_error(), 'cannot open ' + path)
    try:
        out, buf, got = [], ctypes.create_string_buffer(1 << 20), wintypes.DWORD()
        while k32.ReadFile(handle, buf, len(buf), ctypes.byref(got), None) and got.value:
            out.append(buf.raw[:got.value])
            if limit is not None and sum(map(len, out)) >= limit:
                break
    finally:
        k32.CloseHandle(handle)
    return b''.join(out).decode('utf-8', 'replace')


_BUILD = re.compile(r'RPCS3 v\d+\.\d+\.\d+-(\d+)-')


def rpcs3_build(rpcs3):
    """The build number of the RPCS3 that wrote `log/RPCS3.log` ('RPCS3 v0.0.43-20402-d00d8023 Alpha' -> 20402), or None: no
    log yet, or rpcs3.exe is newer than the log (RPCS3 was updated and has not been started since)."""
    path = os.path.join(rpcs3.folder, 'log', 'RPCS3.log')
    try:
        if rpcs3.exe and os.path.getmtime(rpcs3.exe) > os.path.getmtime(path):
            return None
        found = _BUILD.search(read_shared(path, 4096))
    except OSError:
        return None
    return int(found.group(1)) if found else None


_LOGGED_IN = re.compile(r'rpcn: You are now logged in RPCN\((?P<name>[^|)]+?)\s*\|')
_SIGNALING = 'Failed to get a reply from RPCN signaling'
_PROTOCOL = re.compile(r'rpcn: Server returned protocol version: (\d+), expected: (\d+)')
_REFUSED = re.compile(r'rpcn: (?:Failed to connect|Login error|Authentication failed|Invalid credentials|'
                      r'Failed to (?:login|authenticate))|rpcn: .*(?:Wrong|Invalid) (?:password|token)', re.I)


def log_state(text):
    """What RPCS3's log (from this boot: after the newest 'RPCS3 v' start line) says about the online sign-in:
    {'name': the RPCN name signed in, None if not (any more), 'bound': the game's UDP port 3658 was taken,
     'signaling': False when RPCN's UDP check got no reply (the game then says it is not signed in to the online servers),
     'refused': the line that says the sign-in failed, else None, 'fatal': RPCS3 stopped with a fatal error,
     'old': this RPCS3 is older than the RPCN server (its protocol number is lower than the server's)}."""
    marks = [m.start() for m in re.finditer(r'RPCS3 v\d', text)]
    text = text[marks[-1]:] if marks else text
    state = {'name': None, 'bound': False, 'signaling': True, 'refused': None, 'fatal': False, 'old': False}
    for line in text.splitlines():
        found = _LOGGED_IN.search(line)
        if found:
            state['name'], state['refused'] = found.group('name').strip(), None
        elif _PROTOCOL.search(line):
            have = _PROTOCOL.search(line)
            state['old'] = int(have.group(2)) < int(have.group(1))
        elif 'rpcn: Disconnected' in line:
            state['name'] = None
        elif 'P2P port' in line and 'was bound' in line:
            state['bound'] = True
        elif _SIGNALING in line:
            state['signaling'] = False
        elif _REFUSED.search(line):
            state['refused'] = line.split('rpcn:', 1)[-1].strip()
        elif 'Fatal Error' in line or 'RPCS3: Fatal' in line:
            state['fatal'] = True
    return state


def roster_check(data):
    """The friend's roster save `data` is read as a roster before it is put in the game folder (the CRC fits, the tables parse,
    the team table is no bigger than the game's). Returns its CRC; raises ValueError for anything else."""
    crc = roster_crc(data)
    from . import roster as roster_module
    try:
        parsed = roster_module.Roster(data)
        if parsed.T.cur_rec > 252:
            raise ValueError("too many teams")
    except (ValueError, KeyError, IndexError, struct.error, AttributeError, OverflowError) as err:
        raise ValueError(f"not a roster save ({err})") from err
    return crc


def roster_crc(data):
    """The CRC in the header of the roster save `data` (SYS-DATA bytes) as eight hex digits; the official online roster is
    told by it. Raises ValueError for something that is not a roster save."""
    if len(data) < 0x30:
        raise ValueError("file too short to be a save")
    size, stored = struct.unpack_from('>II', data, 0x24)
    if tdb.crc32_bzip2(data[0x2C:0x2C + size]) != stored:
        raise ValueError("section CRC mismatch -- not a supported save")
    return f'{stored:08x}'
