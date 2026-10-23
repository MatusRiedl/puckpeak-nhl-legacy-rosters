"""The main-menu entries that died with the game's servers: View Player Hub, Leaderboards and Lobby, and
Hockey Ultimate Team (main menu and PLAY; the owner, 2026-10-18 late: it cannot be played offline). A
changed copy of the game's menu file hides them.

The menus are data, not game code. fe/ion/game/menus/mainmenuitems.big (inside boot.big on the disc)
is a small BIGF archive around an Apt UI movie ('0' the movie, RefPack-compressed; '1' its
constant file). The movie's start-up script fills the menu lists, one statement per entry:

    objMainMenu.arrPlay.push({name: 'TXT_HUT', screenID: null, reward_desc: ...})

`name` is the entry's text key (fe/loc/nhl_<language>.db). The entries this module hides
(`DEAD`): OSDK_AP_VIEW_HUB, Leaderboards and OSDK_LOBBY in COMMUNITY (arrOnlineCommunity, which the
script also names arrCommunity) and TXT_HUT (arrRootMenu: the main menu's "Featured" row, and PLAY).
GM Connected, the EASHL and online versus (PLAY > Online) stay: the community server Zamboni serves them. The lab showed the game
reads a loose copy in USRDIR before boot.big (2026-10-18, docs/notes/menus.md).

Two ways, chosen by `mode`:

    HIDE    the entry's pair `screenID: <value>` becomes `isHidden: true`. The game's menu manager
            (classloader.big, MenuDataManager) leaves an entry with isHidden out when it counts a
            menu's entries and when the cursor moves (GetNextAvailableItem); the game marks its
            own entries the same way (TXT_FIRST_PARTY_CODE_REDEMPTION, TXT_BE_A_LEGEND). The
            entry stays in its list, so the script's look-ups by name still find it.
    REMOVE  the whole statement becomes code that does nothing (PushZero, Pop pairs), so the entry
            is never added. Every look-up of these names in the script accepts a missing entry
            (ArrayUtil.Search answers 255).

Either way no byte moves: the movie keeps its size, and every pointer and every 4-byte aligned
instruction stays where it was. The changed movie is RefPack-compressed again (refpack.compress,
deterministic) and the archive is laid out like the game's own (parts on 64-byte boundaries, the
16-byte trailer kept). Nothing here knows offsets: the statements are found by their shape in the
player's own file, and a file that does not look as expected is refused (ValueError).

The copy goes into the game's folder on RPCS3's hard disk (`REL`, relative to
dev_hdd0/game/<TITLEID>/USRDIR, like fe/loc/nhl_<language>.db). Whether the game reads a loose file
of boot.big from there is still to be seen in the game (docs/notes/menus.md).
"""
import os
import struct

from . import refpack
from .disc import EbArchive, IsoImage

ARCHIVE = 'boot.big'
MENU_FILE = 'fe/ion/game/menus/mainmenuitems.big'
REL = tuple(MENU_FILE.split('/'))
MENUS_VERSION = '#3'            # change when the copy is made another way ('#3': HUT hidden too)

HIDE, REMOVE = 'hide', 'remove'

DEAD = (                        # (menu list, text key): what the player saw
    ('arrOnlineCommunity', 'OSDK_AP_VIEW_HUB'),  # COMMUNITY: View Player Hub
    ('arrOnlineCommunity', 'Leaderboards'),     # COMMUNITY: Leaderboards
    ('arrOnlineCommunity', 'OSDK_LOBBY'),       # COMMUNITY: Lobby
    ('arrRootMenu', 'TXT_HUT'),                 # main menu: Hockey Ultimate Team (owner, 2026-10-18 late: hide it)
    ('arrPlay', 'TXT_HUT'),                     # PLAY: Hockey Ultimate Team
)

# --- Apt bytecode (big-endian; the opcode table of OpenSAGE's InstructionCollection) -----------
# Opcodes whose arguments start on the next 4-byte boundary of the movie data (zero padding).
# With (0x94) and Try (0x8F) are not read: a script that has them is refused.
_ALIGNED = frozenset((0x81, 0x83, 0x87, 0x88, 0x8B, 0x8C, 0x8E, 0x96, 0x99, 0x9B, 0x9D,
                      0x9F, 0xA1, 0xA4, 0xA5, 0xA6, 0xA7, 0xB8))
_ARGS = {0xA2: 1, 0xAE: 1, 0xAF: 1, 0xB0: 1, 0xB1: 1, 0xB2: 1, 0xB3: 1, 0xB5: 1, 0xB9: 1,
         0xA3: 2, 0xB6: 2, 0xB4: 4, 0xB7: 4,
         0x81: 4, 0x87: 4, 0x8B: 4, 0x8C: 4, 0x99: 4, 0x9D: 4, 0x9F: 4, 0xA1: 4, 0xA4: 4, 0xA5: 4,
         0xA6: 4, 0xA7: 4, 0xB8: 4, 0x83: 8, 0x88: 8, 0x96: 8, 0x9B: 24, 0x8E: 28}
_PLAIN = frozenset([0x00, 0x04, 0x05, 0x06, 0x07, 0x17, 0x18, 0x1C, 0x1D, 0x9A, 0x9E]
                   + list(range(0x0A, 0x16)) + list(range(0x20, 0x2D)) + list(range(0x30, 0x38))
                   + list(range(0x3A, 0x57)) + list(range(0x58, 0x5F)) + list(range(0x60, 0x6A))
                   + list(range(0x70, 0x78)))
_NAMED = frozenset((0xA2, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3))   # one byte: a constant's number
_CONST = (0xA2, 0xA3)           # PushConst (byte), PushConstW (word)
_BRANCH = (0x99, 0x9D, 0xB8)
END, POP, NOT, SET_VARIABLE, DEFINE_LOCAL = 0x00, 0x17, 0x12, 0x1D, 0x3C
INIT_OBJECT, GET_MEMBER, SET_MEMBER = 0x43, 0x4E, 0x4F
PUSH_ZERO, PUSH_ONE, CALL_METHOD_POP = 0x59, 0x5A, 0x5D
PUSH_TRUE, PUSH_FALSE, PUSH_NULL, PUSH_UNDEFINED = 0x73, 0x74, 0x75, 0x76
PUSH_VALUE_OF_VAR, PUSH_BYTE = 0xAE, 0xB5
# What ends a statement (or starts a block) right before a menu entry's statement.
_BOUNDARY = frozenset((END, POP, SET_VARIABLE, DEFINE_LOCAL, SET_MEMBER, CALL_METHOD_POP, 0x5B,
                       0xB0, 0xB2, 0x8E, 0x9B) + _BRANCH)
_SIMPLE_VALUE = frozenset(_CONST + (PUSH_NULL, PUSH_TRUE, PUSH_FALSE, PUSH_UNDEFINED, PUSH_ZERO,
                                    PUSH_ONE, PUSH_BYTE))


class Ins:
    """One instruction: where it starts, its opcode, its size in bytes, the constant it names (a
    string, or None) and the constant pool it was read under."""
    __slots__ = ('pos', 'op', 'size', 'text', 'pool')

    def __init__(self, pos, op, size, text, pool):
        self.pos, self.op, self.size, self.text, self.pool = pos, op, size, text, pool

    @property
    def end(self):
        return self.pos + self.size


class Entry:
    """A menu entry the start-up script adds: its list, its text key and its statement's
    instructions (from `{name: ...` to the CallMethodPop of `push`)."""

    def __init__(self, stream, array, key, code):
        self.stream, self.array, self.key, self.code = stream, array, key, code

    @property
    def start(self):
        return self.code[0].pos

    @property
    def end(self):
        return self.code[-1].end

    @property
    def hidden(self):
        """Does the entry's object carry `isHidden: true`?"""
        return any(a.op in _CONST and a.text == 'isHidden' and b.op == PUSH_TRUE
                   for a, b in zip(self.code, self.code[1:]))

    def __repr__(self):
        return f"Entry({self.array}, {self.key!r}, {self.start:#x}-{self.end:#x})"


class Bigf:
    """A BIGF archive as the game's UI files have it.

        0x00 'BIGF'   0x04 u32 little-endian: end of the parts (rounded up to 4)
        0x08 u32 big-endian: number of parts   0x0C u32 big-endian: size of the header and table
        0x10 per part: u32 offset, u32 size (big-endian), NUL-terminated name
        the parts, each on a 64-byte boundary (an empty part shares the next one's place), then a
        16-byte trailer
    """

    def __init__(self, data):
        if data[:4] != b'BIGF':
            raise ValueError("not a BIGF archive")
        self.raw = bytes(data)
        self.end = struct.unpack_from('<I', data, 4)[0]
        count = struct.unpack_from('>I', data, 8)[0]
        self.parts = []                     # [(name, offset, size)] in table order
        self.table = []                     # where each part's offset / size is written
        pos = 16
        for _ in range(count):
            off, size = struct.unpack_from('>II', data, pos)
            stop = data.index(b'\0', pos + 8)
            self.table.append(pos)
            self.parts.append((data[pos + 8:stop].decode('latin1'), off, size))
            pos = stop + 1
        if not self.parts or self.end > len(self.raw) or any(o + s > self.end for _n, o, s in self.parts):
            raise ValueError("BIGF table does not fit the file")

    def part(self, name):
        return next(self.raw[o:o + s] for n, o, s in self.parts if n == name)

    def rebuilt(self, contents):
        """This archive with some parts' contents replaced ({name: bytes}). The parts keep their
        order; each starts on the next 64-byte boundary after the one before, the header and the
        trailer stay as they are."""
        order = sorted(range(len(self.parts)), key=lambda i: (self.parts[i][1], i))
        first = self.parts[order[0]][1]
        out = bytearray(self.raw[:first])
        places = {}
        for i in order:
            name, off, size = self.parts[i]
            data = contents.get(name, self.raw[off:off + size])
            at = first if i == order[0] else _align(len(out), 64)
            out += b'\0' * (at - len(out))
            places[i] = (at, len(data))
            out += data
        end = _align(len(out), 4)
        out += b'\0' * (end - len(out)) + self.raw[self.end:]
        struct.pack_into('<I', out, 4, end)
        for i, (at, size) in places.items():
            struct.pack_into('>II', out, self.table[i], at, size)
        return bytes(out)


class Movie:
    """The Apt movie of a UI file: the movie data (unpacked) and its constants."""

    def __init__(self, data_part, const_part):
        self.packed = data_part[:2] == refpack.MAGIC
        self.data = refpack.decompress(data_part) if self.packed else bytes(data_part)
        const = refpack.decompress(const_part) if const_part[:2] == refpack.MAGIC else bytes(const_part)
        if not const.startswith(b'Apt constant file'):
            raise ValueError("not an Apt constant file")
        self.movie, count, items = struct.unpack_from('>III', const, 0x14)
        self.consts = []                    # a string, or None for a number
        for i in range(count):
            kind, value = struct.unpack_from('>II', const, items + 8 * i)
            self.consts.append(const[value:const.index(b'\0', value)].decode('latin1') if kind == 1 else None)

    def streams(self):
        """Where each action script of the movie and its sprites starts (sorted, once each)."""
        data, found = self.data, set()
        count, chars = struct.unpack_from('>II', data, self.movie + 0x1C)
        for c in range(count):
            at = struct.unpack_from('>I', data, chars + 4 * c)[0]
            if not at or struct.unpack_from('>I', data, at)[0] not in (5, 9):     # sprite, movie
                continue
            frames, table = struct.unpack_from('>II', data, at + 0x10)
            for f in range(frames):
                n, items = struct.unpack_from('>II', data, table + 8 * f)
                for k in range(n):
                    item = struct.unpack_from('>I', data, items + 4 * k)[0]
                    kind = struct.unpack_from('>I', data, item)[0]
                    if kind == 1:                       # Action
                        found.add(struct.unpack_from('>I', data, item + 4)[0])
                    elif kind == 8:                     # InitAction (sprite, code)
                        found.add(struct.unpack_from('>I', data, item + 8)[0])
        return sorted(found)

    def code(self, start, data=None):
        """The instructions of the script at `start`, up to its last End."""
        data = self.data if data is None else data
        consts = self.consts
        pool = list(range(len(consts)))
        out, pos, furthest = [], start, start
        while True:
            at, op = pos, data[pos]
            pos += 1
            if op in _ALIGNED:
                pos = (pos + 3) & ~3
            n = _ARGS.get(op)
            if n is None:
                if op not in _PLAIN:
                    raise ValueError(f"unknown Apt instruction {op:#04x} at {at:#x}")
                n = 0
            text = None
            if op in _NAMED or op == 0xA3:
                k = data[pos] if op != 0xA3 else struct.unpack_from('>H', data, pos)[0]
                text = consts[pool[k]] if k < len(pool) and pool[k] < len(consts) else None
            elif op in _BRANCH:
                furthest = max(furthest, pos + n + struct.unpack_from('>i', data, pos)[0])
            elif op == 0x88:                            # ConstantPool: count, -> constant numbers
                count, table = struct.unpack_from('>II', data, pos)
                pool = list(struct.unpack_from(f'>{count}I', data, table))
            pos += n
            if pos > len(data):
                raise ValueError(f"Apt script runs past the movie's end at {at:#x}")
            out.append(Ins(at, op, pos - at, text, pool))
            if op == END and pos > furthest:
                return out

    def entries(self, data=None):
        """Every menu entry the scripts add with objMainMenu.<list>.push({name: <key>, ...})."""
        found = []
        for start in self.streams():
            code = self.code(start, data)
            for j, ins in enumerate(code):
                if ins.op != CALL_METHOD_POP or j < 9:
                    continue
                tail = code[j - 7:j]
                if not (tail[0].op == PUSH_BYTE and tail[1].op == INIT_OBJECT and tail[2].op == PUSH_ONE
                        and tail[3].op == PUSH_VALUE_OF_VAR and tail[3].text == 'objMainMenu'
                        and tail[4].op in _CONST and tail[4].text and tail[5].op == GET_MEMBER
                        and tail[6].op in _CONST and tail[6].text == 'push'):
                    continue
                first = j - 8
                while first >= 0 and code[first].op not in _BOUNDARY:
                    first -= 1
                first += 1
                head = code[first:first + 2]
                if (first + 2 > j - 7 or head[0].op not in _CONST or head[0].text != 'name'
                        or head[1].op not in _CONST):
                    continue
                found.append(Entry(start, tail[4].text, head[1].text, code[first:j + 1]))
        return found


def _align(n, a):
    return (n + a - 1) // a * a


def _filler(n):
    """n bytes (2 or more) of code that does nothing: PushZero, Pop pairs (PushZero, Not, Pop for
    an odd count). Nothing in it points anywhere or needs alignment."""
    if n < 2:
        raise ValueError("no filler of one byte")
    if n % 2:
        return bytes((PUSH_ZERO, POP)) * ((n - 3) // 2) + bytes((PUSH_ZERO, NOT, POP))
    return bytes((PUSH_ZERO, POP)) * (n // 2)


def _hidden_pair(n, index):
    """n bytes that push the pair isHidden, true (`index`: the number of 'isHidden' in the pool)."""
    pushes = ([bytes((0xA2, index))] if index < 256 else []) + [b'\xa3' + struct.pack('>H', index)]
    for push in pushes:
        rest = n - 1 - len(push)
        if rest == 0 or rest >= 2:
            return (_filler(rest) if rest else b'') + push + bytes((PUSH_TRUE,))
    raise ValueError(f"no room for isHidden in {n} bytes")


def _pool_index(ins, consts, name):
    for k, c in enumerate(ins.pool):
        if c < len(consts) and consts[c] == name:
            return k
    raise ValueError(f"the script has no constant {name!r}")


def changes(movie, mode=HIDE):
    """The byte changes in the movie data that hide (or remove) the dead entries:
    [(offset, old bytes, new bytes)], same length each."""
    if mode not in (HIDE, REMOVE):
        raise ValueError(f"unknown mode {mode!r}")
    entries = movie.entries()
    out = []
    for array, key in DEAD:
        mine = [e for e in entries if e.array == array and e.key == key]
        if len(mine) != 1:
            raise ValueError(f"menu entry {key} of {array}: found {len(mine)} times, expected once")
        e = mine[0]
        if mode == REMOVE:
            out.append((e.start, movie.data[e.start:e.end], _filler(e.end - e.start)))
            continue
        if e.hidden:
            continue
        pair = e.code[2:5]
        if not (len(pair) == 3 and pair[0].op in _CONST and pair[0].text == 'screenID'
                and pair[1].op in _SIMPLE_VALUE
                and (pair[2].op in _CONST or pair[2] is e.code[-8])):
            raise ValueError(f"menu entry {key} of {array} does not start with name, screenID")
        at, stop = pair[0].pos, pair[1].end
        index = _pool_index(pair[0], movie.consts, 'isHidden')
        out.append((at, movie.data[at:stop], _hidden_pair(stop - at, index)))
    return sorted(out)


def hidden_file(original, mode=HIDE):
    """A copy of the game's mainmenuitems.big (bytes) with the dead entries hidden (HIDE) or left
    out (REMOVE). The same file gives the same copy, byte for byte."""
    bigf = Bigf(original)
    movie = Movie(bigf.part('0'), bigf.part('1'))
    data = bytearray(movie.data)
    for at, old, new in changes(movie, mode):
        if len(old) != len(new) or data[at:at + len(old)] != old:
            raise ValueError(f"change at {at:#x} does not fit")
        data[at:at + len(new)] = new
    data = bytes(data)
    _check(movie, data, mode)
    part = refpack.compress(data) if movie.packed else data
    return bigf.rebuilt({'0': part})


def _check(movie, data, mode):
    """The changed movie still reads to the end of every script, keeps every other entry as it
    was and has the dead ones hidden (or gone)."""
    if len(data) != len(movie.data):
        raise ValueError("the changed movie has another size")
    for start in movie.streams():
        before, after = movie.code(start), movie.code(start, data)
        if before[-1].end != after[-1].end:
            raise ValueError(f"script at {start:#x} ends elsewhere after the change")
    dead = set(DEAD)
    old = [(e.array, e.key) for e in movie.entries()]
    new = movie.entries(data)
    if mode == REMOVE:
        if [(e.array, e.key) for e in new] != [k for k in old if k not in dead]:
            raise ValueError("the menu entries changed beyond the dead ones")
    else:
        if [(e.array, e.key) for e in new] != old:
            raise ValueError("the menu entries changed")
        for e in new:
            if (e.array, e.key) in dead and not e.hidden:
                raise ValueError(f"menu entry {e.key} of {e.array} is not hidden")


def _source(disc):
    """An art/lab.py Disc, an IsoImage, a disc image's path or a folder with the disc's .big files."""
    if hasattr(disc, 'source'):
        return disc.source
    if isinstance(disc, str) and os.path.isfile(disc):
        return IsoImage(disc)
    return disc


def original_file(disc):
    """The disc's own mainmenuitems.big (bytes); read only."""
    return EbArchive.open(_source(disc), ARCHIVE).read(MENU_FILE)


def hidden_files(disc, mode=HIDE):
    """{loose path (tuple, relative to the game's USRDIR): bytes} for the player's own disc."""
    return {REL: hidden_file(original_file(disc), mode)}


def menu_entries(file_bytes):
    """[(list, text key, hidden)] of a mainmenuitems.big, in the script's order (for checks and
    the notes)."""
    bigf = Bigf(file_bytes)
    movie = Movie(bigf.part('0'), bigf.part('1'))
    return [(e.array, e.key, e.hidden) for e in movie.entries()]
