"""Photos and logos: download, draw and install the pictures, and take them away again.

    install(rpcs3, title_id, portraits, logos)   after an update with "Photos and logos" on
    remove()                                     the "Remove photos and logos" button

The pictures go, as loose files, into the game's own folder on RPCS3's hard disk
(dev_hdd0/game/<TITLEID>/USRDIR/fe/ion/artassets/...); the game reads a loose file there before
the one on the disc (tested in the game on 2026-10-03). Each art file is made from one of the
player's own disc (a template) with only the picture swapped, so nothing from EA is shipped, and
the photos and logos are downloaded on the player's PC from the leagues' public sites.

Safety: nothing is written while RPCS3 runs; any file replaced is first copied to
%LOCALAPPDATA%\\NHLLegacyRosterUpdater\\art\\backup, and a list of everything written
(art\\installed.json) lets remove() put every file back as it was. A picture already installed
from the same link is not made again, so a later update downloads only new or changed photos.

Needs Pillow (images.py); the window exe has it.
"""
import concurrent.futures
import hashlib
import io
import json
import os
import shutil

from .. import datasource, savedata
from . import bigf, dds, lab
from .lab import ART, Disc, portrait_folder
from .photopack import PhotoPack, key_for

WORKERS = 6
PORTRAIT_KINDS = ('playerheads', 'playerheadssmall')
LOGO_KINDS = lab.LOGO_KINDS          # (folder, file prefix): plain, small banner, wide, calendar, dynasty
PORTRAIT_TEMPLATE = 100              # the disc portrait whose file new portraits are made from


class ArtError(RuntimeError):
    """Something the player has to fix (RPCS3 running, game not found); the message says what."""


def _paths():
    return datasource.app_dir('art', 'installed.json'), datasource.app_dir('art', 'backup')


def load_manifest():
    path, _ = _paths()
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'game_dir': None, 'files': {}}


def _save_manifest(m):
    path, _ = _paths()
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(m, f, indent=0, sort_keys=True)
    os.replace(tmp, path)


def installed():
    """How many pictures are installed now."""
    return len(load_manifest()['files'])


# --- making the pictures --------------------------------------------------------------------------
def _dds_bytes(template, img):
    """A DDS like `template` (bytes) holding the Pillow image `img` (the template's size)."""
    h = dds.Header(template)
    if img.size != (h.width, h.height):
        raise ValueError(f"the picture must be {h.width} x {h.height}")
    if h.fourcc == 'DXT5':
        buf = io.BytesIO()
        img.save(buf, 'DDS', pixel_format='DXT5')
        body = buf.getvalue()[128:]
    else:
        # plain 32-bit pixels: byte k of each pixel is the channel whose mask starts at bit 8k
        shift = {(m & -m).bit_length() - 1: 'RGBA'[c] for c, m in enumerate(h.masks) if m}
        body = img.convert('RGBA').tobytes('raw', ''.join(shift.get(8 * k, 'X') for k in range(4)))
    if len(body) != h.data_size:
        raise ValueError("the picture came out the wrong size")
    return h.raw + body


def art_file(template_art, img):
    """A new art file: the template (bytes of a disc art file) with `img` as its picture."""
    a = bigf.ArtFile(template_art)
    return a.with_image(_dds_bytes(a.image(), img))


def _template_size(template_art):
    h = dds.Header(bigf.ArtFile(template_art).image())
    return h.width, h.height


def _download(url):
    from PIL import Image
    raw = datasource.http_get(url, timeout=30, retries=2)
    img = Image.open(io.BytesIO(raw))
    img.load()
    return img


def make_portrait(url, templates, pack=None):
    """{kind: art file bytes} for one photo link (None when the photo shows no head). A picture
    in the program's photo pack is used as it is; anything else is downloaded and drawn."""
    from . import images
    photo = None
    out = {}
    for kind in PORTRAIT_KINDS:
        size = _template_size(templates[kind])
        pic = pack.portrait(url, size) if pack else None
        if pic is None:
            photo = photo or _download(url)
            pic = images.portrait(photo, size)
        if pic is None:
            return None
        out[kind] = art_file(templates[kind], pic)
    return out


def make_logo(url, colours, templates, pack=None):
    """{(folder, prefix): art file bytes} for one logo link."""
    from . import images
    img = (pack.logo(url) if pack else None) or _download(url).convert('RGBA')
    out = {}
    for (folder, prefix), template in templates.items():
        out[(folder, prefix)] = art_file(template, images.logo(img, prefix, _template_size(template), colours))
    return out


# --- writing ------------------------------------------------------------------------------------
class _Writer:
    def __init__(self, game_dir):
        self.manifest = load_manifest()
        self.manifest['game_dir'] = game_dir
        self.game_dir = game_dir
        _, self.backups = _paths()
        os.makedirs(self.backups, exist_ok=True)

    def current(self, rel, url):
        """Is this file installed already from this link?"""
        entry = self.manifest['files'].get('/'.join(rel))
        return bool(entry and entry.get('source') == url and os.path.exists(os.path.join(self.game_dir, *rel)))

    def write(self, rel, data, url):
        key = '/'.join(rel)
        path = os.path.join(self.game_dir, *rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        entry = self.manifest['files'].get(key)
        if entry is None:
            entry = {'backup': None}
            if os.path.exists(path):              # a file we did not write: keep the original
                name = hashlib.sha1(key.encode()).hexdigest()[:16] + '_' + os.path.basename(path)
                entry['backup'] = os.path.join(self.backups, name)
                shutil.copy2(path, entry['backup'])
            self.manifest['files'][key] = entry
        entry['source'] = url
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)

    def save(self):
        _save_manifest(self.manifest)


def check(rpcs3, title_id):
    """Raise ArtError, with what to do, when the pictures cannot be installed now."""
    if savedata.running_rpcs3():
        raise ArtError("Close RPCS3 first: photos and logos can only be installed while the game is closed. "
                       "Or switch \"Photos and logos\" off.")
    if not rpcs3.game_disc(title_id):
        raise ArtError("RPCS3 does not say where your copy of the game is, so the photos cannot be made. "
                       "Start the game once from RPCS3's game list, then try again.")
    other = load_manifest().get('game_dir')
    if other not in (None, rpcs3.game_folder(title_id)):
        raise ArtError("Photos and logos are installed for another copy of RPCS3. Press \"Remove photos and "
                       "logos\" first.")


def install(rpcs3, title_id, portraits, logos, say=print, workers=WORKERS, pack=None):
    """Make and install the pictures. `portraits` {artid: photo link}, `logos` {team artid:
    (logo link, colours)} (from portraits.plan()). Pictures come from the program's photo pack
    (`pack`; default: the bundled one, if this edition has it; False: none) or are downloaded.
    Returns (written, already there, failed)."""
    check(rpcs3, title_id)
    if os.path.exists(lab.manifest_path()):
        lab.remove(say=lambda msg: None)  # the one-off art test, if it is still installed
    say("Photos and logos: reading picture templates from your game")
    disc = Disc(rpcs3.game_disc(title_id))
    p_templates = {k: disc.portrait(k, PORTRAIT_TEMPLATE) for k in PORTRAIT_KINDS}
    writer = _Writer(rpcs3.game_folder(title_id))
    pack = PhotoPack.open() if pack is None else pack or None

    jobs = []           # (description, function, [(relative path, key in the result)], link)
    bundled = 0
    for aid, url in sorted(portraits.items()):
        rels = [(ART + (k, portrait_folder(aid), f"p{aid}.big"), k) for k in PORTRAIT_KINDS]
        if not all(writer.current(rel, url) for rel, _k in rels):
            jobs.append(('photo', lambda u=url: make_portrait(u, p_templates, pack), rels, url))
            bundled += bool(pack and key_for(url) in pack.portraits)
    for aid, (url, colours) in sorted(logos.items()):
        templates = {(f, p): disc.logo(f, p, aid) or disc.logo(f, p, 0) for f, p in LOGO_KINDS}
        templates = {k: v for k, v in templates.items() if v}
        rels = [(ART + (f, f"{p}{aid}.big"), (f, p)) for f, p in templates]
        if not all(writer.current(rel, url) for rel, _k in rels):
            jobs.append(('logo', lambda u=url, c=colours, t=templates: make_logo(u, c, t, pack), rels, url))
            bundled += bool(pack and key_for(url) in pack.logos)
    already = len(portraits) + len(logos) - len(jobs)
    if not jobs:
        say(f"Photos and logos: all {already} pictures are installed already")
        return 0, already, 0

    written = failed = 0
    source = f"{bundled} from this program, {len(jobs) - bundled} to download" if pack else "downloading them"
    say(f"Photos and logos: making {len(jobs)} pictures ({already} are installed already; {source})")
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(fn): (what, rels, url) for what, fn, rels, url in jobs}
            for k, fut in enumerate(concurrent.futures.as_completed(futures), 1):
                what, rels, url = futures[fut]
                try:
                    made = fut.result()
                    why = "no head found in it" if made is None else ""
                except Exception as err:       # a photo that will not download or decode: skip it
                    made, why = None, str(err) or type(err).__name__
                if made is None:
                    failed += 1
                    say(f"Skipped the {what} {url}: {why}")
                else:
                    for rel, key in rels:
                        writer.write(rel, made[key], url)
                    written += 1
                if k % 25 == 0 or k == len(jobs):
                    say(f"Photos and logos: {k} of {len(jobs)} pictures made")
                    writer.save()
    finally:
        writer.save()
    say(f"Photos and logos: {written} pictures installed" + (f", {failed} could not be downloaded" if failed else ""))
    return written, already, failed


def remove(say=print):
    """Put every file the photos and logos replaced back and delete the ones they added.
    Returns how many files were handled."""
    m = load_manifest()
    lab_count = lab.remove(say=lambda msg: None) if os.path.exists(lab.manifest_path()) else 0
    if not m['files']:
        say("No photos or logos are installed." if not lab_count else "The art test was removed.")
        return lab_count
    if savedata.running_rpcs3():
        raise ArtError("Close RPCS3 first: photos and logos can only be removed while the game is closed.")
    game_dir = m['game_dir']
    n = 0
    for key, entry in sorted(m['files'].items()):
        path = os.path.join(game_dir, *key.split('/'))
        if entry.get('backup') and os.path.exists(entry['backup']):
            shutil.copy2(entry['backup'], path)
            os.remove(entry['backup'])
        elif os.path.exists(path):
            os.remove(path)
        n += 1
    for key in m['files']:                   # folders we created and left empty
        folder = os.path.dirname(os.path.join(game_dir, *key.split('/')))
        while folder.startswith(game_dir) and len(folder) > len(game_dir):
            try:
                os.rmdir(folder)
            except OSError:
                break
            folder = os.path.dirname(folder)
    path, _ = _paths()
    os.remove(path)
    say(f"Removed the photos and logos: {n} files put back as they were.")
    return n
