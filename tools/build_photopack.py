"""Build the photo pack that goes inside the photo edition of the program (legacy_roster/data/photopack.zip).

    .venv\\Scripts\\python tools\\build_photopack.py            every photo and logo the data pack links
    .venv\\Scripts\\python tools\\build_photopack.py --quality 80

Needs Pillow. Downloads every player photo and club logo the bundled data pack links to (plus
today's NHL.com headshots and the NHL logos), draws them exactly as the program would
(art/images.py) and stores the results as WebP in one zip (layout in art/photopack.py).
A picture already in the previous pack under the same key is copied over, not downloaded again,
unless --fresh is given. Run it after refreshing the data pack, before building the exes.
The zip is a release file: it stays out of git.
"""
import argparse
import concurrent.futures
import datetime
import io
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from legacy_roster import datasource  # noqa: E402
from legacy_roster.art import images, install  # noqa: E402
from legacy_roster.art.photopack import PATH, PhotoPack, file_name, key_for  # noqa: E402

LOGO_SIZE = 512


def links(pack, nhl_teams):
    """({key: photo link}, {key: logo link}) of everything the data pack and the NHL rosters link."""
    photos, logos = {}, {}
    for league in pack.get('leagues', {}).values():
        for team in league['teams'] + league.get('extra', []):     # extra: clubs for a player's own team
            if team.get('logo'):
                logos[key_for(team['logo'])] = team['logo']
            for p in team['players']:
                if p.get('photo'):
                    photos[key_for(p['photo'])] = p['photo']
    for league in pack.get('leagues', {}).values():       # former: last season's photos of players on no list now
        for p in league.get('former') or []:
            photos[key_for(p['photo'])] = p['photo']
    for p in datasource.flatten_nhl(nhl_teams) + (pack.get('nhl_last') or []):   # nhl_last: unsigned free agents
        if p.get('photo'):
            photos[key_for(p['photo'])] = p['photo']
    for url in (pack.get('nhl_logos') or {}).values():
        logos[key_for(url)] = url
        plain = install.plain_logo_url(url)             # the pictures with a white edge are drawn from it
        logos[key_for(plain)] = plain
    return photos, logos


def webp(img, lossless=False, quality=85):
    buf = io.BytesIO()
    img.save(buf, 'WEBP', lossless=lossless, quality=100 if lossless else quality, method=6)
    return buf.getvalue()


def draw_photo(url, quality):
    photo = install._download(url)
    big = images.portrait(photo, (512, 512))
    small = images.portrait(photo, (256, 128))
    if big is None or small is None:
        return None
    return webp(big.crop((0, 0, 512, 256)), quality=quality), webp(small, quality=quality)


def draw_logo(url):
    logo = images._trim(install._download(url))
    logo.thumbnail((LOGO_SIZE, LOGO_SIZE))
    return webp(logo, lossless=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--quality', type=int, default=85, help="WebP quality of the portraits (default 85)")
    ap.add_argument('--fresh', action='store_true', help="download everything again")
    ap.add_argument('--out', default=PATH)
    args = ap.parse_args()
    pack = datasource.read_pack(datasource.BUNDLED_PACK)
    print("NHL rosters from NHL.com ...")
    teams = datasource.fetch_nhl_teams(pack['season'], fresh=True)
    photos, logos = links(pack, teams)
    print(f"{len(photos)} photos and {len(logos)} logos linked")
    old = None if args.fresh else PhotoPack.open(args.out)
    tmp = args.out + '.tmp'
    index = {'built': f"{datetime.date.today():%Y-%m-%d}", 'portraits': {}, 'logos': {}}
    failed = []
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED) as z:       # WebP is compressed already
        jobs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for key, url in photos.items():
                name = file_name(key)
                if old and old.portraits.get(key) == name:
                    z.writestr(f"p/{name}_b.webp", old.zip.read(f"p/{name}_b.webp"))
                    z.writestr(f"p/{name}_s.webp", old.zip.read(f"p/{name}_s.webp"))
                    index['portraits'][key] = name
                else:
                    jobs[pool.submit(draw_photo, url, args.quality)] = ('photo', key, url)
            for key, url in logos.items():
                name = file_name(key)
                if old and old.logos.get(key) == name:
                    z.writestr(f"l/{name}.webp", old.zip.read(f"l/{name}.webp"))
                    index['logos'][key] = name
                else:
                    jobs[pool.submit(draw_logo, url)] = ('logo', key, url)
            print(f"{len(jobs)} to download ({len(index['portraits']) + len(index['logos'])} kept from the last pack)")
            for k, fut in enumerate(concurrent.futures.as_completed(jobs), 1):
                kind, key, url = jobs[fut]
                try:
                    made = fut.result()
                except Exception as err:
                    made, err_text = None, str(err)
                else:
                    err_text = "no head found"
                if made is None:
                    failed.append(f"{kind} {url}: {err_text}")
                    continue
                name = file_name(key)
                if kind == 'photo':
                    z.writestr(f"p/{name}_b.webp", made[0])
                    z.writestr(f"p/{name}_s.webp", made[1])
                    index['portraits'][key] = name
                else:
                    z.writestr(f"l/{name}.webp", made)
                    index['logos'][key] = name
                if k % 250 == 0:
                    print(f"  {k} of {len(jobs)}")
        z.writestr('index.json', json.dumps(index, sort_keys=True))
    if old:
        old.zip.close()
    os.replace(tmp, args.out)
    print(f"{args.out}: {os.path.getsize(args.out) / 1e6:.1f} MB, {len(index['portraits'])} photos, "
          f"{len(index['logos'])} logos, {len(failed)} failed")
    for line in failed[:30]:
        print("   ", line[:200])


if __name__ == '__main__':
    main()
