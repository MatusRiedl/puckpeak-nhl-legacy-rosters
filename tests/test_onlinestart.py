"""Online start (art/onlinestart.py): the main menu's second boot branch goes to online play by itself. The tests need the
game disc (LEGACY_ROSTER_DISC, read only)."""
import os

import pytest

from legacy_roster.art import menus, onlinestart as S
from legacy_roster.art.pressstart import functions

DISC = os.environ.get('LEGACY_ROSTER_DISC')
needs_disc = pytest.mark.skipif(not DISC, reason="needs the game disc (LEGACY_ROSTER_DISC)")


@pytest.fixture(scope='module')
def original():
    return menus.original_file(DISC)


@pytest.fixture(scope='module')
def movie(original):
    bigf = menus.Bigf(original)
    return menus.Movie(bigf.part('0'), bigf.part('1'))


@needs_disc
def test_three_places_change_and_every_change_keeps_its_length(movie):
    changed = S.changes(movie)
    assert [(at, len(new)) for at, _old, new in changed] == [(0x2260, 157), (0x2f4b, 14), (0x680c, 5)]
    assert all(len(old) == len(new) and movie.data[at:at + len(old)] == old for at, old, new in changed)


@needs_disc
def test_the_branch_clears_its_flag_and_calls_the_kept_function(movie):
    _at, _old, call = next(c for c in S.changes(movie) if c[0] == 0x2f4b)
    assert call[:2] == bytes((S.PUSH_ZERO, S.PUSH_CONST)) and call[4] == S.CALL_FUNCTION_POP
    assert movie.data[0x2f44:0x2f4b][-2:] == bytes((S.PUSH_FALSE, S.SET_MEMBER))     # the clear stays as the game has it
    assert all(not (at < 0x2f62 and 0x2f59 < at + len(new)) for at, _old, new in S.changes(movie))   # CheckForNewScenarios stays


@needs_disc
def test_the_new_body_sets_the_controller_hides_the_menu_and_enters_online_play(movie):
    _at, _old, body = next(c for c in S.changes(movie) if c[0] == 0x2260)
    body = body[7:]                                                 # after the note (a zone member set to true)
    assert body[0] == S.PUSH_VAR and body[2] == S.PUSH_CONST8 and body[3 + 1] == S.PUSH_ZERO and body[5] == S.SET_MEMBER
    assert bytes((S.PUSH_BYTE, S.ONLINE_PLAYNOW, S.PUSH_ONE, S.PUSH_VAR)) in body and bytes((S.PUSH_TRUE, S.PUSH_VAR)) in body
    assert functions(movie)[S.CAVE][2] == S.CAVE_FLAGS


@needs_disc
def test_the_copy_is_the_same_each_time_and_keeps_the_hidden_entries_and_function_sizes(original, movie):
    copy = S.start_file(original)
    assert S.start_file(original) == copy
    bigf = menus.Bigf(copy)
    new = menus.Movie(bigf.part('0'), bigf.part('1'))
    assert len(new.data) == len(movie.data)
    assert functions(new) == functions(movie)                       # every function keeps its place and size
    assert [(e.array, e.key) for e in new.entries()] == [(e.array, e.key) for e in movie.entries()]
    assert all(e.hidden for e in new.entries() if (e.array, e.key) in set(menus.DEAD))
    assert S.start_files(DISC)[menus.REL] == copy


@needs_disc
def test_a_copy_already_changed_is_refused(original):
    with pytest.raises(ValueError):
        S.start_file(S.start_file(original))


@pytest.fixture(scope='module')
def cache():
    return menus.EbArchive.open(menus._source(DISC), S.CACHE)


def _movie(file_bytes):
    bigf = menus.Bigf(file_bytes)
    return menus.Movie(bigf.part('0'), bigf.part('1'))


@needs_disc
def test_the_cave_leaves_the_note_the_matchmaking_screen_reads(movie):
    _at, _old, body = next(c for c in S.changes(movie) if c[0] == 0x2260)
    assert body[:2] == bytes((S.PUSH_VAR, body[1])) and body[2] in (S.PUSH_CONST8, S.PUSH_CONST)
    assert bytes((S.PUSH_TRUE, S.SET_MEMBER)) in body[:8]


@needs_disc
def test_the_welcome_back_panel_goes_on_by_itself(cache):
    original = cache.read(S.WELCOME)
    copy = S.welcome_file(original)
    assert S.welcome_file(original) == copy
    old, new = _movie(original), _movie(copy)
    assert len(new.data) == len(old.data) and S._methods(new) == S._methods(old)
    start, end = S._function(new, '_AnimateComplete', 0x20029, 18)
    texts = [i.text for st in new.streams() for i in new.code(st) if start <= i.pos < end and i.text]
    assert texts == ['mScreenHasFinishedTransition', '_EnableEventHandler', '_OnContinue']        # no trace line, the press's call last
    assert sum(a != b for a, b in zip(old.data, new.data)) < 20


@needs_disc
def test_the_matchmaking_screen_searches_only_when_the_note_is_set(cache):
    original = cache.read(S.MATCH)
    copy = S.match_file(original)
    assert S.match_file(original) == copy
    old, new = _movie(original), _movie(copy)
    start, end = S._function(new, S.HANDLER, 0x30129, 107)

    def outside(movie):                         # the handler's old body held a small function of its own, gone with it
        return [m for m in S._methods(movie) if not start <= m[1] < end]
    assert len(new.data) == len(old.data) and outside(new) == outside(old)
    code = [i for st in new.streams() for i in new.code(st) if start <= i.pos < end]
    assert [i.text for i in code if i.text] == [S.ZONE, S.NOTE, S.ZONE, S.NOTE, 'initiateSearchQuick']
    branch = next(i for i in code if i.op == S.BRANCH_IF_TRUE)
    assert branch.pos == 0x41ea and branch.end % 4 == 0
    target = branch.end + int.from_bytes(new.data[branch.end - 4:branch.end], 'big', signed=True)
    assert code[-1].end > target >= branch.end and any(i.pos == target for i in code)         # lands on an instruction inside the body
    a_start, a_end = S._function(new, 'animateInComplete', 0x20029, 36)
    texts = [i.text for st in new.streams() for i in new.code(st) if a_start <= i.pos < a_end and i.text]
    assert texts[-2:] == ['setScreenState', S.HANDLER]                                          # the search comes after the screen is ready


@needs_disc
def test_all_three_files_are_made_for_the_players_own_disc():
    files = S.start_files(DISC)
    assert set(files) == {menus.REL, S.WELCOME_REL, S.MATCH_REL}
    assert S.start_files(DISC) == files


@needs_disc
def test_a_screen_file_that_does_not_look_like_the_games_is_refused(cache):
    with pytest.raises(ValueError):
        S.welcome_file(S.welcome_file(cache.read(S.WELCOME)))
    with pytest.raises(ValueError):
        S.match_file(S.match_file(cache.read(S.MATCH)))
