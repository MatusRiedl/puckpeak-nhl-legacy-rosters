"""Demo: `python -m legacy_roster.hud [--seconds 16] [--rank-up] [--loss]`: two chat lines, then a post-match card over
RPCS3's game window when one is open, else over the main screen."""
import argparse
import time

from . import Hud, emulator_rect, screen_rect


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=16)
    ap.add_argument('--rank-up', action='store_true')
    ap.add_argument('--loss', action='store_true')
    a = ap.parse_args(argv)
    ov = Hud(lambda: emulator_rect() or screen_rect())
    ov.start()
    time.sleep(0.5)
    ov.chat('Partner', 'gg, good game!')
    time.sleep(1.2)
    ov.chat('Partner', 'rematch? I will switch to the Leafs')
    time.sleep(1.6)
    if a.rank_up:
        data = dict(title='Final', sub='4 - 2 win', rating_from=1089, rating_to=1112, tier='Pro', next_name='Top 6',
                    next_at=1200, band_low=1100, rank_up='Pro')
    elif a.loss:
        data = dict(title='Final', sub='1 - 3 loss', rating_from=1067, rating_to=1049, tier='Rookie', next_name='Pro',
                    next_at=1100, band_low=1000)
    else:
        data = dict(title='Final', sub='4 - 2 win', rating_from=1044, rating_to=1067, tier='Rookie', next_name='Pro',
                    next_at=1100, band_low=1000)
    ov.result(data)
    time.sleep(a.seconds)
    ov.stop()
    print('frames', ov.frames, 'error', ov.error)


if __name__ == '__main__':
    main()
