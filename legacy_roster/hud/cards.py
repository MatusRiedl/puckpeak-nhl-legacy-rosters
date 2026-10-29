"""What the overlay draws: chat lines and the post-match card. Layout is in 1080p design pixels, scaled by `s`.

Pure drawing on a `native.Gfx` driven by the state objects of `anim` (so each frame is a function of time).
"""
from . import anim
from .native import argb, hexcolor, with_alpha

# Puck Peak's colours (web/css: --gold, --panel-top, --text, --muted, --good)
ACCENT = hexcolor('#f2b933')        # the accent: names, the bar, the card's top line
PANEL = hexcolor('#0d1d33', 236)
PANEL_HI = hexcolor('#13294a', 255)
WHITE = hexcolor('#e8f1fa')
DIM = hexcolor('#9db3c8')
GREEN = hexcolor('#2fa85c')
RED = hexcolor('#d24545')
GOLD = hexcolor('#ffd166')
HEAD = 'Bahnschrift'
BODY = 'Segoe UI Semibold'

CHAT_W, CHAT_LINE, CHAT_GAP, CHAT_MAX = 520, 44, 6, 5
CARD_W, CARD_H, CARD_PAD = 640, 300, 60            # the card and the margin around it (glow, ring, banner)


def chat_size(s):
    return int(CHAT_W * s), int(CHAT_MAX * (CHAT_LINE + CHAT_GAP) * s)


def card_size(s):
    return int((CARD_W + 2 * CARD_PAD) * s), int((CARD_H + 2 * CARD_PAD) * s)


def fit(gfx, text, font, width):
    """`text` cut with an ellipsis so it is at most `width` pixels wide."""
    if gfx.measure(text, font)[0] <= width:
        return text
    while len(text) > 1 and gfx.measure(text + '…', font)[0] > width:
        text = text[:-1]
    return text + '…'


def draw_chat(gfx, lines, now, s):
    gfx.clear()
    name_f, text_f = gfx.font(HEAD, 19 * s, True), gfx.font(BODY, 20 * s)
    n = len(lines)
    for i, t in enumerate(lines):
        k = t.shown(now)
        if k <= 0:
            continue
        slot = n - 1 - i                      # newest at the bottom
        y = (CHAT_MAX - 1 - slot) * (CHAT_LINE + CHAT_GAP) * s
        who = t.who + ' '
        who_w = gfx.measure(who, name_f)[0]
        room = (CHAT_W - 34) * s - who_w
        text = fit(gfx, t.text, text_f, room)
        w = who_w + gfx.measure(text, text_f)[0] + 30 * s
        h = CHAT_LINE * s
        dx = -(1 - k) * (w + 30 * s)
        gfx.fill_round(dx, y, w, h, 5 * s, with_alpha(PANEL, k))
        gfx.fill_rect(dx, y, 4 * s, h, with_alpha(ACCENT, k))
        gfx.text(who, dx + 16 * s, y + 9 * s, name_f, with_alpha(ACCENT, k))
        gfx.text(text, dx + 16 * s + who_w, y + 9 * s, text_f, with_alpha(WHITE, k))


def draw_result(gfx, res, now, s):
    gfx.clear()
    d = res.d
    ox = oy = CARD_PAD * s
    w, h = CARD_W * s, CARD_H * s
    lift = res.lift(now) * s
    flash = res.flash(now)
    gfx.glow(ox, oy + lift, w, h, 8 * s, ACCENT, 26 * s)
    gfx.fill_round(ox, oy + lift, w, h, 6 * s, PANEL)
    gfx.fill_rect(ox, oy + lift, w, 5 * s, ACCENT)
    x0, y0 = ox + 34 * s, oy + lift

    title_f, num_f = gfx.font(HEAD, 18 * s, True), gfx.font(HEAD, 112 * s, True)
    tier_f, small_f = gfx.font(HEAD, 30 * s, True), gfx.font(BODY, 19 * s)
    gfx.text(d.get('title', 'FINAL').upper(), x0, y0 + 24 * s, title_f, ACCENT)
    sub = d.get('sub', '')
    if sub:
        gfx.text(sub.upper(), x0 + gfx.measure(d.get('title', 'FINAL').upper() + '   ', title_f)[0], y0 + 24 * s, title_f, WHITE)

    rating = int(round(res.rating(now)))
    num = str(rating)
    gfx.text(num, x0 - 4 * s, y0 + 50 * s, num_f, WHITE)
    num_w = gfx.measure(num, num_f)[0]

    delta = d['rating_to'] - d['rating_from']
    chip = res.chip(now)
    if chip > 0.01:
        cw, ch = 118 * s, 52 * s
        cx, cy = x0 + num_w + 18 * s, y0 + 126 * s
        gfx.push(cx + cw / 2, cy + ch / 2, chip, chip)
        gfx.fill_round(-cw / 2, -ch / 2, cw, ch, 5 * s, GREEN if delta >= 0 else RED)
        gfx.text(f'{delta:+d}', -cw / 2, -ch / 2 + 6 * s, gfx.font(HEAD, 34 * s, True), WHITE, w=cw, align=1)
        gfx.pop()

    tier = d.get('tier') or ('Placement' if d.get('placing') else '')
    gfx.text(tier, x0, y0 + 190 * s, tier_f, WHITE if d.get('tier') else DIM)
    nxt = d.get('next_name')
    if d.get('placing'):
        n = d['placing']
        gfx.text(f"{n} more rated game{'s' if n != 1 else ''} for a rank", x0, y0 + 195 * s, small_f, DIM, w=w - 68 * s, align=2)
    elif nxt:
        to_go = max(0, int(d['next_at'] - rating))
        gfx.text(f'{to_go} to {nxt}', x0, y0 + 195 * s, small_f, DIM, w=w - 68 * s, align=2)

    bx, by, bw, bh = x0, y0 + 244 * s, w - 68 * s, 12 * s
    gfx.fill_round(bx, by, bw, bh, bh / 2, hexcolor('#ffffff', 40))
    p = res.progress(now)
    if p > 0.004:
        fw = max(bh, bw * p)
        gfx.fill_round(bx, by, fw, bh, bh / 2, ACCENT)
        gfx.radial(bx + fw, by + bh / 2, 22 * s, hexcolor('#ffe08f', 150))
    if d.get('band_low') is not None and nxt:
        gfx.text(str(d['band_low']), bx, by + 18 * s, gfx.font(BODY, 15 * s), DIM)
        gfx.text(str(d['next_at']), bx, by + 18 * s, gfx.font(BODY, 15 * s), DIM, w=bw, align=2)

    if flash > 0:
        gfx.fill_round(ox, oy + lift, w, h, 6 * s, hexcolor('#ffffff', int(120 * flash)))
    ring = res.ring(now)
    if 0 < ring < 1:
        e = anim.out_cubic(ring)
        gfx.ring(x0 + num_w / 2, y0 + 122 * s, (30 + 260 * e) * s, 5 * s * (1 - e) + 1, hexcolor('#ffd166', int(230 * (1 - e))))
    b = res.banner(now)
    if b > 0.01:
        bh2 = 50 * s                                    # above the card, in its margin: the title line stays readable
        by2 = oy + lift - bh2 - 4 * s + (b - 1) * 40 * s
        gfx.push(ox + w / 2, by2 + bh2 / 2, 1.0, max(0.01, min(1.0, b)))
        gfx.fill_round(-w / 2, -bh2 / 2, w, bh2, 5 * s, GOLD)
        gfx.text('RANK UP  •  ' + str(d['rank_up']).upper(), -w / 2, -bh2 / 2 + 6 * s, gfx.font(HEAD, 29 * s, True),
                 hexcolor('#1a1204'), w=w, align=1)
        gfx.pop()
