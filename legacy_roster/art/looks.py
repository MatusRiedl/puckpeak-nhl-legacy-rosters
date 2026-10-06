"""The look of a team in the game's 3D world: jerseys, pants, socks, number sheets, the menu pictures of the jerseys
and the centre-ice logo (needs Pillow, imported when a picture is made; the engine's other modules never need it).

Why this exists (owner, 2026-10-06): Arizona is Utah now and slots 30 and 31 are still the All-Star teams, so their
jerseys and ice show the wrong team. The game takes every 3D texture from a loose file under
`<game folder>/rendering/...` before its disc (proven by `cli rendering-test`; RPCS3's log names the files Play Now
opens: style 1, variants 3 and 4 for Utah, and `centerlogo_22_cm`).

How a jersey is made. Every standard jersey of style 1 is painted on one shared shirt layout (the normal maps of Utah's,
Seattle's, Vegas's, Edmonton's and Vancouver's jerseys agree to 96-100 %). Utah's own style-1 jersey (variant 3 dark,
variant 4 light) is a flat three-colour design: a body colour, a yoke colour and a trim colour, with the crest and two
shoulder marks on top. `recolour()` swaps those three colours for the team's (keeping the cloth's shading), the crest and
shoulder marks are painted over with the team's own logo, and the result goes into the team's own file: every raster
keeps the size the disc's file has, so the file keeps its layout. Pants, socks and the number sheet go the same way.
Nothing of the game's is shipped: the chassis is read from the player's own disc each time (AGENTS rule 10).

Not every version of a team uses that layout: the old All-Star versions (Seattle and Vegas 0 and 1) and style 0 are
painted on other shirts. Those are left as they are (`STANDARD_LAYOUT`).
"""
import hashlib
import json
import math
import os
from collections import namedtuple

from . import rpsgl

STYLE = 1
CHASSIS_ART = 22                   # Utah's (Arizona's) own files are the chassis
CHASSIS = {False: 3, True: 4}      # dark and light variant of the chassis
JERSEY = "rendering/jersey/texlib_{s}_{a}_{v}.rpsgl"
PANT = "rendering/pant/texlib_{s}_{a}_{v}.rpsgl"
SOCK = "rendering/sock/sock_{s}_{a}_{v}_cm.rpsgl"
CENTRE = "rendering/icesurface/centerlogo_{a}_cm.rpsgl"
PREVIEW = "fe/ion/artassets/jerseys/jersey_{s}_{a}_{v}.big"
FONT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'fonts', 'SourceSans3-Bold.ttf')

# version -> does it use the shared shirt layout? (nm-map correlation with Utah's, tools/look_preview.py --layouts)
STANDARD_LAYOUT = {22: {1: (0, 1, 3, 4)}, 30: {1: (2, 3, 4, 5)}, 31: {1: (2, 3, 4, 5)}}

# the flat colours of the chassis (RGB, measured on the disc's jersey colour maps) and where its crest and marks sit
MASTERS = ((130, 17, 19), (27, 27, 27), (234, 234, 234))         # body, yoke, trim of Utah's style-1 jerseys
CREST = (405, 640, 612, 880)                                      # the box the old crest is painted out of (1024 x 1024)
SHOULDER = ((345, 452, 430, 535), (592, 452, 686, 535))           # the old shoulder marks, left and right
NORMAL_FLAT = (CREST, (335, 445, 440, 540), (585, 445, 695, 540)) # parts of the normal map that carry the old relief

# the colours of a kit: what the chassis' body, yoke and trim colours become (jerseys and socks), what its black
# pants become, and what the number sheet's three colours (digits, outline, small digits' outline) become
Palette = namedtuple('Palette', 'body yoke trim pants font')
Kit = namedtuple('Kit', 'home away')
WHITE = (240, 240, 240)


def kit_for(primary, secondary):
    """A home (dark) and an away (light) kit from a team's two colours (the roster's). Dark: the second colour all
    over, the first as cuffs, stripes and digits. Light: white with the first colour's bands and the second colour's
    sleeves and digits."""
    return Kit(home=Palette(secondary, secondary, primary, secondary, (secondary, secondary, primary)),
               away=Palette(primary, secondary, WHITE, secondary, (secondary, secondary, WHITE)))


def _dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _clamp(v):
    return 0 if v < 0 else 255 if v > 255 else int(round(v))


def refine(img, seeds, tol=40):
    """The real colour of each seed: the mean of the picture's pixels within `tol` of it."""
    colours = img.convert('RGB').getcolors(1 << 22) or []
    out = []
    for seed in seeds:
        n = [0, 0, 0, 0]
        for count, c in colours:
            if _dist2(c, seed) <= tol * tol:
                n[0] += count
                for i in range(3):
                    n[i + 1] += count * c[i]
        out.append(tuple(n[i + 1] / n[0] for i in range(3)) if n[0] else tuple(seed))
    return tuple(out)


def _mapper(masters, targets, tol, shade):
    """A function: one colour of the chassis -> the team's colour (flat parts keep the cloth's shading; a blend of two
    chassis colours (an edge) becomes the same blend of the team's; a colour that is none of them stays)."""
    pairs = [(a, b) for a in range(len(masters)) for b in range(a + 1, len(masters))]

    def lum(c):
        return 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2] + 1.0

    def one(c):
        k = min(range(len(masters)), key=lambda i: _dist2(c, masters[i]))
        if _dist2(c, masters[k]) <= tol * tol:
            m, t = masters[k], targets[k]
            if shade == 'mul':
                f = lum(c) / lum(m)
                return tuple(_clamp(t[i] * f) for i in range(3))
            return tuple(_clamp(t[i] + c[i] - m[i]) for i in range(3))
        best = None
        for a, b in pairs:
            ma, mb = masters[a], masters[b]
            d = [mb[i] - ma[i] for i in range(3)]
            n = sum(x * x for x in d) or 1
            t = max(0.0, min(1.0, sum((c[i] - ma[i]) * d[i] for i in range(3)) / n))
            p = tuple(ma[i] + t * d[i] for i in range(3))
            r = _dist2(c, p)
            if best is None or r < best[0]:
                best = (r, a, b, t, p)
        r, a, b, t, p = best
        if r > (tol * 1.3) ** 2:
            return c
        return tuple(_clamp(targets[a][i] + t * (targets[b][i] - targets[a][i]) + c[i] - p[i]) for i in range(3))
    return one


def recolour(img, masters, targets, tol=40, shade='add'):
    """`img` with the `masters` colours replaced by `targets` (see _mapper). The alpha channel stays as it is."""
    from PIL import Image
    rgba = img.convert('RGBA')
    rgb = rgba.convert('RGB')
    one = _mapper(masters, targets, tol, shade)
    lut = {c: one(c) for _n, c in (rgb.getcolors(1 << 22) or [])}
    raw = rgb.tobytes()
    data = [lut[(raw[i], raw[i + 1], raw[i + 2])] for i in range(0, len(raw), 3)]
    out = Image.new('RGB', rgb.size)
    out.putdata(data)
    out.putalpha(rgba.getchannel('A'))
    return out


def _ring_colour(img, box, margin=6):
    """The colour just outside `box` (the median of a thin ring around it): the cloth the old crest sat on."""
    l, t, r, b = box
    px = img.convert('RGB').load()
    seen = []
    for x in range(l, r, 4):
        seen += [px[x, max(0, t - margin)], px[x, min(img.height - 1, b + margin)]]
    for y in range(t, b, 4):
        seen += [px[max(0, l - margin), y], px[min(img.width - 1, r + margin), y]]
    return tuple(sorted(c[i] for c in seen)[len(seen) // 2] for i in range(3))


def _fill(img, box):
    """`box` of `img` painted over with the cloth colour around it."""
    from PIL import Image
    img.paste(Image.new('RGB', (box[2] - box[0], box[3] - box[1]), _ring_colour(img, box)), box[:2])


def _paste_mark(img, mark, box, turns=0):
    """The logo `mark` fitted into `box` (centred), turned a quarter turn `turns` times counter-clockwise."""
    from PIL import Image
    if turns:
        mark = mark.rotate(90 * turns, expand=True)
    scale = min((box[2] - box[0]) / mark.width, (box[3] - box[1]) / mark.height)
    mark = mark.resize((max(1, round(mark.width * scale)), max(1, round(mark.height * scale))), Image.LANCZOS)
    x, y = (box[0] + box[2] - mark.width) // 2, (box[1] + box[3] - mark.height) // 2
    layer = img.convert('RGBA')
    layer.alpha_composite(mark.convert('RGBA'), (x, y))
    img.paste(layer.convert('RGB'), (0, 0))


def jersey_colour(chassis_cm, palette, logo):
    """The colour map of a jersey (1024 x 1024): the chassis in the team's colours with the team's crest and marks."""
    out = recolour(chassis_cm, MASTERS, (palette.body, palette.yoke, palette.trim)).convert('RGB')
    _fill(out, CREST)
    for box in SHOULDER:
        _fill(out, box)
    if logo is not None:
        _paste_mark(out, logo, (418, 652, 600, 868))
        _paste_mark(out, logo, SHOULDER[0][:2] + (SHOULDER[0][2] - 4, SHOULDER[0][3] - 4), turns=1)
        _paste_mark(out, logo, (SHOULDER[1][0] + 4,) + SHOULDER[1][1:], turns=-1)
    return out


def flatten(img, boxes):
    """The normal map with the relief of the old crest and marks taken out: each box takes the mean of its own ring."""
    from PIL import Image
    out = img.convert('RGBA')
    px = out.load()
    for l, t, r, b in boxes:
        ring = [px[x, y] for x in range(l - 6, r + 6, 3) for y in (t - 6, b + 6)] + \
               [px[x, y] for y in range(t, b, 3) for x in (l - 6, r + 6)]
        mean = tuple(round(sum(c[i] for c in ring) / len(ring)) for i in range(4))
        out.paste(Image.new('RGBA', (r - l, b - t), mean), (l, t))
    return out


def _digest(*parts):
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=list).encode()).hexdigest()[:12]


# --- the menu pictures of the jerseys ------------------------------------------------------------------------------
# `fe/ion/artassets/jerseys/jersey_<style>_<art>_<variant>.big` holds a 256 x 256 render of the jersey on a transparent
# ground (the same shirt, light and pose for every team, so the shirt is the part that differs from team to team).
PREVIEW_TEAMS = tuple(range(0, 30))


def preview_picture(art_file):
    """A menu preview (bytes of its .big) as a Pillow picture."""
    from PIL import Image
    from . import bigf, dds
    width, height, pixels = dds.read(bigf.ArtFile(art_file).image())
    img = Image.new('RGBA', (width, height))
    img.putdata([p for row in pixels for p in row])
    return img


def shirt_mask(disc, own, styles=(STYLE,)):
    """Where the shirt is in a menu preview: the pixels that differ between teams (the head, the gloves and the rest are
    the same in every preview). `own` are previews of the chassis. Returns a Pillow 'L' picture."""
    from PIL import Image, ImageChops, ImageFilter
    mask = Image.new('L', own[0].size, 0)
    for art in PREVIEW_TEAMS:
        for v in (0, 1, 2, 3, 4):
            raw = disc.find(PREVIEW.format(s=STYLE, a=art, v=v))
            if raw is None:
                continue
            other = preview_picture(raw).convert('RGB')
            if other.size != mask.size:
                continue
            for ref in own:
                diff = ImageChops.difference(ref.convert('RGB'), other).convert('L').point(lambda x: 255 if x > 28 else 0)
                mask = ImageChops.lighter(mask, diff)
    return mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))


def _classes(c):
    """How much a shaded colour of the preview belongs to each chassis colour: (body = red, yoke = black, trim = white)."""
    mx, mn = max(c), min(c)
    sat = (mx - mn) / mx if mx else 0
    lum = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
    if sat > 0.38 and c[0] >= c[1] and c[0] >= c[2]:
        return (1.0, 0.0, 0.0)
    white = max(0.0, min(1.0, (lum - 70) / 50))                    # unsaturated: dark is the yoke, light is the trim
    return (0.0, 1.0 - white, white)


def recolour_preview(img, mask, palette_colours):
    """The menu preview with its shirt (inside `mask`) in new colours: each colour's class decides which of the three
    new colours it becomes, its brightness (the shading) is kept."""
    from PIL import Image
    rgba = img.convert('RGBA')
    px, mk = rgba.load(), mask.load()
    inside = [(x, y) for y in range(rgba.height) for x in range(rgba.width) if mk[x, y] and px[x, y][3]]
    ref = [[], [], []]                                              # brightness of each class: its brighter half
    for x, y in inside:
        c = px[x, y]
        w = _classes(c[:3])
        k = w.index(max(w))
        ref[k].append(0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2])
    top = [sorted(v)[int(len(v) * 0.85)] if v else 128.0 for v in ref]
    cache = {}
    for x, y in inside:
        c = px[x, y]
        if c not in cache:
            w = _classes(c[:3])
            lum = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
            out = [0.0, 0.0, 0.0]
            for k in range(3):
                if w[k]:
                    f = lum / max(top[k], 1.0)
                    for i in range(3):
                        out[i] += w[k] * palette_colours[k][i] * f
            cache[c] = tuple(_clamp(v) for v in out) + (c[3],)
        px[x, y] = cache[c]
    return rgba


def crest_box(img, mask):
    """Where the crest sits in a menu preview: the cream parts of Utah's coyote (a colour the shirt has nowhere else),
    trimmed of strays and padded; (left, top, right, bottom)."""
    px, mk = img.convert('RGBA').load(), mask.load()
    mid = img.width // 2
    pts = [(x, y) for y in range(img.height // 3, img.height) for x in range(mid - img.width // 5, mid + img.width // 5)
           if mk[x, y] and px[x, y][3] > 200 and px[x, y][0] > 170 and px[x, y][1] > 135 and px[x, y][2] > 80
           and px[x, y][0] - px[x, y][2] > 45]
    if len(pts) < 20:
        return None
    xs, ys = sorted(p[0] for p in pts), sorted(p[1] for p in pts)
    cut = max(1, len(pts) // 25)
    return xs[cut] - 6, ys[cut] - 20, xs[-cut] + 14, ys[-cut] + 8


def preview_image(chassis_img, mask, palette, logo):
    """The menu preview of a jersey as a picture: the chassis preview in the team's colours with the team's crest."""
    out = recolour_preview(chassis_img, mask, (palette.body, palette.yoke, palette.trim))
    box = crest_box(chassis_img, mask)
    if box is not None:
        _fill_rgba(out, box, mask, chassis_img)
        if logo is not None:
            _paste_rgba(out, logo, box)
    return out


def preview_file(chassis_img, mask, palette, logo, template_art):
    """The menu preview of a jersey (bytes of a .big) in the team's own art file `template_art` (only its picture changes)."""
    from . import install
    return install.art_file(template_art, preview_image(chassis_img, mask, palette, logo))


def _fill_rgba(img, box, mask, original, reach=11):
    """The old crest painted out of `img` inside `box`: the pixels of `original` (the chassis picture) that differ from the
    shirt colour around the crest, a little widened, take the average of the (recoloured) shirt pixels near them, so the
    cloth's light and shade run on under the new crest."""
    from PIL import Image, ImageChops, ImageFilter
    px0, mk = original.convert('RGBA').load(), mask.load()
    ring = [px0[x, y][:3] for x in range(max(0, box[0] - 5), min(img.width, box[2] + 5)) for y in (box[1] - 4, box[3] + 4)
            if 0 <= y < img.height and mk[x, y] and px0[x, y][3] > 200]
    ring += [px0[x, y][:3] for y in range(max(0, box[1]), min(img.height, box[3])) for x in (box[0] - 4, box[2] + 4)
             if 0 <= x < img.width and mk[x, y] and px0[x, y][3] > 200]
    if not ring:
        return
    old = tuple(sorted(c[i] for c in ring)[len(ring) // 2] for i in range(3))
    region = original.convert('RGB').crop(box)
    diff = ImageChops.difference(region, Image.new('RGB', region.size, old)).convert('L').point(lambda v: 255 if v > 40 else 0)
    crest = diff.filter(ImageFilter.MaxFilter(7))
    w, h = region.size
    cp, sp = crest.load(), img.load()
    good = {}
    for y in range(-reach, h + reach):
        for x in range(-reach, w + reach):
            X, Y = box[0] + x, box[1] + y
            inside = 0 <= x < w and 0 <= y < h
            if 0 <= X < img.width and 0 <= Y < img.height and mk[X, Y] and sp[X, Y][3] > 200 and not (inside and cp[x, y]):
                good[(x, y)] = sp[X, Y][:3]
    out = []
    for y in range(h):
        for x in range(w):
            if not cp[x, y]:
                out.append(None)
                continue
            tot, wsum = [0.0, 0.0, 0.0], 0.0
            for yy in range(y - reach, y + reach + 1, 2):
                for xx in range(x - reach, x + reach + 1, 2):
                    c = good.get((xx, yy))
                    if c:
                        k = 1.0 / (1 + (xx - x) ** 2 + (yy - y) ** 2)
                        wsum += k
                        for i in range(3):
                            tot[i] += k * c[i]
            out.append(tuple(round(t / wsum) for t in tot) + (255,) if wsum else None)
    for i, c in enumerate(out):
        if c is not None and mk[box[0] + i % w, box[1] + i // w]:
            img.putpixel((box[0] + i % w, box[1] + i // w), c)


def _paste_rgba(img, mark, box):
    from PIL import Image
    scale = min((box[2] - box[0]) / mark.width, (box[3] - box[1]) / mark.height)
    mark = mark.convert('RGBA').resize((max(1, round(mark.width * scale)), max(1, round(mark.height * scale))), Image.LANCZOS)
    img.alpha_composite(mark, ((box[0] + box[2] - mark.width) // 2, (box[1] + box[3] - mark.height) // 2))


# --- the centre-ice logo -----------------------------------------------------------------------------------------
# measured on the disc's own `centerlogo_<art>_cm` (1024 x 1024 DXT5): an opaque ice-white disc about 388 px in radius
# with a thin blue ring, the club's logo on it, the arena's name set round it outside the disc (twice: above and
# below, the left word on the left half), and a strip 48 px wide at x 488-536 that is fully transparent (the red line
# crosses there). Every transparent pixel carries the ice colour in its RGB, the strip the logo's colours bled in.
ICE = (231, 233, 231)
RING = (8, 60, 173)
DISC_RADIUS = 388
STRIP = (488, 536)


def split_arena(name):
    """An arena's name as the two halves the ice shows (left word(s), right word(s)): 'The Delta Center' ->
    ('DELTA', 'CENTER'); 'Climate Pledge Arena' -> ('CLIMATE', 'PLEDGE ARENA')."""
    words = name.upper().split()
    if len(words) > 2 and words[0] == 'THE':
        words = words[1:]
    if len(words) < 2:
        return (' '.join(words), '')
    cut = min(range(1, len(words)), key=lambda k: abs(len(' '.join(words[:k])) - len(' '.join(words[k:]))))
    return ' '.join(words[:cut]), ' '.join(words[cut:])


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


def _ring_base(size, top, scale):
    """Radius of the baseline the letters of one size ride on: above they stand outside it, below the baseline is the
    outer edge and the letters point in."""
    return (DISC_RADIUS + 34) * scale + (0 if top else size * 0.66)


def _advances(text, font, scale):
    return [font.getlength(c) + 3 * scale for c in text]


def _fit_size(text, scale):
    """The biggest letter size (px, at `scale`) for which `text` spans at most 58 degrees of the ring."""
    size = 86 * scale
    while size > 30 * scale:
        font = _font(size)
        if math.degrees(sum(_advances(text, font, scale)) / _ring_base(size, True, scale)) <= 58:
            break
        size = int(size * 0.94)
    return size


def _arc_word(canvas, text, mid, top, colour, scale, size):
    """`text` set along the outside of the disc, its middle `mid` degrees from straight up (top) or straight down
    (below), negative to the left; letters stand upright (their tops point away from the disc above, towards it below)."""
    from PIL import Image, ImageDraw
    if not text:
        return
    cx = canvas.width // 2
    font = _font(size)
    advance = _advances(text, font, scale)
    base = _ring_base(size, top, scale)
    angle = math.radians(mid) - sum(advance) / base / 2
    tile = int(size * 2)
    for c, adv in zip(text, advance):
        theta = angle + adv / base / 2
        angle += adv / base
        glyph = Image.new('RGBA', (tile, tile), (0, 0, 0, 0))
        ImageDraw.Draw(glyph).text((tile / 2, tile / 2), c, font=font, fill=tuple(colour) + (255,), anchor='ms')
        glyph = glyph.rotate(-math.degrees(theta) if top else math.degrees(theta), resample=Image.BICUBIC)
        x = cx + base * math.sin(theta)
        y = cx - base * math.cos(theta) if top else cx + base * math.cos(theta)
        canvas.alpha_composite(glyph, (round(x - tile / 2), round(y - tile / 2)))


def centre_logo(logo, arena, colour=(32, 32, 32), size=1024):
    """The centre-ice logo for a team: the club's logo on the ice-white disc with the thin ring, the arena's name round
    it, transparent where the red line crosses (and ice-white under everything transparent, as the game's own are)."""
    from PIL import Image, ImageDraw
    scale = 2
    big = size * scale
    cx = big // 2
    canvas = Image.new('RGBA', (big, big), ICE + (0,))
    draw = ImageDraw.Draw(canvas)
    r = DISC_RADIUS * scale
    draw.ellipse((cx - r, cx - r, cx + r, cx + r), fill=RING + (255,))
    r2 = r - 8 * scale
    draw.ellipse((cx - r2, cx - r2, cx + r2, cx + r2), fill=ICE + (255,))
    if logo is not None:
        box = int(2 * r2 * 0.80)
        k = min(box / logo.width, box / logo.height)
        mark = logo.convert('RGBA').resize((max(1, round(logo.width * k)), max(1, round(logo.height * k))), Image.LANCZOS)
        canvas.alpha_composite(mark, (cx - mark.width // 2, cx - mark.height // 2))
    left, right = split_arena(arena or '')
    size_px = min((_fit_size(t, scale) for t in (left, right) if t), default=0)       # both halves in one size
    for text, mid in ((left, -32), (right, 32)):
        _arc_word(canvas, text, mid, True, colour, scale, size_px)
        _arc_word(canvas, text, mid, False, colour, scale, size_px)
    return finish_centre(canvas.resize((size, size), Image.LANCZOS))


def finish_centre(img):
    """A centre-ice picture the way the game's own are: ice-white under everything transparent, the strip where the red
    line crosses transparent and carrying the picture's colours bled in from its edges. Used for ours and the player's."""
    from PIL import Image
    img = img.convert('RGBA')
    size = img.width
    k = size / 1024
    s0, s1 = round(STRIP[0] * k), round(STRIP[1] * k)
    rgb, alpha = img.convert('RGB'), img.getchannel('A')
    ice = Image.new('RGB', img.size, ICE)
    rgb = Image.composite(rgb, ice, alpha.point(lambda v: 255 if v else 0))
    half = (s0 + s1) // 2
    rgb.paste(rgb.crop((s0 - 2, 0, s0 - 1, img.height)).resize((half - s0, img.height)), (s0, 0))   # the colours bled in
    rgb.paste(rgb.crop((s1 + 1, 0, s1 + 2, img.height)).resize((s1 - half, img.height)), (half, 0))
    alpha.paste(0, (s0, 0, s1, img.height))
    rgb.putalpha(alpha)
    return rgb


def centre_file(raw, art, logo, arena, colour, picture=None):
    """The team's own centre-ice file with the new picture in it (`picture`: the player's own, else drawn from the logo)."""
    f = rpsgl.Rpsgl(raw)
    f.replace(f"centerlogo_{art}_cm", finish_centre(picture) if picture is not None else centre_logo(logo, arena, colour))
    return f.build()


# --- the files ---------------------------------------------------------------------------------------------------
PANT_MASTERS = ((22, 22, 22), (234, 234, 234))                   # the chassis' pants: black with white stripes


class Chassis:
    """Utah's own style-1 files on the player's disc (the cloth the other teams' are cut from), read once."""

    def __init__(self, disc):
        self.disc = disc
        self.files = {}

    def _get(self, inner):
        if inner not in self.files:
            raw = self.disc.render(inner)
            if raw is None:
                raise rpsgl.RpsglError(f"the disc has no {inner}")
            self.files[inner] = rpsgl.Rpsgl(raw)
        return self.files[inner]

    def jersey(self, light):
        return self._get(JERSEY.format(s=STYLE, a=CHASSIS_ART, v=CHASSIS[light]))

    def pant(self, light):
        return self._get(PANT.format(s=STYLE, a=CHASSIS_ART, v=CHASSIS[light]))

    def sock(self, light):
        return self._get(SOCK.format(s=STYLE, a=CHASSIS_ART, v=CHASSIS[light]))


Look = namedtuple('Look', 'art kit logos arena ice_colour versions files centre', defaults=((), 'make'))
# art: the team's art id; kit: a Kit; logos: (logo for dark jerseys, logo for light jerseys and the ice) as Pillow pictures;
# arena: the name on the ice; ice_colour: the colour of that name; versions: ((variant, is the version a light one), ...) made
# from the colours; files: ((variant, light, path of the player's own colour map), ...); centre: 'make' (drawn from the logo),
# 'game' (the game's own stays) or the path of the player's own picture


def roster_versions(R, art):
    """The jersey versions of a team the roster lists (`stockteamjerseys`), style 1 (the one Play Now uses):
    [(variant, light, isdefault)] sorted; empty when the roster has no such table."""
    try:
        t = R.f['wgjx']
    except KeyError:
        return []
    return sorted({(t.get(i, 'variant'), bool(t.get(i, 'islightcolor')), bool(t.get(i, 'isdefault')))
                   for i in range(t.cur_rec) if t.get(i, 'teamartid') == art and t.get(i, 'style') == STYLE})


def jersey_versions(R, art):
    """The versions of a team the roster lists that use the shared layout: [(variant, light)] in style 1."""
    wanted = STANDARD_LAYOUT.get(art, {}).get(STYLE, ())
    return tuple((v, light) for v, light, _d in roster_versions(R, art) if v in wanted)


def _corr(a, b):
    pa, pb = list(a.getdata()), list(b.getdata())
    ma, mb = sum(pa) / len(pa), sum(pb) / len(pb)
    num = sum((x - ma) * (y - mb) for x, y in zip(pa, pb))
    den = math.sqrt(sum((x - ma) ** 2 for x in pa) * sum((y - mb) ** 2 for y in pb))
    return num / den if den else 0.0


def sample_palette(chassis_cm, user_cm):
    """The three colours of a player's own colour map: its mean colour where the chassis is body, yoke and trim coloured
    (the crest and shoulder marks left out). Returns (body, yoke, trim)."""
    from PIL import Image
    small = (256, 256)
    base = chassis_cm.convert('RGB').resize(small, Image.BOX)
    mine = user_cm.convert('RGB').resize(small, Image.BOX)
    skip = [tuple(c // 4 for c in box) for box in (CREST,) + SHOULDER]
    sums = [[0, 0, 0, 0] for _ in MASTERS]
    bp, mp = base.load(), mine.load()
    for y in range(small[1]):
        for x in range(small[0]):
            if any(b[0] - 3 <= x <= b[2] + 3 and b[1] - 3 <= y <= b[3] + 3 for b in skip):
                continue
            c = bp[x, y]
            k = min(range(3), key=lambda i: _dist2(c, MASTERS[i]))
            if _dist2(c, MASTERS[k]) <= 25 * 25:
                u = mp[x, y]
                sums[k][0] += 1
                for i in range(3):
                    sums[k][i + 1] += u[i]
    return tuple(tuple(round(s[i + 1] / s[0]) for i in range(3)) if s[0] else MASTERS[k] for k, s in enumerate(sums))


def crest_of(user_cm, body):
    """The crest of a player's own colour map as a transparent picture: what differs from the body colour in the crest's box."""
    from PIL import Image, ImageChops, ImageFilter
    region = user_cm.convert('RGB').crop(CREST)
    diff = ImageChops.difference(region, Image.new('RGB', region.size, tuple(body))).convert('L')
    alpha = diff.point(lambda v: 0 if v < 24 else min(255, v * 4)).filter(ImageFilter.GaussianBlur(0.6))
    out = region.convert('RGBA')
    out.putalpha(alpha)
    return out


class Maker:
    """Makes the files of a look from the player's disc. Heavy parts are made once and kept: the chassis, the shirt mask."""

    def __init__(self, disc):
        self.disc = disc
        self.chassis = Chassis(disc)
        self._mask = None
        self._previews = {}
        self._layout = {}

    def preview_of_chassis(self, light):
        if light not in self._previews:
            self._previews[light] = preview_picture(self.disc.find(PREVIEW.format(s=STYLE, a=CHASSIS_ART, v=CHASSIS[light])))
        return self._previews[light]

    def mask(self):
        if self._mask is None:
            self._mask = shirt_mask(self.disc, [self.preview_of_chassis(False), self.preview_of_chassis(True)])
        return self._mask

    def _relief(self, f):
        from PIL import Image
        key = next((k for k in f.rasters if k.startswith('jersey') and k.endswith('_nm')), None)
        return None if key is None else f.image(key).getchannel('A').resize((128, 128), Image.BOX)

    def standard(self, art, variant):
        """Is this version painted on the shared shirt layout (its relief map agrees with the chassis' by 90 %)?"""
        key = (art, variant)
        if key not in self._layout:
            raw = self.disc.render(JERSEY.format(s=STYLE, a=art, v=variant))
            ok = False
            if raw is not None:
                mine = self._relief(rpsgl.Rpsgl(raw))
                ref = self._relief(self.chassis.jersey(False))
                ok = mine is not None and _corr(mine, ref) > 0.9
            self._layout[key] = ok
        return self._layout[key]

    def thumbnail(self, art, variant, light, kind, logo=None, colours=None, picture=None):
        """A small picture of what a version will look like: 'game' the disc's own menu picture, 'colours' made from
        `colours` ((primary, secondary)) and `logo`, 'file' made from the player's own colour map `picture`."""
        if kind == 'game' or (kind == 'file' and not self.standard(art, variant)):
            if kind == 'file':
                return picture.convert('RGB').resize((256, 256))
            raw = self.disc.find(PREVIEW.format(s=STYLE, a=art, v=variant))
            return None if raw is None else preview_picture(raw)
        if kind == 'colours':
            kit = kit_for(*colours)
            return preview_image(self.preview_of_chassis(light), self.mask(), kit.away if light else kit.home, logo)
        chassis_cm = self.chassis.jersey(light).image(f"jersey_{STYLE}_{CHASSIS_ART}_{CHASSIS[light]}_cm")
        body, yoke, trim = sample_palette(chassis_cm, picture)
        return preview_image(self.preview_of_chassis(light), self.mask(), Palette(body, yoke, trim, yoke, (yoke,) * 2 + (trim,)),
                             crest_of(picture, body))

    def own_colour_map(self, art, variant):
        """The disc's own colour map of a version (1024 x 1024), the starting point to paint on."""
        raw = self.disc.render(JERSEY.format(s=STYLE, a=art, v=variant))
        return None if raw is None else rpsgl.Rpsgl(raw).image(f"jersey_{STYLE}_{art}_{variant}_cm")

    def own_centre(self, art):
        raw = self.disc.render(CENTRE.format(a=art))
        return None if raw is None else rpsgl.Rpsgl(raw).image(f"centerlogo_{art}_cm")

    def paths(self, look):
        """Every file path a look writes (inside the game's USRDIR)."""
        out = []
        for variant, _light in look.versions:
            out += [t.format(s=STYLE, a=look.art, v=variant) for t in (JERSEY, PANT, SOCK, PREVIEW)]
        for variant, _light, _path in look.files:
            out.append(JERSEY.format(s=STYLE, a=look.art, v=variant))
            if self.standard(look.art, variant):
                out += [t.format(s=STYLE, a=look.art, v=variant) for t in (PANT, SOCK, PREVIEW)]
        if look.centre != 'game':
            out.append(CENTRE.format(a=look.art))
        return out

    def files(self, look):
        """{path inside the game folder's USRDIR: bytes} for one team's look: every version's jersey, pants, socks and menu
        picture, and the centre-ice logo."""
        from PIL import Image
        out = {}
        art = look.art
        for variant, light in look.versions:
            palette = look.kit.away if light else look.kit.home
            logo = look.logos[1] if light else look.logos[0]
            for path, make in ((JERSEY, lambda raw: jersey_file(raw, art, variant, self.chassis, light, palette, logo)),
                               (PANT, lambda raw: pant_file(raw, art, variant, self.chassis, light, palette)),
                               (SOCK, lambda raw: sock_file(raw, art, variant, self.chassis, light, palette))):
                inner = path.format(s=STYLE, a=art, v=variant)
                raw = self.disc.render(inner)
                if raw is not None:
                    out[inner] = make(raw)
            inner = PREVIEW.format(s=STYLE, a=art, v=variant)
            raw = self.disc.find(inner)
            if raw is not None:
                out[inner] = preview_file(self.preview_of_chassis(light), self.mask(), palette, logo, raw)
        for variant, light, path in look.files:
            mine = Image.open(path)
            mine.load()
            mine = mine.convert('RGB').resize((1024, 1024), Image.LANCZOS) if mine.size != (1024, 1024) else mine.convert('RGB')
            inner = JERSEY.format(s=STYLE, a=art, v=variant)
            raw = self.disc.render(inner)
            if raw is None:
                continue
            if not self.standard(art, variant):                       # another shirt: only the colour map is theirs
                f = rpsgl.Rpsgl(raw)
                f.replace(f"jersey_{STYLE}_{art}_{variant}_cm", mine)
                out[inner] = f.build()
                continue
            chassis_cm = self.chassis.jersey(light).image(f"jersey_{STYLE}_{CHASSIS_ART}_{CHASSIS[light]}_cm")
            body, yoke, trim = sample_palette(chassis_cm, mine)
            palette = Palette(body, yoke, trim, yoke, (yoke, yoke, trim))
            out[inner] = jersey_file(raw, art, variant, self.chassis, light, palette, None, colour_map=mine)
            for path_t, make in ((PANT, lambda raw: pant_file(raw, art, variant, self.chassis, light, palette)),
                                 (SOCK, lambda raw: sock_file(raw, art, variant, self.chassis, light, palette))):
                inner = path_t.format(s=STYLE, a=art, v=variant)
                raw = self.disc.render(inner)
                if raw is not None:
                    out[inner] = make(raw)
            inner = PREVIEW.format(s=STYLE, a=art, v=variant)
            raw = self.disc.find(inner)
            if raw is not None:
                out[inner] = preview_file(self.preview_of_chassis(light), self.mask(), palette, crest_of(mine, body), raw)
        if look.centre != 'game':
            inner = CENTRE.format(a=art)
            raw = self.disc.render(inner)
            if raw is not None:
                picture = None
                if look.centre != 'make':
                    picture = Image.open(look.centre)
                    picture.load()
                    picture = picture.convert('RGBA').resize((1024, 1024), Image.LANCZOS) if picture.size != (1024, 1024) \
                        else picture.convert('RGBA')
                out[inner] = centre_file(raw, art, look.logos[1], look.arena, look.ice_colour, picture)
        return out


def jersey_file(raw, art, variant, chassis, light, palette, logo, colour_map=None):
    """The team's own jersey file (`raw`: the disc's bytes) with the chassis' look in the team's colours (or the player's own
    colour map `colour_map`, 1024 x 1024, on the chassis' relief and number sheet)."""
    f = rpsgl.Rpsgl(raw)
    src, v = chassis.jersey(light), CHASSIS[light]
    base, mine = f"{STYLE}_{CHASSIS_ART}_{v}", f"{STYLE}_{art}_{variant}"
    f.replace(f"jersey_{mine}_cm", colour_map if colour_map is not None
              else jersey_colour(src.image(f"jersey_{base}_cm"), palette, logo))
    f.copy(f"jersey_{mine}_sm", src, f"jersey_{base}_sm")
    f.replace(f"jersey_{mine}_0_nm", flatten(src.image(f"jersey_{base}_0_nm"), NORMAL_FLAT))
    f.replace(f"font_{mine}_cm", recolour(src.image(f"font_{base}_cm"), MASTERS, palette.font))
    f.copy(f"font_{mine}_nm", src, f"font_{base}_nm")
    f.copy(f"font_{mine}_sm", src, f"font_{base}_sm")
    return f.build()


def pant_file(raw, art, variant, chassis, light, palette):
    f = rpsgl.Rpsgl(raw)
    src, v = chassis.pant(light), CHASSIS[light]
    base, mine = f"pant_{STYLE}_{CHASSIS_ART}_{v}", f"pant_{STYLE}_{art}_{variant}"
    f.replace(f"{mine}_cm", recolour(src.image(f"{base}_cm"), PANT_MASTERS, (palette.pants, palette.trim)))
    f.copy(f"{mine}_nm", src, f"{base}_nm")
    f.copy(f"{mine}_sm", src, f"{base}_sm")
    return f.build()


def sock_file(raw, art, variant, chassis, light, palette):
    f = rpsgl.Rpsgl(raw)
    src, v = chassis.sock(light), CHASSIS[light]
    f.replace(f"sock_{STYLE}_{art}_{variant}_cm",
              recolour(src.image(f"sock_{STYLE}_{CHASSIS_ART}_{v}_cm"), MASTERS, (palette.body, palette.yoke, palette.trim)))
    return f.build()


# --- choosing and installing the looks -------------------------------------------------------------------------------
LOOKS_DRAWING = '#1'               # a change in how the pictures are drawn redraws every installed look once
NEW_TEAMS = {22: 'UTA', 30: 'SEA', 31: 'VGK'}        # slot -> NHL.com code (the logo)
# the versions that use the shared layout, with the roster's own flag for a light jersey (`stockteamjerseys`: the same in
# the game's own roster and the community's): Utah style 1 v0 v3 dark, v1 v4 light; Seattle v3 v4 dark, v2 v5 light;
# Vegas v2 v4 dark, v3 v5 light
DEFAULT_VERSIONS = {22: ((0, False), (1, True), (3, False), (4, True)),
                    30: ((2, True), (3, False), (4, False), (5, True)),
                    31: ((2, False), (3, True), (4, False), (5, True))}


def team_logo(url, pack=None, cache=None):
    """A club's logo from the picture cache, the program's photo pack or the web (kept in the cache), trimmed."""
    from . import images, install
    img = (cache.logo(url) if cache else None) or (pack.logo(url) if pack else None)
    if img is None:
        img = install._download(url).convert('RGBA')
        if cache:
            cache.put_logo(url, images._trim(img))
    return images._trim(img)


def default_looks(nhl_logos, pack=None, cache=None):
    """The three looks of Utah, Seattle and Vegas (colours and arena names are the community roster's:
    `builder.NHL_LOOK`); `nhl_logos` is the data pack's {NHL.com code: logo link}."""
    from .. import builder
    from . import install
    out = []
    for slot, code in sorted(NEW_TEAMS.items()):
        arena, _city, primary, secondary = builder.NHL_LOOK[slot]
        dark = nhl_logos[code]
        out.append(Look(slot, kit_for(primary, secondary),
                        (team_logo(dark, pack, cache), team_logo(install.plain_logo_url(dark), pack, cache)),
                        arena, secondary, DEFAULT_VERSIONS[slot]))
    return out


def parse_colour(text, fallback):
    """'#rrggbb' (or 'rrggbb') as (r, g, b); the fallback when it is not one."""
    t = (text or '').strip().lstrip('#')
    try:
        return (int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)) if len(t) == 6 else tuple(fallback)
    except ValueError:
        return tuple(fallback)


def team_colours(R, slot):
    """A team's two colours as the roster has them: (primary, secondary)."""
    T = R.T
    return tuple(tuple(T.get(slot, f"{kind}color_{c}") for c in 'rgb') for kind in ('primary', 'secondary'))


def team_arena(R, slot):
    try:
        return R.f['OEtS'].get(R.T.get(slot, 'arenaid'), 'arenaname')
    except (KeyError, IndexError):
        return ""


def _ink(colour):
    """A colour for the arena's name that can be read on ice-white."""
    return colour if 0.3 * colour[0] + 0.59 * colour[1] + 0.11 * colour[2] < 150 else (32, 32, 32)


def looks_from(R, edits_by_slot, logo_links, nhl_logos, pack=None, cache=None):
    """The looks to install: Utah, Seattle and Vegas as the update makes them, and every team the player gave a look in the
    Roster editor (edits.json 'uniforms' / 'ice', see edits.py). `R` is the new roster; `logo_links` {slot: logo link}.
    A version the player left alone stays the game's own (except for the three teams, where it is made from the colours)."""
    from .. import builder
    from . import install
    out = []
    for slot in sorted(set(NEW_TEAMS) | {s for s in edits_by_slot if 0 <= s < 32}):
        e = edits_by_slot.get(slot) or {}
        mine, ice = e.get('uniforms') or {}, e.get('ice') or {}
        default = slot in NEW_TEAMS
        if default:
            arena, _city, primary, secondary = builder.NHL_LOOK[slot]
        else:
            primary, secondary = team_colours(R, slot)
            arena = team_arena(R, slot)
        c = mine.get('colours') or {}
        primary, secondary = parse_colour(c.get('primary'), primary), parse_colour(c.get('secondary'), secondary)
        arena = ice.get('arena') or arena
        link = c.get('crest') or logo_links.get(slot) or (nhl_logos or {}).get(NEW_TEAMS.get(slot, ''))
        if link is None and default:
            continue
        logos = (None, None)
        if link:
            try:
                logos = (team_logo(link, pack, cache), team_logo(install.plain_logo_url(link), pack, cache))
            except Exception:
                if default:
                    continue
        listed = roster_versions(R, slot) or [(v, light, False) for v, light in DEFAULT_VERSIONS.get(slot, ())]
        choice = mine.get('versions') or {}
        versions, files = [], []
        for variant, light, _d in listed:
            use = choice.get(str(variant)) or ('colours' if default and (variant, light) in DEFAULT_VERSIONS[slot] else 'game')
            if use == 'colours':
                versions.append((variant, light))
            elif use.startswith('file:'):
                files.append((variant, light, use[5:]))
        use = ice.get('use') or ('logo' if default else 'game')
        centre = 'make' if use == 'logo' else 'game' if use == 'game' else use[5:]
        if not versions and not files and centre == 'game':
            continue
        out.append(Look(slot, kit_for(primary, secondary), logos, arena, _ink(secondary), tuple(versions), tuple(files), centre))
    return out


def look_paths(look, maker=None):
    """Every file path (inside the game's USRDIR) a look writes, without making any of it (`maker` finds out which versions
    of the player's own pictures use the shared layout; without it they count as one file each)."""
    if maker is not None:
        return maker.paths(look)
    paths = []
    for variant, _light in look.versions:
        paths += [t.format(s=STYLE, a=look.art, v=variant) for t in (JERSEY, PANT, SOCK, PREVIEW)]
    paths += [JERSEY.format(s=STYLE, a=look.art, v=variant) for variant, _l, _p in look.files]
    return paths + ([CENTRE.format(a=look.art)] if look.centre != 'game' else [])


def _file_hash(path):
    try:
        with open(path, 'rb') as f:
            return hashlib.sha1(f.read()).hexdigest()[:10]
    except OSError:
        return 'missing'


def look_digest(look):
    """What a look is made of, as a short text: a changed colour, logo, picture, arena or drawing makes a new one."""
    logos = [hashlib.sha1(l.convert('RGBA').tobytes()).hexdigest()[:10] if l is not None else '' for l in look.logos]
    return _digest(look.art, [list(map(list, p[:4])) + [list(map(list, p.font))] for p in look.kit], logos, look.arena,
                   list(look.ice_colour), [list(v) for v in look.versions],
                   [[v, light, _file_hash(path)] for v, light, path in look.files],
                   look.centre if look.centre in ('make', 'game') else _file_hash(look.centre), LOOKS_DRAWING)


def install_looks(rpcs3, title_id, looks, say=print, also=()):
    """Make the files of `looks` from the player's disc and write them into the game folder(s) (RPCS3 closed), with kept
    copies of anything replaced and the manifest "Restore the game's own pictures" uses. Returns how many files were
    written; a look that is installed already is skipped, and a file an earlier run wrote that no look wants any more
    is put back as the game had it."""
    from . import install
    from .lab import Disc
    install.check(rpcs3, title_id)
    targets = [title_id] + [t for t in also if t != title_id]
    writer = install._Writer([rpcs3.game_folder(t) for t in targets])
    maker = Maker(Disc(rpcs3.game_disc(title_id)))
    written = 0
    try:
        wanted = set()
        for look in looks:
            paths = look_paths(look, maker)
            wanted.update(paths)
            source = f"looks:{look_digest(look)}"
            if all(writer.current(tuple(p.split('/')), source) for p in paths):
                say(f"Jerseys and ice: slot {look.art} is installed already")
                continue
            say(f"Jerseys and ice: making the look of slot {look.art}")
            files = maker.files(look)
            if not files:
                raise install.ArtError("The game's 3D textures were not found on your disc, so nothing was written.")
            for inner, data in sorted(files.items()):
                writer.write(tuple(inner.split('/')), data, source)
                written += 1
            writer.save()
        for key in writer.stale('looks:', wanted):                   # chosen "the game's own" since the last time
            writer.drop(tuple(key.split('/')))
    finally:
        writer.save()
    return written
