"""The art file format (portraits, logos), the in-game art test, and photos and logos, on
synthetic files (no download, no game disc)."""
import io
import json
import os
import random
import shutil
import struct
import zipfile

import pytest

from legacy_roster import pipeline, savedata
from legacy_roster.art import bigf, dds, install, lab, portraits, refpack
from legacy_roster.builder import Data
from legacy_roster.roster import Roster


def dds_header(width, height, dxt5=True):
    h = bytearray(128)
    h[:4] = b'DDS '
    struct.pack_into('<7I', h, 4, 124, 0x1007, height, width, 0, 0, 0)
    struct.pack_into('<I', h, 76, 32)
    if dxt5:
        struct.pack_into('<I4s', h, 80, 4, b'DXT5')
    else:
        struct.pack_into('<III4I', h, 80, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    return bytes(h)


def make_art(width=64, height=32, dxt5=True):
    """A BIGF art file shaped like the game's: Apt data, a 288-byte part, markers, image, constants."""
    header = dds_header(width, height, dxt5)
    pixels = [[((x * 7) % 256, (y * 13) % 256, 90, 255 if y < height // 2 else 0) for x in range(width)]
              for y in range(height)]
    image = refpack.compress(dds.build(header, pixels))
    parts = [('0', b'Apt Data:1:5:4\x1a' + bytes(100)), ('7', bytes(288)), ('sg1', b''), ('6', image),
             ('sg2', b''), ('1', b'Apt constant file\x1a' + bytes(14))]
    table = b''.join(struct.pack('>II', 0, 0) + n.encode() + b'\0' for n, _ in parts)
    out = bytearray(b'BIGF' + bytes(4) + struct.pack('>II', len(parts), 16 + len(table) + 8))
    out += table + b'L288' + bytes(4)
    offsets = []
    for _n, data in parts:
        out += bytes(-len(out) % 64)
        offsets.append(len(out))
        out += data
    end = len(out)
    out += bytes(range(16))                     # the trailer
    struct.pack_into('<I', out, 4, end)
    pos = 16
    for (n, data), off in zip(parts, offsets):
        struct.pack_into('>II', out, pos, off, len(data))
        pos += 8 + len(n) + 1
    return bytes(out), pixels


SAMPLES = {'empty': b'', 'one byte': b'a', 'repeats': b'abc' * 5000, 'long range': bytes(range(256)) * 300,
           'noise': bytes(random.Random(4).randrange(256) for _ in range(20000)),
           'two letters': bytes(random.Random(5).choice(b'ab') for _ in range(40000))}


@pytest.mark.parametrize('name', sorted(SAMPLES))
def test_refpack_round_trip(name):
    data = SAMPLES[name]
    packed = refpack.compress(data)
    assert refpack.decompress(packed) == data
    if len(data) > 1000 and len(set(data)) < 10:
        assert len(packed) < len(data) // 3          # it really compresses


def test_an_art_file_reads_and_takes_a_new_image():
    raw, pixels = make_art()
    a = bigf.ArtFile(raw)
    assert a.image_part == '6' and a.end == len(raw) - 16
    w, h, back = dds.read(a.image())
    assert (w, h) == (64, 32)
    diffs = [abs(p - q) for r1, r2 in zip(pixels, back) for c1, c2 in zip(r1, r2) for p, q in zip(c1, c2)]
    assert sum(diffs) / len(diffs) < 6            # DXT5 is lossy; on real portraits the mean is ~0.2
    new = dds.build(a.image(), [[(255, 0, 0, 255)] * 64 for _ in range(32)])
    b = bigf.ArtFile(a.with_image(new))
    assert b.image() == new
    assert [n for n, _, _ in b.parts] == [n for n, _, _ in a.parts]
    assert b.part('0') == a.part('0') and b.part('1') == a.part('1') and b.part('7') == a.part('7')
    assert b.raw[b.end:] == a.raw[a.end:]             # the trailer goes along unchanged
    assert dds.read(b.image())[2][5][5] == (255, 0, 0, 255)


def test_32_bit_logos_are_exact():
    raw, pixels = make_art(32, 32, dxt5=False)
    assert dds.read(bigf.ArtFile(raw).image())[2] == pixels


class FakeDisc:
    """Stands in for the player's game disc: synthetic templates, a few portrait ids 'on the disc'."""

    def __init__(self, _path):
        class Arc:
            entries = {f"fe/ion/artassets/playerheads/{lab.portrait_folder(i)}/p{i}.big": None for i in (1, 100, 9857)}
        self.archives = {'nocache.big': Arc(), 'cache.big': Arc()}

    def portrait(self, kind, artid):
        return make_art(64, 64)[0] if kind == 'playerheads' else make_art(64, 32)[0]

    def logo(self, folder, prefix, artid):
        return make_art(32, 32, dxt5=False)[0]


def fake_rpcs3(base_dir, tmp_path, monkeypatch):
    """A pretend RPCS3 with the base roster and a game 'disc' (FakeDisc stands in for reading it)."""
    rpcs3 = tmp_path / 'rpcs3'
    saves = rpcs3 / 'dev_hdd0' / 'home' / '00000001' / 'savedata'
    saves.mkdir(parents=True)
    (rpcs3 / 'rpcs3.exe').write_text('fake')
    shutil.copytree(base_dir, saves / os.path.basename(base_dir))
    (rpcs3 / 'config').mkdir()
    (rpcs3 / 'config' / 'games.yml').write_text(f"BLES02153: {(tmp_path / 'disc.iso').as_posix()}\n")
    (tmp_path / 'disc.iso').write_bytes(b'not read: FakeDisc stands in')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    return savedata.find_rpcs3(str(rpcs3 / 'rpcs3.exe'))


def test_the_art_test_installs_and_removes_cleanly(base_dir, tmp_path, monkeypatch):
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    monkeypatch.setattr(lab, 'Disc', FakeDisc)
    game = r.game_folder('BLES02153')
    theirs = os.path.join(game, 'fe', 'ion', 'artassets', 'teamlogos', 't0.big')
    os.makedirs(os.path.dirname(theirs))
    with open(theirs, 'wb') as f:
        f.write(b'a logo someone else put there')

    slot = lab.install(r, say=lambda m: None)
    R = Roster(slot.sys_data)
    assert R.T.get(22, 'fullname') == 'Utah Mammoth' and R.T.get(31, 'abbrname') == 'VGK'
    new = [i for i in range(R.P.cur_rec) if R.name(i) in lab.NEW_PLAYERS]
    assert new and all(R.P.get(i, 'hasportrait') and R.P.get(i, 'artid') for i in new)
    written = [os.path.join(rt, f) for rt, _, fs in os.walk(game) for f in fs]
    assert len(written) >= 8 and all(bigf.ArtFile(open(p, 'rb').read()).image() for p in written if p != theirs)
    with pytest.raises(RuntimeError):            # not twice
        lab.install(r, say=lambda m: None)

    lab.remove(say=lambda m: None)
    assert [os.path.join(rt, f) for rt, _, fs in os.walk(game) for f in fs] == [theirs]
    assert open(theirs, 'rb').read() == b'a logo someone else put there'
    assert os.path.exists(slot.sys_data)         # the LAB roster stays; the player deletes it in the game


# --- photos and logos ------------------------------------------------------------------------------
def test_photos_give_lasting_portrait_ids(base_bytes, data, tmp_path):
    """Players with a photo get an id: EA's and the community's are kept, others get one of ours
    that this PC remembers, so a second run on the output is byte-identical (also with the
    registry lost: the ids in the roster are kept)."""
    d = Data(nhl_players=data.nhl_players, ea_ratings=data.ea_ratings, iihf=data.iihf, season_year=data.season_year,
             nhl_logos={'EDM': 'https://logo/edm.png', 'UTA': 'https://logo/uta.png'})
    assert sum(1 for p in d.nhl_players if p.get('photo')) > 600
    reg = portraits.Registry(str(tmp_path / 'ids.json'))
    first = pipeline.build(base_bytes, d, art_registry=reg)
    assert first.ok
    photos, logos = first.art
    assert len(photos) > 600 and len(set(photos.values())) == len(photos)
    R = Roster(first.data)
    mcdavid = next(i for i in range(R.P.cur_rec) if R.name(i) == 'Connor McDavid' and R.teams_of(i))
    assert R.P.get(mcdavid, 'artid') == 9857 and 9857 in photos        # EA's id, file gets today's photo
    ours = [a for a in photos if a in portraits.NEW_IDS]
    assert ours and all(R.P.get(r, 'hasportrait') for r in range(R.P.cur_rec) if R.P.get(r, 'artid') in ours)
    assert R.T.get(22, 'artid') in logos and logos[R.T.get(22, 'artid')][0] == 'https://logo/uta.png'
    reg.save()
    again = pipeline.build(first.data, d, art_registry=portraits.Registry(str(tmp_path / 'ids.json')))
    assert again.data == first.data and again.art[0] == photos
    lost = pipeline.build(first.data, d, art_registry=portraits.Registry(str(tmp_path / 'none.json')))
    assert lost.data == first.data


def test_photos_off_changes_nothing(base_bytes, built, data):
    assert built.art is None
    assert pipeline.build(base_bytes, data).data == built.data


def head_photo(width=240, height=240, background=(240, 240, 240, 255)):
    """A pretend player photo: a round head on shoulders on a plain background."""
    from PIL import Image, ImageDraw
    img = Image.new('RGBA', (width, height), background)
    draw = ImageDraw.Draw(img)
    draw.ellipse((80, 20, 160, 130), fill=(200, 160, 130, 255))
    draw.rectangle((105, 120, 135, 160), fill=(200, 160, 130, 255))
    draw.rounded_rectangle((20, 150, 220, 300), radius=40, fill=(20, 60, 140, 255))
    return img


def test_a_photo_becomes_a_portrait_where_the_games_own_are():
    pytest.importorskip('PIL')
    from legacy_roster.art import images
    for photo in (head_photo(), head_photo(background=(0, 0, 0, 0))):     # plain background, cut-out
        cut = images.cut_out(photo)
        assert cut.getpixel((3, 3))[3] == 0 and cut.getpixel((120, 70))[3] == 255
        for size, (top, cx, width, last) in images.PORTRAIT_SPOTS.items():
            pic = images.portrait(photo, size)
            assert pic.size == size
            found = images.head(pic.getchannel('A'))
            assert abs(found[0] - top) <= 3 and abs(found[1] - cx) <= 3 and abs(found[2] - width) <= 0.1 * width
            assert all(pic.getpixel((x, y))[3] == 0 for y in range(last + 1, size[1]) for x in range(0, size[0], 16))
    logo = head_photo(background=(0, 0, 0, 0))
    for kind, size in (('t', (256, 256)), ('s', (128, 64)), ('w', (256, 256)), ('c', (128, 128)), ('d', (128, 128))):
        assert images.logo(logo, kind, size).size == size


class SizedDisc(FakeDisc):
    """Templates in the game's real sizes (portraits 512 x 512 and 256 x 128, logos 256 / 128)."""
    SIZES = {'teamlogos': (256, 256), 'teamlogossmall': (128, 64), 'teamlogoswide': (256, 256),
             'teamlogoscalendar': (128, 128), 'teamlogosdynasty': (128, 128)}

    def portrait(self, kind, artid):
        return make_art(512, 512)[0] if kind == 'playerheads' else make_art(256, 128)[0]

    def logo(self, folder, prefix, artid):
        return make_art(*self.SIZES[folder], dxt5=False)[0]


def test_photos_and_logos_install_once_and_remove_cleanly(base_dir, tmp_path, monkeypatch):
    pytest.importorskip('PIL')
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    monkeypatch.setattr(install, 'Disc', SizedDisc)
    fetched = []
    monkeypatch.setattr(install, '_download', lambda url: fetched.append(url) or head_photo(
        background=(0, 0, 0, 0) if 'logo' in url else (240, 240, 240, 255)))
    game = r.game_folder('BLES02153')
    theirs = os.path.join(game, 'fe', 'ion', 'artassets', 'teamlogos', 't22.big')
    os.makedirs(os.path.dirname(theirs))
    with open(theirs, 'wb') as f:
        f.write(b'a logo someone else put there')
    photos = {9857: 'https://photo/mcdavid.png', 20000: 'https://photo/new.png'}
    logos = {22: ('https://logo/uta.png', ((0, 0, 0), (110, 40, 120)))}

    assert install.install(r, 'BLES02153', photos, logos, say=lambda m: None) == (3, 0, 0)
    written = sorted(os.path.relpath(os.path.join(rt, f), game) for rt, _, fs in os.walk(game) for f in fs)
    assert os.path.join('fe', 'ion', 'artassets', 'playerheads', 'p8001_12000', 'p20000.big') in written
    assert len(written) == 2 * 2 + 5
    pic = bigf.ArtFile(open(os.path.join(game, 'fe', 'ion', 'artassets', 'playerheads', 'p8001_12000', 'p9857.big'),
                            'rb').read())
    assert dds.Header(pic.image()).width == 512
    assert open(theirs, 'rb').read() != b'a logo someone else put there'
    assert install.installed() == 9

    fetched.clear()                              # the same links again: nothing is downloaded or written
    assert install.install(r, 'BLES02153', photos, logos, say=lambda m: None) == (0, 3, 0)
    assert fetched == []
    photos[20000] = 'https://photo/new-season.png'
    assert install.install(r, 'BLES02153', photos, logos, say=lambda m: None) == (1, 2, 0)

    # with a photo pack inside the program, its pictures are used and nothing is downloaded
    from legacy_roster.art import images, photopack
    from PIL import Image
    pack_path = tmp_path / 'photopack.zip'
    with zipfile.ZipFile(pack_path, 'w') as z:
        big = images.portrait(head_photo(), (512, 512)).crop((0, 0, 512, 256))
        name = photopack.file_name('https://photo/bundled.png')
        for suffix, img in (('_b', big), ('_s', images.portrait(head_photo(), (256, 128)))):
            buf = io.BytesIO()
            img.save(buf, 'WEBP')
            z.writestr(f"p/{name}{suffix}.webp", buf.getvalue())
        buf = io.BytesIO()
        Image.new('RGBA', (64, 64), (200, 0, 0, 255)).save(buf, 'WEBP', lossless=True)
        z.writestr(f"l/{photopack.file_name('https://logo/bundled.png')}.webp", buf.getvalue())
        z.writestr('index.json', json.dumps({'built': '2026-10-03',
                                             'portraits': {'https://photo/bundled.png': name},
                                             'logos': {'https://logo/bundled.png':
                                                       photopack.file_name('https://logo/bundled.png')}}))
    pack = photopack.PhotoPack.open(str(pack_path))
    assert len(pack) == 2 and photopack.key_for(
        'https://assets.nhle.com/mugs/nhl/20262027/EDM/8478402.png') == 'nhl:8478402'
    fetched.clear()
    assert install.install(r, 'BLES02153', {20001: 'https://photo/bundled.png'},
                           {23: ('https://logo/bundled.png', ((0, 0, 0), (9, 9, 9)))},
                           say=lambda m: None, pack=pack) == (2, 0, 0)
    assert fetched == []

    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: 'rpcs3.exe')
    with pytest.raises(install.ArtError):
        install.remove(say=lambda m: None)
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    install.remove(say=lambda m: None)
    assert [os.path.join(rt, f) for rt, _, fs in os.walk(game) for f in fs] == [theirs]
    assert open(theirs, 'rb').read() == b'a logo someone else put there'
    assert install.installed() == 0
