"""No Press Start (art/pressstart.py): the title screen's copy that presses Start by itself in a quick boot. The file
tests need the game disc (LEGACY_ROSTER_DISC, read only); the bytes of the change are checked without it."""
import hashlib
import os

import pytest

from legacy_roster.art import pressstart as P

DISC = os.environ.get('LEGACY_ROSTER_DISC')
needs_disc = pytest.mark.skipif(not DISC, reason="needs the game disc (LEGACY_ROSTER_DISC)")
COPY_SHA1 = '23fdd2f076187cd4ad37edc67e3fe7d4f0a9bb74'      # the copy from the EU and the NA disc (press-start.md)


def test_the_change_is_the_disc_s_eighteen_bytes_and_the_call_of_start_pressed():
    # the disc's transitionDone: 0x40fd to 0x410f, QUICK_BOOT_FLOW #202, showPressStart #203, startPressed #78
    before = P._tail(0x40fd, 0x410f, 0xca, 0xcb)
    after = P._tail(0x40fd, 0x410f, 0xca, 0xcb, 0x4e)
    assert before.hex(' ') == 'b9 01 af ca 73 49 12 9d 00 00 00 00 00 00 03 59 b0 cb'
    assert after.hex(' ') == 'b9 01 af ca 12 9d 00 00 00 00 07 59 b0 cb 59 5a b0 4e'


def test_another_file_is_refused():
    with pytest.raises(ValueError, match="not the Press Start screen"):
        P.skip_file(b'BIGF' + bytes(P.SIZE - 4))


@pytest.fixture(scope='module')
def original():
    return P.original_file(DISC)


@needs_disc
def test_the_copy_presses_start_after_the_quick_boot_and_changes_nothing_else(original):
    copy = P.skip_file(original)
    assert hashlib.sha1(copy).hexdigest() == COPY_SHA1 and P.skip_file(original) == copy
    bigf, movie, data, found = P.changed_movie(original)
    assert sum(a != b for a, b in zip(movie.data, data)) == 11 and len(data) == len(movie.data)
    new = P.Bigf(copy)
    assert P.Movie(new.part('0'), new.part('1')).data == data
    assert all(new.part(n) == bigf.part(n) for n, _o, _s in bigf.parts if n != '0')
    assert P.functions(movie, data) == found                         # every function keeps its place and size
    assert P.skip_files(DISC) == {P.REL: copy}
    assert P.REL == ('fe', 'ion', 'game', 'screens', 'bootflow', '03_pressstart.big')


@needs_disc
def test_a_copy_already_changed_is_refused(original):
    with pytest.raises(ValueError):
        P.skip_file(P.skip_file(original))
