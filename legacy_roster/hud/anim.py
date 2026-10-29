"""Easing and timeline helpers for the in-game overlay. Pure functions of time: no Windows, no drawing (unit-tested)."""
import math


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def lerp(a, b, k):
    return a + (b - a) * k


def span(t, start, end):
    """0..1 progress of `t` through [start, end]; 0 before, 1 after."""
    return 0.0 if end <= start else clamp((t - start) / (end - start))


def out_cubic(k):
    return 1 - (1 - k) ** 3


def in_cubic(k):
    return k ** 3


def in_out_cubic(k):
    return 4 * k ** 3 if k < .5 else 1 - (-2 * k + 2) ** 3 / 2


def out_back(k, s=1.9):
    k -= 1
    return 1 + (s + 1) * k ** 3 + s * k ** 2


def out_elastic(k):
    if k <= 0 or k >= 1:
        return clamp(k)
    return 2 ** (-9 * k) * math.sin((k * 10 - .75) * (2 * math.pi) / 3) + 1


def pulse(k):
    """0 -> 1 -> 0 over k in 0..1 (a flash)."""
    return math.sin(clamp(k) * math.pi)


class Toast:
    """A chat line: slides in, waits, slides out. `shown(now)` is 0..1 (how far in), `done(now)` when gone."""
    IN, OUT = .35, .45

    def __init__(self, who, text, now, hold=6.0):
        self.who, self.text, self.t0, self.hold = who, text, now, hold

    def shown(self, now):
        t = now - self.t0
        if t < self.IN:
            return out_cubic(span(t, 0, self.IN))
        out_start = self.IN + self.hold
        return 1 - in_cubic(span(t, out_start, out_start + self.OUT))

    def done(self, now):
        return now - self.t0 > self.IN + self.hold + self.OUT


class Chat:
    """The visible chat lines, newest at the bottom; at most `limit`, an older one leaves early when a new one needs the room."""

    def __init__(self, limit=5):
        self.limit, self.lines = limit, []

    def add(self, who, text, now, hold=6.0):
        self.lines.append(Toast(who, str(text)[:140], now, hold))
        for old in self.lines[:-self.limit]:
            old.hold = min(old.hold, max(0.0, now - old.t0 - Toast.IN))   # starts leaving now
        self.tick(now)

    def tick(self, now):
        self.lines = [t for t in self.lines if not t.done(now)]
        return self.lines


class Result:
    """The post-match card: enter, the rating counts up while the bar fills, the +/- chip pops, a rank-up gets a flash.

    `data` = {title, sub, rating_from, rating_to, tier, next_name, next_at, band_low, rank_up (name | None), rank, of}
    """
    ENTER, COUNT_AT, COUNT_END, CHIP_AT, FLASH_AT, FLASH_END, EXIT = .55, .75, 2.2, 1.9, 2.3, 3.2, .6

    def __init__(self, data, now, hold=9.0):
        self.d, self.t0, self.hold = dict(data), now, hold

    def t(self, now):
        return now - self.t0

    def done(self, now):
        return self.t(now) > self.hold + self.EXIT

    def alpha(self, now):
        t = self.t(now)
        if t > self.hold:
            return 1 - span(t, self.hold, self.hold + self.EXIT)
        return span(t, 0, self.ENTER)

    def lift(self, now):
        """Pixels (at 1080p) the card still has to rise."""
        return 40 * (1 - out_cubic(span(self.t(now), 0, self.ENTER)))

    def rating(self, now):
        k = out_cubic(span(self.t(now), self.COUNT_AT, self.COUNT_END))
        return lerp(self.d['rating_from'], self.d['rating_to'], k)

    def progress(self, now):
        """The bar's fill 0..1 in the current band, following the count (a rank-up wraps through full)."""
        d = self.d
        if d.get('placing'):             # unranked: the bar counts the placement games played
            total = d.get('placing_of', 5)
            return clamp((total - d['placing']) / total) * out_cubic(span(self.t(now), self.COUNT_AT, self.COUNT_END))
        low, nxt = d.get('band_low', 0), d.get('next_at')
        if not nxt or nxt <= low:
            return 1.0
        r = self.rating(now)
        return clamp((r - low) / (nxt - low))

    def chip(self, now):
        """Scale of the +/- chip, with an overshoot."""
        return out_back(span(self.t(now), self.CHIP_AT, self.CHIP_AT + .45))

    def flash(self, now):
        return pulse(span(self.t(now), self.FLASH_AT, self.FLASH_END)) if self.d.get('rank_up') else 0.0

    def ring(self, now):
        """0..1 radius progress of the rank-up ring, 0 when there is none."""
        return span(self.t(now), self.FLASH_AT, self.FLASH_END + .6) if self.d.get('rank_up') else 0.0

    def banner(self, now):
        """The 'RANK UP' strip: 0..1 how far in."""
        if not self.d.get('rank_up'):
            return 0.0
        return out_back(span(self.t(now), self.FLASH_AT, self.FLASH_AT + .5))
