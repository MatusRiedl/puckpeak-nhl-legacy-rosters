"""The crests of the custom teams that play in a league (Coachella Valley, Henderson: layout.OWN_ART) on their jerseys,
Select Jerseys and centre ice, installed with "Photos, logos and team names" (lab round 34, docs/notes/lab-round-34.md).

The game draws a custom team (slots 222-251, art id 20000 + n) with create-a-team logo n - 1: the loose files
`rendering/czlogo/logoct_<art - 20001>_*` in the game's USRDIR are read before the disc's, so the crest is written there:
- `0_tm` (512, DXT1): the crest as weights of the colours of table NDEo equipment 11 zones 1-3 (red, green, blue = zone
  1, 2, 3), alpha its shape. `1_tm` is the same for zones 4-6; black there adds nothing (the game's own files);
- `dm` (DXT5): the crest in its colours, alpha 0 (as the game's);
- `<cut>_nm` / `<cut>_sm` (the jersey cuts 0 1 2 4 5): the whole jersey's bump and shine maps with a crest pressed in,
  taken over from the game's logo whose shape is closest (the raster names keep their length: only logos with as many
  digits).
The menus' logo (`t<art>.big`) is the photos' own. A player who builds a create-a-team team with the same logo number sees
this crest too. The engine reads nothing here: these are pictures only.
"""
import hashlib

from .. import custom_kit, layout as L

CRESTS_DRAWING = '#1'              # a change in how the files are made redraws them once
FIRST_ART = 20001                  # art id of create-a-team logo 0
SIZE, MARGIN = 512, 8
TPL = 'rendering/czlogo/logoct_{n}_{s}.rpsgl'
TM = ('0_tm', '1_tm', 'dm')
CUTS = (0, 1, 2, 4, 5)
BUMP = tuple(f'{c}_{k}' for c in CUTS for k in ('nm', 'sm'))
LOGOS = range(0, 87)               # the disc's create-a-team logos (54 has no files)
CREST_EQUIPMENT = 11               # NDEo equipment 11: the crest's colours (zones 1-6)


def logo_number(art):
    """The create-a-team logo a custom team with art id `art` wears, or None (not a custom team's art id)."""
    return art - FIRST_ART if art >= FIRST_ART else None


def palette(R, slot):
    """The crest's three colours of slot `slot` (NDEo equipment 11, home version, zones 1-3)."""
    E = R.f['NDEo']
    for i in range(E.cur_rec):
        if E.get(i, 'team') == slot + 1 and E.get(i, 'equipment') == CREST_EQUIPMENT and E.get(i, 'variant') == 1:
            return tuple(tuple(E.get(i, f'zone{z}_{c}') for c in 'rgb') for z in (1, 2, 3))
    return None


def crest_teams(R, pictures=None):
    """[(slot, art id, palette)] of the teams whose crest the photos install: the slots of layout.OWN_ART that hold their
    own art id, and the custom teams with a crest picture of their own (`pictures` {slot: link}, the Roster editor's kit,
    custom_kit.write gave them a logo no other team wears)."""
    out = []
    wanted = {slot: art for slot, art in L.OWN_ART.items() if slot < R.T.cur_rec and R.T.get(slot, 'artid') == art}
    wanted.update({slot: R.T.get(slot, 'artid') for slot in (pictures or {}) if custom_kit.is_custom(slot)
                   and slot < R.T.cur_rec})
    for slot, art in sorted(wanted.items()):
        if custom_kit.logo_of(art) is not None:
            colours = palette(R, slot)
            if colours:
                out.append((slot, art, colours))
    return out


def fitted(img, size=SIZE, margin=MARGIN):
    """The logo trimmed to its shape and centred in a `size` square with `margin` free around it."""
    from PIL import Image
    img = img.convert('RGBA')
    box = img.getchannel('A').getbbox()
    if box:
        img = img.crop(box)
    k = (size - 2 * margin) / max(img.size)
    img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
    out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    out.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    return out


def main_colours(img, n=3):
    """The `n` colours most of the picture's visible part is painted in, most used first: the colours a crest picture
    of the player's own is drawn in (NDEo piece 11, the Roster editor's kit)."""
    from PIL import Image
    img = img.convert('RGBA')
    img.thumbnail((128, 128))
    raw = img.tobytes()
    pixels = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 4) if raw[i + 3] >= 128]
    if not pixels:
        return [(255, 255, 255)] * n
    strip = Image.new('RGB', (len(pixels), 1))
    strip.putdata(pixels)
    q = strip.quantize(colors=4 * n, method=0)          # median cut, then the most used colours that differ
    palette = q.getpalette()
    found = [tuple(palette[3 * i:3 * i + 3]) for _count, i in sorted(q.getcolors(), key=lambda c: (-c[0], c[1]))]
    out = []
    for colour in found:
        if all(sum((a - b) ** 2 for a, b in zip(colour, kept)) > DISTINCT ** 2 for kept in out):
            out.append(colour)
    return (out + out[-1:] * n)[:n]


DISTINCT = 48       # main_colours: colours closer than this (RGB distance) count as one (a picture's soft edges)


def mix(colour, colours):
    """(w1, w2, w3), none below 0, sum 1: the mix of the three `colours` closest to `colour` (least squares in the plane
    they span, clamped)."""
    p1, p2, p3 = colours
    u = [a - b for a, b in zip(p1, p3)]
    v = [a - b for a, b in zip(p2, p3)]
    r = [a - b for a, b in zip(colour, p3)]

    def dot(x, y):
        return sum(i * j for i, j in zip(x, y))
    uu, uv, vv, ur, vr = dot(u, u), dot(u, v), dot(v, v), dot(u, r), dot(v, r)
    det = uu * vv - uv * uv
    if abs(det) < 1e-9:                                 # the colours on a line: the nearest one
        dists = [dot([a - b for a, b in zip(colour, p)], [a - b for a, b in zip(colour, p)]) for p in colours]
        return [1.0 if k == dists.index(min(dists)) else 0.0 for k in range(3)]
    a = (ur * vv - vr * uv) / det
    b = (vr * uu - ur * uv) / det
    w = [max(0.0, a), max(0.0, b), max(0.0, 1 - a - b)]
    s = sum(w) or 1.0
    return [x / s for x in w]


def weights(img, colours):
    """`img` (RGBA) as weights of the three colours, red / green / blue summing to 255; alpha kept."""
    from PIL import Image
    raw, seen, out = img.convert('RGBA').tobytes(), {}, bytearray()
    for i in range(0, len(raw), 4):
        k = bytes(raw[i:i + 3])
        if k not in seen:
            w = [round(x * 255) for x in mix(tuple(k), colours)]
            w[w.index(max(w))] += 255 - sum(w)          # rounding: the sum stays 255
            seen[k] = bytes(w)
        out += seen[k]
        out.append(raw[i + 3])
    return Image.frombytes('RGBA', img.size, bytes(out))


def shown(tinted, colours):
    """The crest as the game paints `tinted` (weights) with `colours`."""
    from PIL import Image
    raw, out = tinted.tobytes(), bytearray()
    for i in range(0, len(raw), 4):
        r, g, b = raw[i:i + 3]
        out += bytes(round((r * p1 + g * p2 + b * p3) / 255) for p1, p2, p3 in zip(*colours))
        out.append(raw[i + 3])
    return Image.frombytes('RGBA', tinted.size, bytes(out))


def _mask(img):
    return img.getchannel('A').point(lambda x: 255 if x >= 128 else 0).convert('1')


def _load(disc, n, s):
    from . import rpsgl
    raw = disc.render(TPL.format(n=n, s=s))
    return None if raw is None else rpsgl.Rpsgl(raw)


def closest(disc, crest, n):
    """The game's logo (number) whose shape is closest to `crest`'s (intersection over union of the shapes) and that has every
    bump and shine map; only logos with as many digits as `n`. None when there is none."""
    from PIL import ImageChops, ImageStat
    mine = _mask(crest)
    best, score = None, -1.0
    for k in LOGOS:
        if len(str(k)) != len(str(n)):
            continue
        f = _load(disc, k, '0_tm')
        if f is None or any(disc.render(TPL.format(n=k, s=s)) is None for s in BUMP):
            continue
        other = _mask(f.image(f'logoct_{k}_0_tm'))
        both = ImageStat.Stat(ImageChops.logical_and(mine, other).convert('L')).sum[0]
        either = ImageStat.Stat(ImageChops.logical_or(mine, other).convert('L')).sum[0]
        iou = both / max(1, either)
        if iou > score:
            best, score = k, iou
    return best


def _renamed(f, old, new):
    """Texture file `f` with its raster names `old` -> `new` (the same length: the header keeps its layout)."""
    from . import rpsgl
    if len(old) != len(new):
        raise ValueError(f"{old} -> {new}: the names differ in length")
    data = bytearray(f.data)
    data[:f.header] = bytes(data[:f.header]).replace(old.encode(), new.encode())
    return rpsgl.Rpsgl(rpsgl.pack(bytes(data)) if f.packed else bytes(data))


def crest_paths(art):
    n = logo_number(art)
    return [TPL.format(n=n, s=s) for s in TM + BUMP]


def crest_files(disc, art, logo, colours):
    """{path inside USRDIR: file} of the crest of art id `art`: the logo picture `logo` (Pillow) in the three `colours`,
    made on the player's own disc. Logo n's own files are the templates of 0_tm, 1_tm and dm (a file the disc lacks for it
    is left out); the bump and shine maps come from the closest logo of the game's. {} when the disc has no files for it."""
    from PIL import Image
    n = logo_number(art)
    crest = fitted(logo)
    donor = closest(disc, crest, n)
    if donor is None or _load(disc, n, '0_tm') is None:
        return {}
    tinted = weights(crest, colours)
    out = {}
    for s in TM:
        f = _load(disc, n, s)
        if f is None:
            continue
        name = f'logoct_{n}_{s}'
        if s == '0_tm':
            f.replace(name, tinted)
        elif s == '1_tm':                   # zones 4-6: none
            blank = Image.new('RGBA', tinted.size, (0, 0, 0, 255))
            blank.putalpha(tinted.getchannel('A'))
            f.replace(name, blank)
        else:                               # dm: the crest in its colours, alpha 0
            pic = shown(tinted, colours)
            pic.putalpha(0)
            f.replace(name, pic)
        out[TPL.format(n=n, s=s)] = f.build()
    for s in BUMP:
        f = _load(disc, donor, s)
        if donor != n:
            f = _renamed(f, f'logoct_{donor}_{s}', f'logoct_{n}_{s}')
        out[TPL.format(n=n, s=s)] = f.build()
    return out


def crest_digest(art, logo, colours):
    pic = hashlib.sha1(logo.convert('RGBA').tobytes()).hexdigest()[:10]
    return f"{CRESTS_DRAWING}:{art}:{pic}:" + ','.join('%02x%02x%02x' % c for c in colours)


def crests_from(R, logo_links, pack=None, cache=None, skipped=None, pictures=None):
    """[(art id, logo picture, colours)] to install for roster `R`; `logo_links` {slot: logo link}, `pictures` {slot: the
    player's own crest picture} (wins). A team whose logo cannot be had goes into `skipped` as (slot, why)."""
    from .looks import team_logo
    out = []
    for slot, art, colours in crest_teams(R, pictures):
        link = (pictures or {}).get(slot) or logo_links.get(slot)
        if not link:
            if skipped is not None:
                skipped.append((slot, "no logo is known for it"))
            continue
        try:
            out.append((art, team_logo(link, pack, cache), colours))
        except Exception as err:
            if skipped is not None:
                skipped.append((slot, f"its logo could not be had ({err})"))
    return out


def install_crests(rpcs3, title_id, crests, say=print, also=()):
    """Make the files of `crests` (crests_from) from the player's disc and write them into the game folder(s) (RPCS3
    closed), with the manifest "Restore the game's own pictures" uses. A crest installed already is skipped; files of a
    crest no longer wanted are taken away. Returns how many files were written."""
    from . import install
    from .lab import Disc
    install.check(rpcs3, title_id)
    targets = [title_id] + [t for t in also if t != title_id]
    writer = install._Writer([rpcs3.game_folder(t) for t in targets])
    disc = Disc(rpcs3.game_disc(title_id))
    written, wanted = 0, set()
    try:
        for art, logo, colours in crests:
            paths = crest_paths(art)
            source = f"crests:{crest_digest(art, logo, colours)}"
            if all(writer.current(tuple(p.split('/')), source) for p in paths):
                continue
            files = crest_files(disc, art, logo, colours)
            wanted.update(files)
            for inner, data in sorted(files.items()):
                writer.write(tuple(inner.split('/')), data, source)
                written += 1
        wanted.update(p for art, _l, _c in crests for p in crest_paths(art))
        for key in writer.stale('crests:', wanted):
            writer.drop(tuple(key.split('/')))
    finally:
        writer.save()
    if written:
        say(f"Jerseys and ice: crests of {len(crests)} custom teams on their jerseys and centre ice")
    return written
