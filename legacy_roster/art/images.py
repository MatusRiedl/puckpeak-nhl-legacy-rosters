"""Turning downloaded photos and logos into the pictures the game's menus show (needs Pillow).

This is the one engine module that uses Pillow; it is imported only when photos and logos are
switched on. Everything here works on Pillow images and returns Pillow images; dds.py and
bigf.py turn them into art files.

Portraits: the game's own portraits are cut-outs (head and shoulders on a transparent
background) placed at the same spot of a 512 x 512 canvas (top half) and of a 256 x 128 one.
`portrait()` finds the head in a photo -- the top of the hair, the middle of the head and its
width -- and scales and moves it to where the game's own portraits have it (measured on the disc:
PORTRAIT_SPOTS). Studio photos get their backdrop removed first; a mottled backdrop that cannot be
removed cleanly is faded out in a soft oval around the head instead (`prepare()`).

Logos: one clean logo becomes the five pictures the menus use (plain, small banner, wide
watermark, calendar, dynasty), drawn in the style of the game's own.
"""
from PIL import Image, ImageChops, ImageDraw, ImageFilter

# where the head sits in the game's own portraits (medians of head() over the disc's portraits):
# canvas size -> (top of the hair, middle of the head x, head width, last row with picture)
PORTRAIT_SPOTS = {(512, 512): (26, 235, 144, 247), (512, 256): (16, 233, 145, 242),
                  (256, 128): (13, 101, 74, 127)}
FADE = {(512, 512): 26, (512, 256): 26, (256, 128): 0}     # rows the shoulders fade out over


def _rows(alpha):
    """[(opaque pixels, their mean x)] per row of an alpha channel (pixels more than half
    opaque). Counting pixels, not the span, keeps a speck of leftover background from counting."""
    w, h = alpha.size
    data = alpha.tobytes()
    out = []
    for y in range(h):
        xs = [x for x, v in enumerate(data[y * w:(y + 1) * w]) if v > 128]
        out.append((len(xs), sum(xs) / len(xs) if xs else 0))
    return out


def head(alpha):
    """(top, centre x, width) of the head in a cut-out's alpha channel, or None.

    Going down from the top of the hair the outline widens to the ears; the head's width is its
    widest row before the jaw (the shoulders, far wider, come later). The width is the steadiest
    measure of a head's size on the game's own portraits (it varies 8 % between players)."""
    rows = _rows(alpha)
    w = alpha.size[0]
    top = next((y for y, (n, _x) in enumerate(rows) if n > max(3, w // 50)), None)
    if top is None:
        return None
    widest, centre = 0, None
    y = top
    while y < len(rows) and (widest == 0 or y < top + 0.8 * widest):
        n, x = rows[y]
        if n > widest:
            widest, centre = n, x
        y += 1
    return (top, centre, widest) if widest > w // 20 else None


def _keep_player(mask):
    """Only the part of a mask that hangs together with the player (who stands on the bottom
    edge, in the middle); loose islands of background go."""
    w, h = mask.size
    row = mask.crop((0, h - 1, w, h)).tobytes()
    seeds = [x for x in sorted(range(w), key=lambda x: abs(x - w // 2)) if row[x] == 255]
    if not seeds:
        return mask
    marked = mask.copy()
    ImageDraw.floodfill(marked, (seeds[0], h - 1), 128)
    return marked.point(lambda v: 255 if v == 128 else 0)


def _edge_pixels(rgb):
    """The colours along the top edge and down both sides to 70 % of the height."""
    w, h = rgb.size
    px = rgb.load()
    return ([px[x, 0] for x in range(0, w, 2)] + [px[0, y] for y in range(0, h * 7 // 10, 2)]
            + [px[w - 1, y] for y in range(0, h * 7 // 10, 2)])


def _runs(row, at_least=3):
    """How many separate stretches of opaque pixels a row of an alpha mask has."""
    count, length = 0, 0
    for v in row:
        if v > 128:
            length += 1
        else:
            count += length >= at_least
            length = 0
    return count + (length >= at_least)


def _clean(mask, found):
    """Does a background-removed mask look like one person: the head near the top, a plausible
    size, and down to the shoulders every row one stretch, with no islands of backdrop beside it?"""
    w, h = mask.size
    if not _plausible(found, w, h):
        return False
    data = mask.tobytes()
    rows = [data[y * w:(y + 1) * w] for y in range(found[0], min(h, found[0] + int(1.3 * found[2])))]
    busy = sum(1 for r in rows if _runs(r) > 1)
    return busy <= 0.08 * len(rows)


def _plausible(found, w, h):
    """A head (top, centre, width) where a portrait photo has one: near the top, middle third."""
    return bool(found) and found[0] < 0.25 * h and w / 3 < found[1] < 2 * w / 3 and 0.08 * w < found[2] < 0.75 * w


def _background_mask(rgb):
    """(mask of the player, its head) for a studio photo: flood fill from the edges, as tolerant as
    the backdrop is uneven. None when the fill took most or nothing of the picture."""
    w, h = rgb.size
    edge = _edge_pixels(rgb)
    spread = sum((sum((c[k] - sum(e[k] for e in edge) / len(edge)) ** 2 for c in edge) / len(edge)) ** 0.5
                 for k in range(3)) / 3
    marker = (255, 0, 255)
    work = rgb.copy()
    # start from the top edge and the upper sides, only where the colour is the backdrop's: a
    # shoulder touching the side of the picture must not be filled away
    top_row = sorted(rgb.getpixel((x, 0)) for x in range(w))
    backdrop = top_row[len(top_row) // 2]
    like_backdrop = lambda c: sum(abs(a - b) for a, b in zip(c, backdrop)) < 90
    seeds = [(x, 0) for x in range(0, w, max(1, w // 16))] + \
        [(x, y) for x in (0, w - 1) for y in range(0, h * 2 // 5, max(1, h // 16))]
    for s in seeds:
        if work.getpixel(s) != marker and like_backdrop(rgb.getpixel(s)):
            ImageDraw.floodfill(work, s, marker, thresh=int(min(60, max(24, 2.5 * spread + 12))))
    diff = ImageChops.difference(work, Image.new('RGB', (w, h), marker)).convert('L')
    mask = diff.point(lambda v: 255 if v > 0 else 0)
    share = sum(mask.histogram()[255:]) / (w * h)
    if not 0.2 < share < 0.9:
        return None
    # specks of background the fill missed go (opening), and islands not joined to the player
    k = max(3, (min(w, h) // 60) | 1)
    mask = _keep_player(mask.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k)))
    return mask, head(mask)


# where the head usually is in a league's square headshot, as shares of the picture:
# (top of the hair, middle, head width); used when the backdrop cannot be removed
HEADSHOT = (0.05, 0.5, 0.47)


def prepare(photo):
    """(RGBA picture, (top, centre x, width) of the head) for a photo, or None.

    A photo with real transparency is used as it is; a studio photo gets its backdrop removed. When
    the backdrop cannot be removed cleanly, the photo is shown in a soft oval around the head
    instead, around the head the fill found if it is a plausible one, else where league headshots
    usually have it (HEADSHOT)."""
    img = photo.convert('RGBA')
    if img.getchannel('A').getextrema()[0] < 200:          # already a cut-out
        found = head(img.getchannel('A'))
        return (img, found) if found else None
    w, h = img.size
    cut = _background_mask(img.convert('RGB'))
    if cut is not None and _clean(*cut):
        img.putalpha(cut[0].filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2)))
        return img, cut[1]
    if cut is not None and _plausible(cut[1], w, h):
        top, cx, width = cut[1]
    else:
        top, cx, width = HEADSHOT[0] * h, HEADSHOT[1] * w, HEADSHOT[2] * w
    oval = Image.new('L', (w, h), 0)
    ImageDraw.Draw(oval).ellipse((cx - 1.05 * width, top - 0.3 * width, cx + 1.05 * width, top + 3.2 * width), fill=255)
    edges = Image.new('L', (w, h), 0)                      # the photo's own edges fade out too
    ImageDraw.Draw(edges).rectangle((w * 0.05, h * 0.04, w * 0.95, h * 1.2), fill=255)
    img.putalpha(ImageChops.multiply(oval.filter(ImageFilter.GaussianBlur(width / 7)),
                                     edges.filter(ImageFilter.GaussianBlur(w * 0.03))))
    return img, (top, cx, width)


def cut_out(photo):
    """The RGBA picture `prepare()` makes of a photo (transparent around the player)."""
    prepared = prepare(photo)
    return prepared[0] if prepared else photo.convert('RGBA')


def portrait(photo, size):
    """The game's portrait picture (RGBA, `size`) made from a photo (None if no head is found)."""
    top, cx, width, last = PORTRAIT_SPOTS[size]
    prepared = prepare(photo)
    if prepared is None:
        return None
    src, (s_top, s_cx, s_width) = prepared
    scale = width / s_width
    scaled = src.resize((max(1, round(src.width * scale)), max(1, round(src.height * scale))), Image.LANCZOS)
    canvas = Image.new('RGBA', size, (0, 0, 0, 0))
    dx, dy = round(cx - s_cx * scale), round(top - s_top * scale)
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    layer.paste(scaled, (dx, dy))
    # nothing below the last row; the shoulders fade out over the rows above it
    fade = FADE[size]
    ramp = Image.new('L', size, 255)
    draw = ImageDraw.Draw(ramp)
    for y in range(last + 1 - fade, size[1]):
        v = 0 if y > last else int(255 * (last + 1 - y) / (fade + 1)) if fade else 255
        draw.line(((0, y), (size[0], y)), fill=v)
    layer.putalpha(ImageChops.multiply(layer.getchannel('A'), ramp))
    canvas.alpha_composite(layer)
    return canvas


# --- logos -------------------------------------------------------------------------------------
def _trim(img):
    """The logo alone: a plain backdrop (some clubs publish their logo on white) made transparent
    by filling from the corners, then cropped to what is left."""
    img = img.convert('RGBA')
    if img.getchannel('A').getextrema()[0] >= 200:
        w, h = img.size
        marker = (255, 0, 255)
        work = img.convert('RGB')
        for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
            if work.getpixel(corner) != marker:
                ImageDraw.floodfill(work, corner, marker, thresh=24)
        keep = ImageChops.difference(work, Image.new('RGB', (w, h), marker)).convert('L').point(
            lambda v: 255 if v > 0 else 0)
        if 0.05 < sum(keep.histogram()[255:]) / (w * h) < 0.98:
            img.putalpha(keep.filter(ImageFilter.GaussianBlur(0.8)))
    box = img.getchannel('A').getbbox()
    return img.crop(box) if box else img


def _fit(img, box_w, box_h):
    scale = min(box_w / img.width, box_h / img.height)
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)


def _outlined(img, width, colour=(255, 255, 255)):
    """The logo on a soft outline of `colour` (the game's logos have a white edge and a shadow)."""
    pad = width * 3
    base = Image.new('RGBA', (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
    base.paste(img, (pad, pad))
    alpha = base.getchannel('A')
    shadow = alpha.filter(ImageFilter.MaxFilter(width * 2 + 1)).filter(ImageFilter.GaussianBlur(width))
    edge = alpha.filter(ImageFilter.MaxFilter(width * 2 - 1 if width > 1 else 3))
    out = Image.new('RGBA', base.size, (0, 0, 0, 0))
    out.alpha_composite(Image.merge('RGBA', (*Image.new('RGB', base.size, (0, 0, 0)).split(),
                                             shadow.point(lambda v: v * 0.45))), (width // 2, width))
    out.alpha_composite(Image.merge('RGBA', (*Image.new('RGB', base.size, colour).split(), edge)))
    out.alpha_composite(base)
    return out


def _centred(img, size, scale=1.0, at=(0.5, 0.5)):
    """`img` fitted into `scale` times `size`, its middle at `at` (parts outside are cut off)."""
    canvas = Image.new('RGBA', size, (0, 0, 0, 0))
    fitted = _fit(img, size[0] * scale, size[1] * scale)
    canvas.paste(fitted, (round(size[0] * at[0] - fitted.width / 2), round(size[1] * at[1] - fitted.height / 2)))
    return canvas


def _round(size, inset=0.12, soft=0.12):
    """An alpha mask: a circle filling the picture (less `inset` at each side), edge blurred over
    `soft` of the width, clear in the corners."""
    w, h = size
    mask = Image.new('L', size, 0)
    ImageDraw.Draw(mask).ellipse((w * inset, h * inset, w * (1 - inset), h * (1 - inset)), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(w * soft))


def badge(text, colours=((20, 60, 110), (200, 210, 220)), size=512):
    """A plain round badge with `text` (a draft class's year) for teams that have no logo."""
    from PIL import ImageFont
    inner, ring = colours if colours and colours[0] != colours[1] else ((20, 60, 110), (200, 210, 220))
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, size - 8, size - 8), fill=tuple(ring) + (255,))
    d.ellipse((size * 0.07, size * 0.07, size * 0.93, size * 0.93), fill=tuple(inner) + (255,))
    try:
        font = ImageFont.load_default(size=int(size * 0.32))
    except TypeError:                                   # Pillow before 10.1: the small bitmap font
        font = ImageFont.load_default()
    box = d.textbbox((0, 0), text, font=font)
    d.text(((size - (box[2] - box[0])) / 2 - box[0], (size - (box[3] - box[1])) / 2 - box[1]), text,
           font=font, fill=(255, 255, 255, 255))
    return img


def _reflected(img, size):
    """The favourite-team picture (kind 'r', NHL teams only): the logo in the upper half, standing
    on a faint mirror image of itself, as on the disc (logo about 190 x 180 pixels around y 125,
    the reflection under it fading out within about 50 pixels)."""
    w, h = size
    mark = _outlined(_fit(img, w * 0.72, h * 0.3), max(2, w // 64))
    mark = mark.crop(mark.getchannel('A').getbbox() or (0, 0, mark.width, mark.height))
    canvas = Image.new('RGBA', size, (0, 0, 0, 0))
    x, y = round((w - mark.width) / 2), round(h * 0.245 - mark.height / 2)
    canvas.alpha_composite(mark, (x, max(0, y)))
    bottom = max(0, y) + mark.height
    fade_h = max(1, round(h * 0.11))
    mirror = mark.transpose(Image.FLIP_TOP_BOTTOM).crop((0, 0, mark.width, min(mark.height, fade_h)))
    fade = Image.linear_gradient('L').resize((mirror.width, mirror.height)).point(lambda v: round((255 - v) * 0.3))
    mirror.putalpha(ImageChops.multiply(mirror.getchannel('A'), fade))
    if bottom < h:
        canvas.alpha_composite(mirror, (x, bottom), (0, 0, mirror.width, min(mirror.height, h - bottom)))
    return canvas


def logo(img, kind, size, colours=((60, 60, 60), (20, 20, 20))):
    """One of the game's logo pictures: kind 't' plain, 'd' dynasty, 'c' calendar, 'w' wide
    watermark, 's' small banner (in the team's colours), 'r' with a reflection (favourite team)."""
    clean = _trim(img)
    if kind == 'r':
        return _reflected(clean, size)
    if kind == 't':
        return _centred(_outlined(_fit(clean, size[0] * 0.78, size[1] * 0.78), max(2, size[0] // 64)), size, 0.94)
    if kind == 'd':
        return _centred(_outlined(_fit(clean, size[0] * 0.8, size[1] * 0.8), 2), size, 0.96)
    if kind == 'c':
        out = _centred(clean, size, 1.25, (0.42, 0.5))
        fade = Image.linear_gradient('L').rotate(90).resize(size)  # clear on the right
        out.putalpha(ImageChops.multiply(out.getchannel('A'), fade.point(lambda v: min(255, 80 + v))))
        return out
    if kind == 'w':
        out = _centred(clean, size, 2.2, (0.45, 0.5))
        out.putalpha(ImageChops.multiply(out.getchannel('A'), _round(size)))
        return out
    if kind == 's':
        w, h = size
        top, bottom = colours
        band = Image.new('RGBA', size, (0, 0, 0, 0))
        grad = Image.linear_gradient('L').resize(size)
        band = Image.composite(Image.new('RGBA', size, bottom + (255,)), Image.new('RGBA', size, top + (255,)), grad)
        mask = Image.new('L', size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((1, 1, w - 2, h - 2), radius=h // 6, fill=230)
        band.putalpha(mask)
        mark = _fit(clean, w * 0.9, h * 1.6)
        layer = Image.new('RGBA', size, (0, 0, 0, 0))
        layer.paste(mark, (w - mark.width + w // 10, (h - mark.height) // 2))
        layer.putalpha(ImageChops.multiply(layer.getchannel('A'), mask))
        band.alpha_composite(layer)
        return band
    raise ValueError(f"unknown logo kind {kind}")
