"""Photos and logos: download, draw and install the pictures, and take them away again.

    install(rpcs3, title_id, portraits, logos)   after an update with "Photos and logos" on
    remove()                                     the "Restore the game's own pictures" button

The pictures go, as loose files, into the game's own folder on RPCS3's hard disk
(dev_hdd0/game/<TITLEID>/USRDIR/fe/ion/artassets/...); the game reads a loose file there before
the one on the disc (tested in the game on 2026-10-03). Each art file is made from one of the
player's own disc (a template) with only the picture swapped, so nothing from EA is shipped, and
the photos and logos are downloaded on the player's PC from the leagues' public sites.

The European (BLES02153) and North American (BLUS31540) versions each have their own folder; their
discs hold the same art and text files, so one set of pictures made from either disc serves both
(`also`: further versions that receive every file too).

Safety: nothing is written while RPCS3 runs; any file replaced is first copied to
%LOCALAPPDATA%\\NHLLegacyRosterUpdater\\art\\backup, and a list of everything written, per game
folder (art\\installed.json), lets remove() put every file back as it was. A picture already
installed from the same link is not made again, so a later update downloads only new or changed
photos.

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
from .photopack import PhotoPack, PictureCache, key_for

WORKERS = 6
PORTRAIT_KINDS = ('playerheads', 'playerheadssmall')
LOGO_KINDS = lab.LOGO_KINDS          # (folder, file prefix): plain, small banner, wide, calendar, dynasty
# the logo standing on its reflection: the favourite-team screens. The disc has one for each NHL team
# (art ids 0-29); Seattle and Vegas in the All-Star slots 30/31 get one made from Anaheim's file
REFLECTION = ('teamlogosreflection', 'r')
PORTRAIT_TEMPLATE = 100              # the disc portrait whose file new portraits are made from


def logo_kinds(artid):
    """The logo pictures a team gets: every kind, and for the 32 NHL teams the reflection too."""
    return LOGO_KINDS + (REFLECTION,) if artid < 32 else LOGO_KINDS


class ArtError(RuntimeError):
    """Something the player has to fix (RPCS3 running, game not found); the message says what."""


def _paths():
    return datasource.app_dir('art', 'installed.json'), datasource.app_dir('art', 'backup')


def load_manifest():
    """{'games': {game folder: {file key: {'source': link, 'backup': path or None,
    'stamp': [size, time] of the file as written}}}}. 'stamp' tells a file of ours from one put
    there later (another picture pack); manifests before 0.6 have none."""
    path, _ = _paths()
    try:
        with open(path, encoding='utf-8') as f:
            m = json.load(f)
    except (OSError, ValueError):
        m = {}
    if 'games' not in m:                # version 0.4 and earlier: one game folder
        m = {'games': {m['game_dir']: m.get('files') or {}} if m.get('game_dir') else {}}
    return m


def _save_manifest(m):
    path, _ = _paths()
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(m, f, indent=0, sort_keys=True)
    os.replace(tmp, path)


def installed():
    """How many picture and text files are installed now (every game version together)."""
    return sum(len(files) for files in load_manifest()['games'].values())


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
    """A picture from a link; 'file:<path>' is a picture of the player's own (Roster editor)."""
    from PIL import Image
    if url.startswith('file:'):
        img = Image.open(url[5:])
    else:
        img = Image.open(io.BytesIO(datasource.http_get(url, timeout=30, retries=2)))
    img.load()
    return img


def _cacheable(url):
    return not url.startswith(('file:', 'badge:'))        # the player's own pictures are on his PC already


def make_portrait(url, templates, pack=None, cache=None):
    """{kind: art file bytes} for one photo link (None when the photo shows no head). A picture
    this PC drew before (`cache`) or the program's photo pack has is used as it is; anything else
    is downloaded, drawn, and kept in the cache."""
    from . import images
    cache = cache if cache and _cacheable(url) else None
    if cache and cache.headless(url):
        return None
    stores = [s for s in (cache, pack) if s]
    photo = None
    drawn, out = {}, {}
    for kind in PORTRAIT_KINDS:
        size = _template_size(templates[kind])
        pic = next((p for p in (s.portrait(url, size) for s in stores) if p is not None), None)
        if pic is None:
            photo = photo or _download(url)
            pic = drawn[size] = images.portrait(photo, size)
        if pic is None:
            if cache:
                cache.put_portrait(url, None, None)
            return None
        out[kind] = art_file(templates[kind], pic)
    if cache and (512, 512) in drawn and (256, 128) in drawn:
        cache.put_portrait(url, drawn[(512, 512)], drawn[(256, 128)])
    return out


def make_logo(url, colours, templates, pack=None, cache=None):
    """{(folder, prefix): art file bytes} for one logo link (from the cache, the pack, or downloaded
    and then kept in the cache)."""
    from . import images
    cache = cache if cache and _cacheable(url) else None
    if url.startswith('badge:'):                   # a draft-class pool: a badge with its year
        img = images.badge(url[len('badge:'):], colours)
    else:
        img = (cache.logo(url) if cache else None) or (pack.logo(url) if pack else None)
        if img is None:
            img = _download(url).convert('RGBA')
            if cache:
                cache.put_logo(url, images._trim(img))
    out = {}
    for (folder, prefix), template in templates.items():
        out[(folder, prefix)] = art_file(template, images.logo(img, prefix, _template_size(template), colours))
    return out


# --- writing ------------------------------------------------------------------------------------
class _Writer:
    """Writes files into one or more game folders (the versions of the game being updated) and
    keeps the manifest of everything written."""

    def __init__(self, game_dirs):
        self.manifest = load_manifest()
        self.game_dirs = list(game_dirs)
        for d in self.game_dirs:
            self.manifest['games'].setdefault(d, {})
        _, self.backups = _paths()
        os.makedirs(self.backups, exist_ok=True)

    def current(self, rel, url):
        """Is this file installed already from this link, in every game folder (and still ours)?"""
        key = '/'.join(rel)
        for d in self.game_dirs:
            entry = self.manifest['games'][d].get(key)
            path = os.path.join(d, *rel)
            if not (entry and entry.get('source') == url and os.path.exists(path) and ours(entry, path)):
                return False
        return True

    def _keep(self, game_dir, key, path, newer=False):
        """Copy the file at `path` (not ours) aside so "Restore" can put it back. A copy already kept
        is never overwritten by one of our own files (after a lost manifest the file there is ours);
        only `newer`, a file someone put there after ours, replaces it."""
        name = hashlib.sha1(f"{game_dir}|{key}".encode()).hexdigest()[:16] + '_' + os.path.basename(path)
        target = os.path.join(self.backups, name)
        if newer or not os.path.exists(target):
            shutil.copy2(path, target)
        return target

    def write(self, rel, data, url):
        key = '/'.join(rel)
        for d in self.game_dirs:
            files = self.manifest['games'][d]
            path = os.path.join(d, *rel)
            entry = files.get(key)
            exists = os.path.exists(path)
            if entry and entry.get('source') == url and exists and ours(entry, path):
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if entry is None:
                entry = files[key] = {'backup': None}
                if exists:                            # a file we did not write: keep the original
                    entry['backup'] = self._keep(d, key, path)
            elif exists and not ours(entry, path):    # put there after ours (another pack): keep that one
                entry['backup'] = self._keep(d, key, path, newer=True)
            entry['source'] = url
            tmp = path + '.tmp'
            with open(tmp, 'wb') as f:
                f.write(data)
            os.replace(tmp, path)
            entry['stamp'] = stamp(path)

    def save(self):
        _save_manifest(self.manifest)


def stamp(path):
    st = os.stat(path)
    return [st.st_size, st.st_mtime_ns]


def ours(entry, path):
    """Is the file at `path` still the one this program wrote (manifests before 0.6: assumed)?"""
    if not entry.get('stamp'):
        return True
    try:
        return stamp(path) == list(entry['stamp'])
    except OSError:
        return False


def _inside(path, folder):
    path, folder = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return path.startswith(folder.rstrip(os.sep) + os.sep)


def check(rpcs3, title_id):
    """Raise ArtError, with what to do, when the pictures cannot be installed now."""
    if savedata.running_rpcs3():
        raise ArtError("Close RPCS3 first: photos and logos can only be installed while the game is closed. "
                       "Or switch \"Photos and logos\" off.")
    if not rpcs3.game_disc(title_id):
        raise ArtError("RPCS3 does not say where your copy of the game is, so the photos cannot be made. "
                       "Start the game once from RPCS3's game list, then try again.")
    if any(not _inside(d, rpcs3.dev_hdd0) for d in load_manifest()['games']):
        raise ArtError("Photos and logos are installed for another copy of RPCS3. Press \"Restore the game's "
                       "own pictures\" first.")


def install_names(disc, writer, names, say):
    """The game's text files with the roster's team names (loc.py), one per language, made from
    the disc's own each time (so nothing piles up). Returns how many files were written."""
    import hashlib as _h
    from . import loc
    source = 'names:' + _h.sha1(json.dumps(names, sort_keys=True, default=sorted).encode()).hexdigest()
    written = 0
    for lang in loc.LANGUAGES:
        rel = ('fe', 'loc', f"nhl_{lang}.db")
        if writer.current(rel, source):
            continue
        original = disc.text_file(lang)
        if original is None:
            continue
        text = loc.LocFile(original)
        if loc.apply_names(text, names):
            writer.write(rel, text.build(), source)
            written += 1
    if written:
        say(f"Photos and logos: team names written in {written} languages")
    return written


def install(rpcs3, title_id, portraits, logos, say=print, workers=WORKERS, pack=None, names=None, also=(),
            cache=None):
    """Make and install the pictures. `portraits` {artid: photo link}, `logos` {team artid:
    (logo link, colours)} (from portraits.plan()). Pictures come from the program's photo pack
    (`pack`; default: the bundled one, if this edition has it; False: none) or are downloaded.
    `names` (portraits.names()) go into the game's text files. Templates come from the disc of
    `title_id`; `also` are further versions of the game (title ids) that get every file as well.
    Returns (written, already there, failed)."""
    check(rpcs3, title_id)
    if os.path.exists(lab.manifest_path()):
        lab.remove(say=lambda msg: None)  # the one-off art test, if it is still installed
    say("Photos and logos: reading picture templates from your game")
    disc = Disc(rpcs3.game_disc(title_id))
    p_templates = {k: disc.portrait(k, PORTRAIT_TEMPLATE) for k in PORTRAIT_KINDS}
    targets = [title_id] + [t for t in also if t != title_id]
    writer = _Writer([rpcs3.game_folder(t) for t in targets])
    pack = PhotoPack.open() if pack is None else pack or None
    cache = PictureCache() if cache is None else cache or None
    if names:
        try:
            install_names(disc, writer, names, say)
        finally:
            writer.save()

    jobs = []           # (description, function, [(relative path, key in the result)], link)
    bundled = kept = 0
    for aid, url in sorted(portraits.items()):
        rels = [(ART + (k, portrait_folder(aid), f"p{aid}.big"), k) for k in PORTRAIT_KINDS]
        if not all(writer.current(rel, url) for rel, _k in rels):
            jobs.append(('photo', lambda u=url: make_portrait(u, p_templates, pack, cache), rels, url))
            if cache and _cacheable(url) and (cache.portrait(url, (256, 128)) is not None or cache.headless(url)):
                kept += 1
            else:
                bundled += bool(pack and key_for(url) in pack.portraits)
    for aid, (url, colours) in sorted(logos.items()):
        templates = {(f, p): disc.logo(f, p, aid) or disc.logo(f, p, 0) for f, p in logo_kinds(aid)}
        templates = {k: v for k, v in templates.items() if v}
        rels = [(ART + (f, f"{p}{aid}.big"), (f, p)) for f, p in templates]
        if not all(writer.current(rel, url) for rel, _k in rels):
            jobs.append(('logo', lambda u=url, c=colours, t=templates: make_logo(u, c, t, pack, cache), rels, url))
            if cache and _cacheable(url) and cache._name(url, 'l'):
                kept += 1
            else:
                bundled += bool(pack and key_for(url) in pack.logos) or url.startswith(('badge:', 'file:'))
    already = len(portraits) + len(logos) - len(jobs)
    if not jobs:
        say(f"Photos and logos: all {already} pictures are installed already")
        return 0, already, 0

    written = failed = 0
    fetch = len(jobs) - bundled - kept
    source = ", ".join(part for part in (f"{bundled} from this program" if pack else "",
                                         f"{kept} kept on this PC" if kept else "",
                                         f"{fetch} to download" if fetch else "") if part) or "none to download"
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
    if not any(m['games'].values()):
        say("No photos or logos are installed." if not lab_count else "The art test was removed.")
        path, _ = _paths()
        if os.path.exists(path):
            os.remove(path)
        return lab_count
    if savedata.running_rpcs3():
        raise ArtError("Close RPCS3 first: photos and logos can only be removed while the game is closed.")
    n = 0
    for game_dir, files in sorted(m['games'].items()):
        for key, entry in sorted(files.items()):
            path = os.path.join(game_dir, *key.split('/'))
            if entry.get('backup') and os.path.exists(entry['backup']):
                shutil.copy2(entry['backup'], path)
                os.remove(entry['backup'])
            elif os.path.exists(path) and ours(entry, path):
                os.remove(path)             # a file someone put there after ours (no copy kept) stays
            n += 1
        for key in files:                    # folders we created and left empty
            folder = os.path.dirname(os.path.join(game_dir, *key.split('/')))
            while folder.startswith(game_dir) and len(folder) > len(game_dir):
                try:
                    os.rmdir(folder)
                except OSError:
                    break
                folder = os.path.dirname(folder)
    path, _ = _paths()
    os.remove(path)
    say(f"The game's own pictures are back: {n} files put back as they were.")
    return n
