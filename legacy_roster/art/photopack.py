"""The photos and logos that come inside the photo edition of the program (photopack.zip).

The owner decided (2026-10-03) that players should not each have to download every photo: the
"Photos" exe carries a zip of the pictures already drawn (`tools/build_photopack.py`). Only
pictures missing from it are downloaded. The plain exe has no zip; there `PhotoPack.open()`
returns None and every picture is downloaded as before.

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


class PhotoPack:
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

    def _image(self, member):
        from PIL import Image
        img = Image.open(io.BytesIO(self.zip.read(member)))
        img.load()
        return img.convert('RGBA')

    def portrait(self, url, size):
        """The bundled portrait for a photo link at `size` ((512, 512), (512, 256) or (256, 128)),
        or None."""
        name = self.portraits.get(key_for(url))
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
        name = self.logos.get(key_for(url))
        return self._image(f"l/{name}.webp") if name else None
