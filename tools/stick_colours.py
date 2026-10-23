"""The colours of every hockey stick the game can draw: writes the tables of legacy_roster/sticks.py.

    .venv\\Scripts\\python tools\\stick_colours.py [--disc <iso or game folder>] [--sheet <folder>] [--check]

Reads (only reads) every stick texture of the player's own disc (`rendering/playerstick/texlib_<id>.rpsgl` in
cacherender.big; the models equipment.available finds) and measures its colours: pixels that are nearly grey, black or
white (saturation under 40 %, brightness under 22 %) do not count, the rest are grouped by hue in windows of 40 degrees,
the biggest first, each with its share of the whole texture (shares under 2 % are left out). The game's own roster
(stock.from_disc) says which models are this era's (CURRENT). BRAND below is read off the textures by eye: a new
model id stops the tool until it has one.

--disc   the disc image or extracted game folder (default: $LEGACY_ROSTER_DISC)
--sheet  also write contact sheets of all sticks into this folder, to check BRAND by eye (they hold the game's own art:
         keep them out of git)
--check  write nothing; exit 1 when sticks.py's tables differ from the disc's
"""
import argparse
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from PIL import Image, ImageDraw  # noqa: E402

from legacy_roster import equipment, stock  # noqa: E402
from legacy_roster.art import rpsgl  # noqa: E402
from legacy_roster.art.disc import EbArchive, IsoImage  # noqa: E402
from legacy_roster.roster import Roster  # noqa: E402

MODULE = os.path.join(HERE, 'legacy_roster', 'sticks.py')
START = '# --- tables made by tools/stick_colours.py'
END = '# --- end of the made tables ---'
GREY = 102          # saturation (0-255) under which a pixel is grey / black / white
DARK = 56           # brightness (0-255) under which a pixel is black
WINDOW = 14         # half a hue window (0-255 scale: 14 = about 20 degrees)
LEAST = 0.02        # colours covering less of the texture are left out
MOST = 3            # colours kept per stick

# The maker printed on each texture (2026-10-18, contact sheet of the EU disc). Reebok and CCM were one company; the
# texture says which name the stick carries.
BRAND = {
    18: 'Easton', 24: 'TPS', 25: 'Reebok', 26: 'Reebok', 30: 'TPS', 31: 'Sher-Wood', 32: 'Bauer', 33: 'Warrior',
    34: 'Warrior', 35: 'Titan', 36: 'Sher-Wood', 37: 'Bauer', 39: 'Rebellion', 40: 'Sher-Wood', 41: 'Easton',
    45: 'CCM', 46: 'Bauer', 47: 'CCM', 48: 'Warrior', 49: 'Warrior', 50: 'Reebok', 51: 'CCM', 52: 'Easton',
    53: 'Rebellion', 54: 'Warrior', 55: 'Warrior', 56: 'Bauer', 60: 'Easton', 63: 'Warrior', 64: 'CCM', 65: 'CCM',
    67: 'CCM', 68: 'Reebok', 70: 'Bauer', 71: 'Bauer', 72: 'CCM', 73: 'CCM', 74: 'Easton', 75: 'Easton',
    77: 'Easton', 78: 'Bauer', 79: 'Sher-Wood', 81: 'Easton', 82: 'Easton', 83: 'Warrior', 84: 'Warrior',
    85: 'Easton', 86: 'CCM', 87: 'CCM', 88: 'Reebok', 89: 'Bauer', 90: 'Bauer', 91: 'Sher-Wood', 92: 'Winnwell',
    93: 'Winnwell', 94: 'Busch', 95: 'Sher-Wood', 96: 'STX', 97: 'STX', 98: 'Warrior', 99: 'CCM', 100: 'Warrior',
    101: 'Warrior', 102: 'CCM', 103: 'CCM', 104: 'Easton', 105: 'Bauer', 106: 'Graf', 107: 'STX', 108: 'Bauer',
    109: 'Sher-Wood', 110: 'STX', 111: 'Bauer', 112: 'CCM',
}


def texture(archive, stick):
    """The stick's colour picture (Pillow, RGB)."""
    t = rpsgl.Rpsgl(archive.read(f'rendering/playerstick/texlib_{stick}.rpsgl'))
    names = sorted(n for n, r in t.rasters.items() if r['format'] and n.endswith('_cm')) or \
        sorted(n for n, r in t.rasters.items() if r['format'])
    return t.image(names[0]).convert('RGB')


def clusters(img):
    """((hue in degrees, share of the texture), ...) of the picture's colours, the biggest first."""
    hist = [0] * 256
    data = img.convert('HSV').tobytes()
    for k in range(0, len(data), 3):
        if data[k + 1] >= GREY and data[k + 2] >= DARK:
            hist[data[k]] += 1
    total = img.width * img.height
    out = []
    for _ in range(MOST):
        sums = [sum(hist[(c + d) % 256] for d in range(-WINDOW, WINDOW + 1)) for c in range(256)]
        centre = max(range(256), key=lambda c: (sums[c], -c))
        if sums[centre] / total < LEAST:
            break
        bins = [(centre + d) % 256 for d in range(-WINDOW, WINDOW + 1)]
        x = sum(hist[b] * math.cos(b / 256 * 2 * math.pi) for b in bins)
        y = sum(hist[b] * math.sin(b / 256 * 2 * math.pi) for b in bins)
        out.append((round(math.degrees(math.atan2(y, x))) % 360, round(sums[centre] / total, 3)))
        for b in bins:
            hist[b] = 0
    return tuple(out)


def tables(disc):
    """(the text that goes between the markers of sticks.py, the archive, the stick ids)."""
    source = IsoImage(disc) if os.path.isfile(disc) else disc
    archive = EbArchive.open(source, 'cacherender.big')
    ids = sorted(equipment.available(list(archive.entries))['stick'])
    missing = [i for i in ids if i not in BRAND]
    if missing:
        sys.exit(f"no BRAND for stick(s) {missing}: look at them (--sheet) and add them to BRAND")
    found = {i: clusters(texture(archive, i)) for i in ids}
    R = Roster(stock.from_disc(disc))
    A = R.f[equipment.TABLE]
    current = sorted({A.get(i, equipment.tag('stick')) for i in range(A.cur_rec)} & set(ids))
    lines = [START + " from the game disc's stick textures; run it again rather than editing ---", 'CLUSTERS = {']
    lines += [f"    {i}: {found[i]!r}," for i in ids]
    lines.append('}')
    lines.append('BRAND = {')
    row = '   '
    for i in ids:
        item = f" {i}: {BRAND[i]!r},"
        if len(row) + len(item) > 116:
            lines.append(row)
            row = '   '
        row += item
    lines += [row, '}', 'CURRENT = frozenset({' + ', '.join(map(str, current)) + '})', END]
    return '\n'.join(lines), archive, ids


def sheets(archive, ids, folder, per=12):
    os.makedirs(folder, exist_ok=True)
    for s in range(0, len(ids), per):
        part = ids[s:s + per]
        sheet = Image.new('RGB', (1024 + 60, 128 * len(part)), (90, 90, 90))
        draw = ImageDraw.Draw(sheet)
        for j, i in enumerate(part):
            sheet.paste(texture(archive, i), (60, 128 * j))
            draw.text((5, 128 * j + 55), str(i), fill=(255, 255, 0))
        sheet.save(os.path.join(folder, f'sticks_{s // per + 1}.png'))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--disc', default=os.environ.get('LEGACY_ROSTER_DISC'))
    ap.add_argument('--sheet')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args(argv)
    if not args.disc:
        sys.exit("say where the game disc is: --disc <iso or game folder> (or set LEGACY_ROSTER_DISC)")
    text, archive, ids = tables(args.disc)
    if args.sheet:
        sheets(archive, ids, args.sheet)
    with open(MODULE, encoding='utf-8') as f:
        module = f.read()
    rx = re.compile(re.escape(START) + r'.*?' + re.escape(END), re.S)
    if not rx.search(module):
        sys.exit(f"{MODULE} has no table markers")
    new = rx.sub(lambda _m: text, module, count=1)
    if args.check:
        print("sticks.py is up to date" if new == module else "sticks.py differs from the disc")
        return 0 if new == module else 1
    if new != module:
        with open(MODULE, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new)
    print(f"{len(ids)} sticks measured; {MODULE} {'written' if new != module else 'unchanged'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
