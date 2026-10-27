"""The small picture packs of 0.76.0 (`arenas`, `ice`, `masks`; the program downloads them, legacy_roster/packs.py).

A pack is a zip with `index.json` ({"format": 1, "built": "2026-10-27", ...what the pack holds, per pack}) and the
members the index names. Nothing here is a whole game file: arenas are the bytes that differ, ice and masks are
pictures that go into the player's own disc file (art/arenas.py, art/brightice.py, art/masks.py).
"""
import json
import zipfile

from .. import packs

FORMAT = 1


class ExtraPack:
    def __init__(self, path):
        self.zip = zipfile.ZipFile(path)
        self.index = json.loads(self.zip.read('index.json'))
        if self.index.get('format') != FORMAT:
            raise ValueError("this pack was made for a newer program")

    @classmethod
    def open(cls, name):
        """The pack `name` on this PC, or None (not downloaded, not readable, made for a newer program)."""
        path = packs.path(name)
        if not path:
            return None
        try:
            return cls(path)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            return None

    def read(self, member):
        return self.zip.read(member)

    def picture(self, member):
        """A member as a Pillow picture (RGBA)."""
        import io

        from PIL import Image
        img = Image.open(io.BytesIO(self.zip.read(member)))
        img.load()
        return img.convert('RGBA')

    def close(self):
        self.zip.close()
