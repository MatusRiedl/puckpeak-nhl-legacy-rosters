"""The photos and logos that come inside the program (photopack.zip), and the ones this PC has
drawn itself (PictureCache).

The owner decided (2026-10-03) that players should not each have to download every photo, and
(2026-10-04) that there is one program, with the pictures inside: the exe carries a zip of the
pictures already drawn (`tools/build_photopack.py`). Only pictures missing from it (new players)
are downloaded, and each of those is kept on the PC (PictureCache), so it is downloaded once.
Run from source without the zip, `PhotoPack.open()` returns None and the cache and downloads do
the work. The command-line exe has no zip either.

    photopack.zip
        index.json          {"built": "2026-10-03", "portraits": {key: name}, "logos": {key: name}}
        p/<name>_b.webp     the portrait's top 512 x 256 (drawn by images.portrait at 512 x 512)
        p/<name>_s.webp     the small portrait, 256 x 128
        l/<name>.webp       the logo, trimmed, at most 512 px (images.logo draws the five styles from it)

A picture's key is its link, except NHL.com headshots, whose link names the season: they are keyed
by the NHL player id (`nhl:8478402`) so a new season's link still finds the bundled photo.
"""
import hashlib
import io
import json
import os
import re
import zipfile

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'photopack.zip')
NHL_HEADSHOT = re.compile(r'assets\.nhle\.com/mugs/.*/(\d+)\.png')


def key_for(url):
    m = NHL_HEADSHOT.search(url or '')
    return f"nhl:{m.group(1)}" if m else url


def file_name(key):
    return hashlib.sha1(key.encode('utf-8')).hexdigest()[:20]


class _Pictures:
    """Reading pictures stored the photo pack's way (the pack and the cache share the layout)."""

    def _read(self, member):
        raise NotImplementedError

    def _name(self, url, kind):
        """The stored name of the picture for a link ('p' portrait, 'l' logo), or None."""
        raise NotImplementedError

    def _image(self, member):
        from PIL import Image
        img = Image.open(io.BytesIO(self._read(member)))
        img.load()
        return img.convert('RGBA')

    def portrait(self, url, size):
        """The stored portrait for a photo link at `size` ((512, 512), (512, 256) or (256, 128)),
        or None."""
        name = self._name(url, 'p')
        if name is None:
            return None
        from PIL import Image
        if size == (256, 128):
            return self._image(f"p/{name}_s.webp")
        top = self._image(f"p/{name}_b.webp")
        canvas = Image.new('RGBA', size, (0, 0, 0, 0))
        canvas.paste(top, (0, 0))
        return canvas

    def logo(self, url):
        name = self._name(url, 'l')
        return self._image(f"l/{name}.webp") if name else None


class PhotoPack(_Pictures):
    def __init__(self, path):
        self.zip = zipfile.ZipFile(path)
        index = json.loads(self.zip.read('index.json'))
        self.built = index.get('built', '')
        self.portraits = index.get('portraits', {})
        self.logos = index.get('logos', {})

    @classmethod
    def open(cls, path=None):
        """The bundled pack, or None (the plain edition has none, or it cannot be read)."""
        path = path or PATH
        if not os.path.exists(path):
            return None
        try:
            return cls(path)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            return None

    def __len__(self):
        return len(self.portraits) + len(self.logos)

    def _read(self, member):
        return self.zip.read(member)

    def _name(self, url, kind):
        return (self.portraits if kind == 'p' else self.logos).get(key_for(url))


def webp(img, lossless=False, quality=85):
    """A picture as WebP bytes, the way the pack stores them."""
    buf = io.BytesIO()
    img.save(buf, 'WEBP', lossless=lossless, quality=100 if lossless else quality, method=6)
    return buf.getvalue()


class PictureCache(_Pictures):
    """Pictures this PC downloaded and drew, kept in the pack's layout under
    %LOCALAPPDATA%\\NHLLegacyRosterUpdater\\art\\pictures, keyed by their exact link (a traded
    player's new photo has a new link, so it is fetched once more). A photo that showed no head is
    remembered too (`<name>.none`), so it is not downloaded again either."""
    LOGO_SIZE = 512

    def __init__(self, folder=None):
        if folder is None:
            from .. import datasource
            folder = os.path.dirname(datasource.app_dir('art', 'pictures', 'x'))
        self.folder = folder

    def _path(self, member):
        return os.path.join(self.folder, *member.split('/'))

    def _read(self, member):
        with open(self._path(member), 'rb') as f:
            return f.read()

    def _name(self, url, kind):
        name = file_name(url)
        member = f"p/{name}_s.webp" if kind == 'p' else f"l/{name}.webp"
        return name if os.path.exists(self._path(member)) else None

    def headless(self, url):
        """Was this photo found to show no head (so it makes no portrait)?"""
        return os.path.exists(self._path(f"p/{file_name(url)}.none"))

    def _write(self, member, data):
        path = self._path(member)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)

    def put_portrait(self, url, big, small):
        """Keep a drawn portrait (`big` 512 x 512, `small` 256 x 128); None for both: no head in it."""
        name = file_name(url)
        try:
            if big is None or small is None:
                self._write(f"p/{name}.none", b'')
                return
            self._write(f"p/{name}_b.webp", webp(big.crop((0, 0, 512, 256))))
            self._write(f"p/{name}_s.webp", webp(small))
        except OSError:                 # a full disk only costs a later download
            pass

    def put_logo(self, url, img):
        logo = img.copy()
        logo.thumbnail((self.LOGO_SIZE, self.LOGO_SIZE))
        try:
            self._write(f"l/{file_name(url)}.webp", webp(logo, lossless=True))
        except OSError:
            pass
