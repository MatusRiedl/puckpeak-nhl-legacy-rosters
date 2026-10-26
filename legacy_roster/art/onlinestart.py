"""Online start: the main menu's second boot branch goes to online play by itself.

The main menu's show function (boot.big `fe/ion/game/menus/mainmenuitems.big`, art/menus.py) ends with

    if (IS_AUTO_SELECT_PLAYNOW_ON_BOOT) { clear it and the HUT flag; highlight Play Now }
    else if (IS_AUTO_SELECT_HUT_ON_BOOT) { clear the HUT flag; highlight Hockey Ultimate Team }
    CheckForNewScenarios()

The native answer for the first flag is true on every normal boot (the game's own thunk `li r3,1`), so the second branch never
runs. The game patch's entry `gamepatch.ONLINE_START` (ticked by the program for one start only) makes the answer false; the
second flag is already true then. This change turns the second branch into

    clear the HUT flag;  OverrideUnicornMenuItemForDemo()

and gives that demo-only function a new body, the three things a pressed "Online Versus" item does:

    zone.gControllerIDCurrentScreen = 0          // enterMatchMaker hands it to the sign-in; nothing sets it before a press
    gMenuTransition(zone, true)                  // takes the main menu away, as a pressed item does
    objMainMenu.enterMatchMaker(ONLINE_PLAYNOW)  // the Online Versus Play entry

(`zone` is the screen-flow object of the game's scripts; its name is put together below.)

The game deletes the demo functions again right after defining them (`delete OverrideUnicornMenuItemForDemo`, the branch
for a game that is not a demo), so a call by name finds nothing: that is why every earlier try, which named a dead function,
did nothing. The delete statement (5 bytes) becomes filler, which keeps this one function alive; nothing else calls it.
Why not one inline block? The branch has 21 bytes and the three steps need 24 plus the clear.

Without the patch entry the branch is dead, so the copy behaves exactly like the game's own file (lab, 2026-10-26: Play
highlighted, the news panel as before, and after Back from online play the menu does not start it again). Every change keeps
its length (filler pads), so no pointer moves. Research: docs/notes/online-boot-hook.md.

The cave also leaves a note for the two screens that follow, `zone.OPTION_LEFT = true` (a name both files already hold; nothing
reads it on the zone), and two more files change so that no button is left to press:

  * welcomebackscreen.big (cache.big): when the "Welcome back" panel has finished moving in, it goes on by itself, as if
    Continue were pressed (`_AnimateComplete` calls `_OnContinue`; the trace line it began with goes). Always, not only
    after the note: the panel only greets a player who is signed in.
  * matchmakingscreen.big (cache.big): when the screen has finished moving in, `animateInComplete` calls a handler that no
    one else calls (`OnCreateSessionTollBoothFailure`); the handler now says: if the note is set, clear it and start the
    quick search, as the pressed Search tile does (`initiateSearchQuick`). Cleared at once, so Back and a second visit
    behave as before. Without the note the screen is the game's own.
"""
import struct

from .menus import _filler, _pool_index
from .pressstart import functions

CACHE = 'cache.big'
WELCOME = 'fe/ion/online/screens/login/welcomebackscreen.big'
MATCH = 'fe/ion/online/screens/matchmaking/matchmakingscreen.big'
WELCOME_REL = tuple(WELCOME.split('/'))
MATCH_REL = tuple(MATCH.split('/'))
FILES_VERSION = '#1'            # change when the two screens' copies are made another way
NOTE = 'OPTION_LEFT'            # the member of the zone that says "start the search by yourself" (in both files' pools)
HANDLER = 'OnCreateSessionTollBoothFailure'     # a function of the matchmaking screen that no script calls

ONLINE_PLAYNOW = 16             # Notification.eState.ONLINE_PLAYNOW (main.big)
CAVE = 'OverrideUnicornMenuItemForDemo'     # kept alive; its new body does the start
CAVE_FLAGS = 0x4012a
MIN_CAVE = 64
HUT_FLAG = 'IS_AUTO_SELECT_HUT_ON_BOOT'
ZONE = 'E' + 'A_ZONE'             # the scripts' screen-flow object (written in pieces: tools/clean_check.py)
(PUSH_ZERO, PUSH_ONE, PUSH_TRUE, PUSH_BYTE, PUSH_CONST8, PUSH_CONST, PUSH_VAR, SET_MEMBER, CALL_METHOD_POP,
 CALL_FUNCTION_POP, DELETE, DELETE_VAR, PUSH_REGISTER, PUSH_FALSE, GET_MEMBER, NOT, BRANCH_IF_TRUE, CALL_METHOD_C8) = (
    0x59, 0x5A, 0x73, 0xB5, 0xA2, 0xA3, 0xAE, 0x4F, 0x5D, 0x5B, 0x3B, 0x17, 0xB9, 0x74, 0x4E, 0x12, 0x9D, 0xB2)
DEFINE_FUNCTION2 = 0x8E
HUT_CALL = 14                   # the bytes of the highlight call in the HUT branch that change
CLEAR = 7                       # the bytes before it: the clear of the HUT flag, which stay
DELETE_LEN = 5                  # `PushConstW name, Delete, Pop`: the statement that removes the function again


def _word(n):
    return struct.pack('>H', n)


def _find_hut(movie):
    """(instruction of the TXT_HUT push, end of the highlight call) of the HUT branch."""
    found = []
    for start in movie.streams():
        code = movie.code(start)
        for n, ins in enumerate(code):
            if ins.text != 'TXT_HUT' or n < 3 or n + 6 >= len(code):
                continue
            if (code[n - 3].text == HUT_FLAG and code[n - 2].op == PUSH_FALSE and code[n - 1].op == SET_MEMBER
                    and code[n + 1].op == PUSH_ONE and code[n + 5].text == 'SetHighlightedMenuItem'
                    and code[n + 6].op == CALL_METHOD_POP):
                found.append((ins, code[n + 6].end))
    if len(found) != 1:
        raise ValueError(f"the main menu's HUT branch: found {len(found)} times, expected once")
    return found[0]


def _find_delete(movie):
    """The instruction of `delete CAVE`'s name push (the function the game removes again)."""
    found = []
    for start in movie.streams():
        code = movie.code(start)
        for n, ins in enumerate(code[:-2]):
            if ins.op == PUSH_CONST and ins.text == CAVE and code[n + 1].op == DELETE and code[n + 2].op == DELETE_VAR:
                found.append((ins, code[n + 2].end))
    if len(found) != 1:
        raise ValueError(f"the delete of {CAVE}: found {len(found)} times, expected once")
    return found[0]


def _push(ins, movie, name):
    """The push of constant `name` (one byte of number when it fits, else two)."""
    k = _pool_index(ins, movie.consts, name)
    return bytes((PUSH_CONST8, k)) if k < 256 else bytes((PUSH_CONST,)) + _word(k)


def _body(ins, movie):
    """The cave's new body: the controller, the menu taken away, the call."""
    eaz, cid, gmt, mm, em = (_pool_index(ins, movie.consts, n) for n in (
        ZONE, 'gControllerIDCurrentScreen', 'gMenuTransition', 'objMainMenu', 'enterMatchMaker'))
    if max(eaz, cid, mm) > 255:
        raise ValueError("a constant of the start has no one-byte number")
    out = bytes((PUSH_VAR, eaz)) + _push(ins, movie, NOTE) + bytes((PUSH_TRUE, SET_MEMBER))        # zone.OPTION_LEFT = true
    out += bytes((PUSH_VAR, eaz, PUSH_CONST8, cid, PUSH_ZERO, SET_MEMBER))                         # zone.gControllerIDCurrentScreen = 0
    out += bytes((PUSH_TRUE, PUSH_VAR, eaz, PUSH_BYTE, 2, PUSH_CONST)) + _word(gmt) + bytes((CALL_FUNCTION_POP,))
    out += bytes((PUSH_BYTE, ONLINE_PLAYNOW, PUSH_ONE, PUSH_VAR, mm, PUSH_CONST)) + _word(em) + bytes((CALL_METHOD_POP,))
    return out


def changes(movie):
    """[(offset, old bytes, new bytes)] (same length each) that make the HUT branch enter online play."""
    hut, hut_end = _find_hut(movie)
    if hut_end - hut.pos != HUT_CALL:
        raise ValueError(f"the HUT branch's highlight call is {hut_end - hut.pos} bytes, expected {HUT_CALL}")
    clear = movie.data[hut.pos - CLEAR:hut.pos]
    if clear[0] != PUSH_REGISTER or clear[-2:] != bytes((PUSH_FALSE, SET_MEMBER)):
        raise ValueError("the HUT branch does not start by clearing its flag")
    found = functions(movie)
    if CAVE not in found:
        raise ValueError(f"the main menu has no function {CAVE}")
    start, end, flags = found[CAVE]
    if flags != CAVE_FLAGS:
        raise ValueError(f"{CAVE} has the flags {flags:#x}, expected {CAVE_FLAGS:#x}")
    if end - start < MIN_CAVE:
        raise ValueError(f"{CAVE} is only {end - start} bytes")
    body = _body(hut, movie)
    drop, drop_end = _find_delete(movie)
    if drop_end - drop.pos != DELETE_LEN:
        raise ValueError(f"the delete of {CAVE} is {drop_end - drop.pos} bytes, expected {DELETE_LEN}")
    index = _pool_index(hut, movie.consts, CAVE)
    call = bytes((PUSH_ZERO, PUSH_CONST)) + _word(index) + bytes((CALL_FUNCTION_POP,))
    out = [(hut.pos, movie.data[hut.pos:hut_end], call + _filler(HUT_CALL - len(call))),
           (start, movie.data[start:end], body + _filler(end - start - len(body))),
           (drop.pos, movie.data[drop.pos:drop_end], _filler(DELETE_LEN))]
    return sorted(out)


def _ins_at(movie, pos):
    for start in movie.streams():
        for ins in movie.code(start):
            if ins.pos == pos:
                return ins
    raise ValueError(f"no instruction at {pos:#x}")


def _methods(movie):
    """[(name, body start, body end, flags)] of the functions the screens' scripts define: a method has no name of its own,
    the constant pushed right before its definition names it."""
    out = []
    for start in movie.streams():
        code = movie.code(start)
        for n, ins in enumerate(code):
            if ins.op != DEFINE_FUNCTION2:
                continue
            name_at, _params, _regs, f1, f2, _param_at, size = struct.unpack_from('>IIBBHII', movie.data, (ins.pos + 4) & ~3)
            name = movie.data[name_at:movie.data.index(bytes(1), name_at)].decode('latin1') if name_at else ''
            if not name and n and code[n - 1].text:
                name = code[n - 1].text
            out.append((name, ins.end, ins.end + size, (f1 << 16) | f2))
    return out


def _function(movie, name, flags, size):
    found = [m for m in _methods(movie) if m[0] == name]
    if len(found) != 1:
        raise ValueError(f"the script defines {name} {len(found)} times, expected once")
    _name, start, end, got = found[0]
    if got != flags or end - start != size:
        raise ValueError(f"{name} has flags {got:#x} and {end - start} bytes, expected {flags:#x} and {size}")
    return start, end


def welcome_changes(movie):
    """The Welcome back panel goes on by itself: the trace line at the start of `_AnimateComplete` (7 bytes) leaves and
    the call of `_OnContinue` takes the place after the two statements that make the panel ready for a press."""
    start, end = _function(movie, '_AnimateComplete', 0x20029, 18)
    first = _ins_at(movie, start)
    old = movie.data[start:end]
    if (first.op != PUSH_CONST8 or first.text != '_AnimateComplete()' or old[7:9] != bytes((PUSH_REGISTER, 1))
            or old[-5:-2] != bytes((PUSH_ZERO, PUSH_REGISTER, 1)) or old[-2] != CALL_METHOD_C8):
        raise ValueError("_AnimateComplete does not look as expected")
    k = _pool_index(first, movie.consts, '_OnContinue')
    if k > 255:
        raise ValueError("_OnContinue has no one-byte number")
    new = old[7:] + bytes((PUSH_ZERO, PUSH_REGISTER, 1, CALL_METHOD_C8, k))
    return [(start, old, new + _filler(len(old) - len(new)))]


def _gate(first, movie, start, size):
    """The dead handler's new body: if zone.OPTION_LEFT { zone.OPTION_LEFT = false; this.initiateSearchQuick() }.
    The branch jumps over both statements to filler (a branch's offset starts on a 4-byte boundary of the movie)."""
    eaz = _pool_index(first, movie.consts, ZONE)
    search = _pool_index(first, movie.consts, 'initiateSearchQuick')
    if max(eaz, search) > 255:
        raise ValueError("a constant of the search has no one-byte number")
    note = _push(first, movie, NOTE)
    out = bytearray((PUSH_VAR, eaz)) + note + bytes((GET_MEMBER, NOT, BRANCH_IF_TRUE))
    while (start + len(out)) % 4:
        out.append(0)
    at = len(out)
    out += bytes(4)
    out += bytes((PUSH_VAR, eaz)) + note + bytes((PUSH_FALSE, SET_MEMBER))
    out += bytes((PUSH_ZERO, PUSH_REGISTER, 1, CALL_METHOD_C8, search))
    struct.pack_into('>i', out, at, len(out) - (at + 4))
    if size - len(out) < 2:
        raise ValueError("no room for the search gate")
    return bytes(out) + _filler(size - len(out))


def match_changes(movie):
    """The matchmaking screen searches by itself: `animateInComplete` loses its trace line (14 bytes) and calls the dead
    handler last, after the screen is ready (the search sets its own state, which must come after `setScreenState`)."""
    a_start, a_end = _function(movie, 'animateInComplete', 0x20029, 36)
    h_start, h_end = _function(movie, HANDLER, 0x30129, 107)
    first = _ins_at(movie, a_start)
    old = movie.data[a_start:a_end]
    texts = [i.text for s in movie.streams() for i in movie.code(s) if a_start <= i.pos < a_end]
    if old[14] != PUSH_ZERO or texts[-4:] != ['STATE_TOP_ACTIVE', None, None, 'setScreenState'] or 'AnimateIn' not in texts:
        raise ValueError("animateInComplete does not look as expected")
    if sum(1 for s in movie.streams() for i in movie.code(s) if i.text == HANDLER) != 1:
        raise ValueError(f"{HANDLER} is named more than by its own definition")
    handler = _ins_at(movie, h_start)
    call = bytes((PUSH_ZERO, PUSH_REGISTER, 1)) + _push(first, movie, HANDLER) + bytes((CALL_METHOD_POP,))
    new = old[14:] + call
    return sorted([(a_start, old, new + _filler(len(old) - len(new))),
                   (h_start, movie.data[h_start:h_end], _gate(handler, movie, h_start, h_end - h_start))])


def _apply(movie, data, listed):
    """`data` (a bytearray of the movie) with the same-length changes made; every script must end where it did."""
    taken = []
    for at, old, new in listed:
        if len(old) != len(new) or data[at:at + len(old)] != old:
            raise ValueError(f"change at {at:#x} does not fit")
        if any(at < b and a < at + len(new) for a, b in taken):
            raise ValueError(f"change at {at:#x} overlaps another")
        taken.append((at, at + len(new)))
        data[at:at + len(new)] = new
    data = bytes(data)
    for stream in movie.streams():
        if movie.code(stream)[-1].end != movie.code(stream, data)[-1].end:
            raise ValueError(f"the script at {stream:#x} ends elsewhere after the change")
    return data


def _patched(original, make):
    """A copy (bytes) of a UI file with the changes `make(movie)` lists."""
    from . import menus, refpack
    bigf = menus.Bigf(original)
    movie = menus.Movie(bigf.part('0'), bigf.part('1'))
    data = _apply(movie, bytearray(movie.data), make(movie))
    return bigf.rebuilt({'0': refpack.compress(data) if movie.packed else data})


def start_file(original, mode=None):
    """A copy of the game's mainmenuitems.big (bytes) with the dead entries hidden (art/menus.py) and the online start in
    place. The same file gives the same copy, byte for byte."""
    from . import menus, refpack
    mode = mode or menus.HIDE
    bigf = menus.Bigf(original)
    movie = menus.Movie(bigf.part('0'), bigf.part('1'))
    data = _apply(movie, bytearray(movie.data), menus.changes(movie, mode) + changes(movie))
    menus._check(movie, data, mode)
    return bigf.rebuilt({'0': refpack.compress(data) if movie.packed else data})


def welcome_file(original):
    """A copy of the game's welcomebackscreen.big that goes on by itself."""
    return _patched(original, welcome_changes)


def match_file(original):
    """A copy of the game's matchmakingscreen.big that starts the quick search by itself when the note is set."""
    return _patched(original, match_changes)


def screen_files(disc):
    """{loose path (tuple, relative to the game's USRDIR): bytes} of the two screens that follow the main menu (the Welcome
    back panel and the matchmaking screen), made from the player's own disc. Without the online start's note they behave
    as before, except that the Welcome back panel goes on by itself."""
    from . import menus
    cache = menus.EbArchive.open(menus._source(disc), CACHE)
    return {WELCOME_REL: welcome_file(cache.read(WELCOME)), MATCH_REL: match_file(cache.read(MATCH))}


def start_files(disc, mode=None):
    """{loose path: bytes} for the player's own disc: the main menu, the Welcome back panel and the matchmaking screen."""
    from . import menus
    files = {menus.REL: start_file(menus.original_file(disc), mode)}
    files.update(screen_files(disc))
    return files
