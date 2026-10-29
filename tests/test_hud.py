"""The overlay over the game (legacy_roster/hud, ported from NHL 19): the timeline maths is pure; the Windows drawing gets a smoke run with nothing shown."""
import sys
import time

import pytest

from legacy_roster.hud import anim

CARD = dict(title='Final', sub='4 - 2 win', rating_from=1044, rating_to=1067, tier='Rookie', next_name='Pro', next_at=1100,
            band_low=1000)


def test_easing_is_bounded_and_hits_its_ends():
    for f in (anim.out_cubic, anim.in_cubic, anim.in_out_cubic):
        assert f(0) == 0 and f(1) == 1
    assert anim.out_back(1) == pytest.approx(1) and max(anim.out_back(k / 100) for k in range(101)) > 1   # overshoots
    assert anim.span(5, 2, 4) == 1 and anim.span(1, 2, 4) == 0 and anim.span(3, 2, 4) == .5
    assert anim.pulse(0) == pytest.approx(0) and anim.pulse(.5) == pytest.approx(1) and anim.pulse(1) == pytest.approx(0, abs=1e-9)


def test_a_toast_slides_in_waits_and_leaves():
    t = anim.Toast('Bo', 'gg', 10.0, hold=2.0)
    assert t.shown(10.0) == 0 and t.shown(10.0 + anim.Toast.IN) == pytest.approx(1)
    assert t.shown(11.5) == 1 and not t.done(11.5)
    assert 0 < t.shown(10 + anim.Toast.IN + 2.0 + .2) < 1
    assert t.done(10 + anim.Toast.IN + 2.0 + anim.Toast.OUT + .01)


def test_chat_keeps_the_newest_few_and_makes_room_by_sending_the_oldest_out():
    chat = anim.Chat(limit=2)
    for i, now in enumerate((0, 1, 2)):
        chat.add('P', f'm{i}', now)
    assert [t.text for t in chat.lines] == ['m0', 'm1', 'm2'] or len(chat.lines) <= 3
    assert [t.text for t in chat.tick(2.2 + anim.Toast.OUT)] == ['m1', 'm2']      # m0 left early, the two newest stay
    assert chat.tick(100) == []
    chat.add('P', 'x' * 500, 0)
    assert len(chat.lines[0].text) == 140                                         # one line, not a wall of text


def test_the_result_counts_up_fills_the_bar_pops_the_chip_and_fades():
    r = anim.Result(CARD, 100.0, hold=5.0)
    assert r.rating(100.0) == 1044 and r.alpha(100.0) == 0 and r.lift(100.0) == pytest.approx(40)
    assert r.rating(100 + r.COUNT_END) == 1067 and r.rating(200) == 1067
    mid = r.rating(100 + (r.COUNT_AT + r.COUNT_END) / 2)
    assert 1044 < mid < 1067
    assert r.progress(100 + r.COUNT_END) == pytest.approx(.67) and r.progress(100.0) == pytest.approx(.44)
    assert r.chip(100.0) == 0 and r.chip(100 + r.CHIP_AT + .45) == pytest.approx(1)
    assert r.flash(101) == 0 and r.banner(101) == 0 and r.ring(101) == 0               # no rank-up: no flourish
    assert r.alpha(102) == 1 and 0 < r.alpha(105.3) < 1 and r.done(106) and not r.done(104)


def test_a_rank_up_gets_a_flash_a_ring_and_a_banner():
    r = anim.Result(dict(CARD, rating_from=1089, rating_to=1112, tier='Pro', next_at=1200, band_low=1100, rank_up='Pro'), 0.0)
    t = (r.FLASH_AT + r.FLASH_END) / 2
    assert r.flash(t) == pytest.approx(1) and 0 < r.ring(t) < 1 and r.banner(r.FLASH_AT + .6) == pytest.approx(1, abs=.05)


def test_placement_games_fill_the_bar_by_games_played_and_the_top_rank_is_a_full_bar():
    placing = anim.Result(dict(CARD, tier=None, placing=3, placing_of=5), 0.0)
    assert placing.progress(10) == pytest.approx(.4)
    top = anim.Result(dict(CARD, next_at=None, next_name=None), 0.0)
    assert top.progress(10) == 1.0
    assert anim.Result(dict(CARD, next_at=1000), 0.0).progress(10) == 1.0           # bad data does not divide by zero


@pytest.mark.skipif(sys.platform != 'win32', reason='GDI+ and layered windows are Windows only')
def test_the_windows_drawing_runs_a_chat_and_a_rank_up_card_without_errors():
    from legacy_roster import hud
    from legacy_roster.hud import native
    native.QUIET = True
    try:
        clock = [0.0]
        h = hud.Hud(lambda: (0, 0, 1920, 1080), clock=lambda: clock[0])
        h.start()
        h.chat('Partner', 'gg, good game! ' + 'long ' * 40)
        h.result(dict(CARD, rating_from=1089, rating_to=1112, tier='Pro', next_name='Top 6', next_at=1200, band_low=1100,
                      rank_up='Pro'))
        deadline = time.time() + 5
        while h.frames < 5 and h.error is None and time.time() < deadline:
            clock[0] += .3
            time.sleep(.05)
        h.stop()
    finally:
        native.QUIET = False
    assert h.error is None and h.frames >= 5


def test_the_game_window_is_told_from_rpcs3s_main_window_and_dialogs():
    from legacy_roster import hud
    assert hud.is_game_title('FPS: 59.94 | Vulkan | 0.0.38-18000 | NHL Legacy Edition [BLES02153]')
    assert hud.is_game_title('NHL Legacy Edition [BLUS31540]')
    assert not hud.is_game_title('RPCS3 0.0.38-18000-abcdef Alpha | master')
    assert not hud.is_game_title('Settings') and not hud.is_game_title('')
