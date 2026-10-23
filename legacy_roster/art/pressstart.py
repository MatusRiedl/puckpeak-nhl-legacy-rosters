"""No Press Start: with the game patch's intro skip (gamepatch.INTRO_ENTRY, the game's own quick boot) the game still
stops on the title screen until Start is pressed. A changed copy of that screen presses it by itself.

The screen is fe/ion/game/screens/bootflow/03_pressstart.big (inside cacheboot.big on the disc; the same file on the EU
and the NA disc), a BIGF archive around an Apt UI movie like the main menu's (art/menus.py). Its function
`transitionDone` ends with

    if (_global.QUICK_BOOT_FLOW == true) showPressStart();

and the copy makes that

    if (_global.QUICK_BOOT_FLOW) { showPressStart(); startPressed(0); }

`startPressed(0)` is what the screen's own key handler calls on a Start press of controller 0: it hides the screen,
plays the select sound and starts the profile and roster loads. The 18 bytes keep their length, so no pointer moves and
the next function starts where it did. In a full boot (no quick boot) QUICK_BOOT_FLOW is false and the copy behaves as
the disc's file. Research: docs/notes/press-start.md.

Nothing here knows offsets: the function and the constants are found by name in the player's own file, and only the
file this change was made for (size and SHA-1) is taken. The copy is made on the player's PC from their own disc (rule 9)
and goes into the game's folder on RPCS3's hard disk (`REL`, relative to dev_hdd0/game/<TITLEID>/USRDIR), which the
game reads before cacheboot.big.
"""
import hashlib
import struct

from . import refpack
from .disc import EbArchive
from .menus import Bigf, Movie, _source

ARCHIVE = 'cacheboot.big'
PRESS_FILE = 'fe/ion/game/screens/bootflow/03_pressstart.big'
REL = tuple(PRESS_FILE.split('/'))
PRESS_VERSION = '#1'            # change when the copy is made another way
SIZE = 357_924
SHA1 = 'db01dae14b000c87fc0cfb1ce986321d89923ada'
FLAGS = 0x2012a                 # transitionDone's DefineFunction2 flags: register 1 holds _global

DEFINE_FUNCTION2, PUSH_REGISTER, GET_NAMED_MEMBER, PUSH_TRUE, EQUALS2, NOT = 0x8E, 0xB9, 0xAF, 0x73, 0x49, 0x12
BRANCH_IF_TRUE, PUSH_ZERO, PUSH_ONE, CALL_NAMED_FUNC_POP = 0x9D, 0x59, 0x5A, 0xB0
TAIL = 18                       # the bytes of transitionDone that change


def functions(movie, data=None):
    """{name: (body start, body end, flags)} of every DefineFunction2 in the movie's scripts."""
    data = movie.data if data is None else data
    out = {}
    for start in movie.streams():
        for ins in movie.code(start, data):
            if ins.op != DEFINE_FUNCTION2:
                continue
            name_at, _params, _regs, f1, f2, _param_at, size = struct.unpack_from('>IIBBHII', data, (ins.pos + 4) & ~3)
            name = data[name_at:data.index(b'\0', name_at)].decode('latin1') if name_at else ''
            out[name] = (ins.end, ins.end + size, (f1 << 16) | f2)
    return out


def pool_index(pool, consts, name):
    """The number of constant `name` in the pool (one byte: it must be there once, below 256)."""
    hits = [k for k, c in enumerate(pool) if k < 256 and c < len(consts) and consts[c] == name]
    if len(hits) != 1:
        raise ValueError(f"the screen's script has the constant {name!r} {len(hits)} times, expected once")
    return hits[0]


def _tail(at, end, quick, show, press=None):
    """transitionDone's last bytes, from `at` to `end`: the disc's (press None) or the copy's. A BranchIfTrue's
    argument starts on the next multiple of 4, so the padding depends on where the bytes sit."""
    out = bytearray((PUSH_REGISTER, 1, GET_NAMED_MEMBER, quick))
    out += bytes((NOT,)) if press is not None else bytes((PUSH_TRUE, EQUALS2, NOT))
    out.append(BRANCH_IF_TRUE)
    while (at + len(out)) % 4:
        out.append(0)
    out += b'\0\0\0\0'
    branch_end = at + len(out)
    out += bytes((PUSH_ZERO, CALL_NAMED_FUNC_POP, show))
    if press is not None:
        out += bytes((PUSH_ZERO, PUSH_ONE, CALL_NAMED_FUNC_POP, press))
    struct.pack_into('>i', out, branch_end - at - 4, end - branch_end)
    return bytes(out)


def changed_movie(original):
    """(archive, movie, changed movie data, functions) of the disc's 03_pressstart.big (bytes)."""
    if len(original) != SIZE or hashlib.sha1(original).hexdigest() != SHA1:
        raise ValueError("This is not the Press Start screen this change was made for.")
    bigf = Bigf(original)
    movie = Movie(bigf.part('0'), bigf.part('1'))
    if not movie.packed:
        raise ValueError("the Press Start screen's movie is not packed")
    found = functions(movie)
    if 'transitionDone' not in found or 'showPressStart' not in found or 'startPressed' not in found:
        raise ValueError("the Press Start screen lacks transitionDone, showPressStart or startPressed")
    _body, end, flags = found['transitionDone']
    if flags != FLAGS:
        raise ValueError(f"transitionDone has the flags {flags:#x}, expected {FLAGS:#x}")
    at = end - TAIL
    pool = next((i.pool for s in movie.streams() for i in movie.code(s) if i.pos == at), None)
    if pool is None:
        raise ValueError("no instruction starts where transitionDone's change would")
    quick, show, press = (pool_index(pool, movie.consts, n) for n in ('QUICK_BOOT_FLOW', 'showPressStart',
                                                                      'startPressed'))
    before, after = _tail(at, end, quick, show), _tail(at, end, quick, show, press)
    if len(before) != TAIL or len(after) != TAIL or movie.data[at:end] != before:
        raise ValueError("transitionDone does not end the way it should")
    data = bytearray(movie.data)
    data[at:end] = after
    return bigf, movie, bytes(data), found


def packed_file(bigf, movie, data, end):
    """The archive with the changed movie, after the checks: every script reads to the same end, transitionDone (ending
    at `end`) ends with the call of startPressed and something starts after it, only part 0 changed."""
    if len(data) != len(movie.data):
        raise ValueError("the changed movie has another size")
    for start in movie.streams():
        code = movie.code(start, data)
        if movie.code(start)[-1].end != code[-1].end:
            raise ValueError(f"the script at {start:#x} ends elsewhere after the change")
        last = [i for i in code if i.end == end]
        if last and (last[0].op != CALL_NAMED_FUNC_POP or last[0].text != 'startPressed'
                     or not any(i.pos == end for i in code)):
            raise ValueError("transitionDone does not end with startPressed")
    packed = refpack.compress(data)
    if refpack.decompress(packed) != data:
        raise ValueError("the packed movie does not unpack to itself")
    out = bigf.rebuilt({'0': packed})
    new = Bigf(out)
    if any(new.part(name) != bigf.part(name) for name, _o, _s in bigf.parts if name != '0'):
        raise ValueError("another part of the Press Start screen changed")
    return out


def skip_file(original):
    """A copy of the game's 03_pressstart.big (bytes) that presses Start by itself in a quick boot. The same file gives
    the same copy, byte for byte."""
    bigf, movie, data, found = changed_movie(original)
    return packed_file(bigf, movie, data, found['transitionDone'][1])


def original_file(disc):
    """The disc's own 03_pressstart.big (bytes); read only."""
    return EbArchive.open(_source(disc), ARCHIVE).read(PRESS_FILE)


def skip_files(disc):
    """{loose path (tuple, relative to the game's USRDIR): bytes} for the player's own disc."""
    return {REL: skip_file(original_file(disc))}
