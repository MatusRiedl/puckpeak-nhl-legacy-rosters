"""Pictures of the new jerseys and centre-ice logos, to look at BEFORE anything is installed (writes only into --out).

    .venv\\Scripts\\python tools\\look_preview.py --out <folder> [--disc <iso or folder>] [--roster <SYS-DATA>] [--slots 22,30,31]

For every team one picture: the game's own menu picture and colour map of the home and away jerseys next to the new ones,
and the game's own centre-ice logo next to the new one. The disc is only read; the pictures are made on this PC from it
and are not meant for the repository (they contain the game's own art).
"""
import argparse
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from legacy_roster import builder  # noqa: E402
from legacy_roster.art import images, looks, rpsgl  # noqa: E402
from legacy_roster.art.lab import Disc  # noqa: E402
from legacy_roster.art.photopack import PhotoPack  # noqa: E402
from legacy_roster.roster import Roster  # noqa: E402

CODES = {22: 'UTA', 30: 'SEA', 31: 'VGK'}
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def logos_for(code, pack, pictures):
    dark = pack['nhl_logos'][code]
    plain = looks_plain(dark)
    pick = lambda url: images._trim(pictures.logo(url)) if pictures and pictures.logo(url) else None  # noqa: E731
    return pick(dark) or pick(plain), pick(plain) or pick(dark)


def looks_plain(url):
    return url.replace('/500-dark/', '/500/')


def on(img, colour):
    base = Image.new('RGBA', img.size, colour + (255,))
    base.alpha_composite(img.convert('RGBA'))
    return base.convert('RGB')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', required=True)
    ap.add_argument('--disc', default=os.environ.get('LEGACY_ROSTER_DISC'))
    ap.add_argument('--roster', default=os.path.join(HERE, 'work', 'backup', 'BLES021530202', 'SYS-DATA'))
    ap.add_argument('--slots', default='22,30,31')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    disc = Disc(args.disc)
    roster = Roster(args.roster)
    pack = json.load(gzip.open(os.path.join(HERE, 'legacy_roster', 'data', 'datapack.json.gz'), 'rt', encoding='utf-8'))
    pictures = PhotoPack.open()
    maker = looks.Maker(disc)
    for slot in (int(s) for s in args.slots.split(',')):
        arena, _city, primary, secondary = builder.NHL_LOOK[slot]
        look = looks.Look(slot, looks.kit_for(primary, secondary), logos_for(CODES[slot], pack, pictures), arena,
                          secondary, looks.jersey_versions(roster, slot))
        files = maker.files(look)
        print(slot, len(files), 'files,', f"{sum(len(v) for v in files.values()) / 1e6:.0f} MB")
        shown = {}
        for variant, light in look.versions:
            shown.setdefault(light, variant)
        sheet = Image.new('RGB', (2 * 2 * 512, 2 * 512 + 512), (70, 80, 100))
        for col, light in enumerate((False, True)):
            variant = shown.get(light)
            if variant is None:
                continue
            old_prev = looks.preview_picture(disc.find(looks.PREVIEW.format(s=1, a=slot, v=variant)))
            new_prev = looks.preview_picture(files[looks.PREVIEW.format(s=1, a=slot, v=variant)])
            old_cm = rpsgl.Rpsgl(disc.render(looks.JERSEY.format(s=1, a=slot, v=variant))).image(f'jersey_1_{slot}_{variant}_cm')
            new_cm = rpsgl.Rpsgl(files[looks.JERSEY.format(s=1, a=slot, v=variant)]).image(f'jersey_1_{slot}_{variant}_cm')
            x = col * 1024
            sheet.paste(on(old_prev, (60, 70, 90)).resize((256, 256)), (x, 0))
            sheet.paste(on(new_prev, (60, 70, 90)).resize((256, 256)), (x + 256, 0))
            sheet.paste(on(old_cm, (60, 70, 90)).resize((256, 256)), (x + 512, 0))
            sheet.paste(on(new_cm, (60, 70, 90)).resize((256, 256)), (x + 768, 0))
            sheet.paste(on(new_prev, (60, 70, 90)).resize((512, 512)), (x, 256))
            sheet.paste(on(new_cm, (60, 70, 90)).resize((512, 512)), (x + 512, 256))
        old_ice = rpsgl.Rpsgl(disc.render(looks.CENTRE.format(a=slot))).image(f'centerlogo_{slot}_cm')
        new_ice = rpsgl.Rpsgl(files[looks.CENTRE.format(a=slot)]).image(f'centerlogo_{slot}_cm')
        sheet.paste(on(old_ice, (190, 215, 240)).resize((512, 512)), (0, 768 + 0))
        sheet.paste(on(new_ice, (190, 215, 240)).resize((512, 512)), (512, 768))
        sheet.crop((0, 0, 2048, 1280)).save(os.path.join(args.out, f"look_{slot}.png"))
        new_ice.save(os.path.join(args.out, f"ice_{slot}.png"))


if __name__ == '__main__':
    main()
