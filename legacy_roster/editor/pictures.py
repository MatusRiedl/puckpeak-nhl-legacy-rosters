"""The player's picture on the Roster editor's card (no window code here; needs Pillow).

    current(artid, hasportrait)   the portrait the game shows for a portrait id now: the loose file
                                  "Photos and logos" put into RPCS3's game folder, else the disc's own
    new(link)                     the photo an update would install from a link, drawn the way the
                                  update draws it (from the program's photo pack when it has it)

Both give (picture, caption): the top half of the game's big portrait (512 x 256, head and
shoulders), or None with a caption saying why there is none. Reading the disc and downloading
take a moment, so the window calls these from a worker thread; one lock keeps the disc's single
file handle safe.
"""
import io
import os
import threading

from ..art import bigf
from ..art.lab import ART, Disc, portrait_folder
from ..art.photopack import PhotoPack

SIZE = (512, 256)
NOW, AFTER, MINE = "In the game now", "After the update", "Your picture"
NO_PHOTO = "No photo in the game (it shows a silhouette)"
NO_GAME = "No picture: RPCS3 does not say where the game is"


def _top(img):
    """The head and shoulders: the top half of a 512 x 512 portrait."""
    img = img.convert('RGBA')
    if img.size != (512, 512):
        img = img.resize((512, 512))
    return img.crop((0, 0) + SIZE)


class Pictures:
    def __init__(self, rpcs3, title_id, pack=None):
        self.rpcs3, self.title_id = rpcs3, title_id
        self.pack = PhotoPack.open() if pack is None else pack or None
        self._disc = None
        self._lock = threading.Lock()
        self._new = {}              # link -> picture (None: no head found / no download)

    def _art_file(self, artid):
        """The bytes of the portrait file the game uses for `artid` (None when it has none)."""
        rel = ART + ('playerheads', portrait_folder(artid), f"p{artid}.big")
        loose = os.path.join(self.rpcs3.game_folder(self.title_id), *rel)
        if os.path.exists(loose):
            with open(loose, 'rb') as f:
                return f.read()
        path = self.rpcs3.game_disc(self.title_id)
        if not path:
            raise FileNotFoundError(NO_GAME)
        with self._lock:
            if self._disc is None:
                self._disc = Disc(path)
            return self._disc.find('/'.join(rel))

    def current(self, artid, hasportrait):
        if not artid or not hasportrait:
            return None, NO_PHOTO
        try:
            raw = self._art_file(artid)
        except FileNotFoundError:
            return None, NO_GAME
        if raw is None:
            return None, NO_PHOTO
        from PIL import Image
        img = Image.open(io.BytesIO(bigf.ArtFile(raw).image()))
        img.load()
        return _top(img), NOW

    def new(self, link):
        if link not in self._new:
            pic = self.pack.portrait(link, (512, 512)) if self.pack else None
            if pic is None:
                from ..art import images
                from ..art.install import _download
                try:
                    pic = images.portrait(_download(link), (512, 512))
                except Exception:           # no connection or not a picture: show what the game has
                    pic = None
            self._new[link] = _top(pic) if pic is not None else None
        return self._new[link], AFTER

    @staticmethod
    def mine(link):
        """The player's own picture (a 'file:' link from the editor), drawn like a portrait."""
        from PIL import Image
        from ..art import images
        photo = Image.open(link[5:])
        photo.load()
        pic = images.portrait(photo, (512, 512))
        return (_top(pic) if pic is not None else photo.convert('RGBA')), MINE
