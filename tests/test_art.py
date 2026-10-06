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


def test_the_league_test_moves_only_the_named_custom_teams(base_dir, tmp_path, monkeypatch):
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    before = Roster(open(savedata.list_rosters(r.savedata)[0].sys_data, 'rb').read())
    slot = lab.league_test(r, say=lambda m: None)
    R = Roster(slot.sys_data)
    for custom, (like, (full, _short, _abbr)) in lab.LEAGUE_MOVES.items():
        assert R.T.get(custom, 'league') == R.T.get(like, 'league') and R.T.get(custom, 'fullname') == full
    others = [t for t in range(R.T.cur_rec) if t not in lab.LEAGUE_MOVES]
    assert all(R.T.get(t, 'league') == before.T.get(t, 'league') for t in others)


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
    photos, logos, names = first.art
    assert ('PHX', 'Utah Mammoth', 'Utah', 'Mammoth', 'UTA') in names['teams'] or any(t[1] == 'Utah Mammoth' for t in names['teams'])
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
    for kind, size in (('t', (256, 256)), ('s', (128, 64)), ('w', (256, 256)), ('c', (128, 128)), ('d', (128, 128)),
                       ('r', (256, 512))):
        assert images.logo(logo, kind, size).size == size
    # the favourite-team picture: the logo in the upper half, a faint reflection, then nothing
    r = images.logo(logo, 'r', (256, 512)).getchannel('A')
    assert r.crop((0, 60, 256, 190)).getextrema()[1] == 255
    assert 0 < r.crop((0, 215, 256, 260)).getextrema()[1] <= 80
    assert r.crop((0, 280, 256, 512)).getextrema()[1] == 0


def test_logos_stay_where_the_games_own_logos_are():
    """Testers, 0.7.0: big logos covered the team's record, calendar logos spilled out of their cells.
    Each kind now stays inside the area the disc's own logos of that kind fill (images.LOGO_BOX)."""
    pytest.importorskip('PIL')
    from legacy_roster.art import images
    for logo in (head_photo(background=(0, 0, 0, 0)), head_photo()):
        for kind, size in (('t', (256, 256)), ('s', (128, 64)), ('w', (256, 256)), ('c', (128, 128)), ('d', (128, 128))):
            pic = images.logo(logo, kind, size)
            box = pic.getchannel('A').point(lambda v: 255 if v > 40 else 0).getbbox()
            l, t, r, b = images.LOGO_BOX[kind]
            assert box[0] >= l * size[0] - 1 and box[1] >= t * size[1] - 1, kind
            assert box[2] <= r * size[0] + 1 and box[3] <= b * size[1] + 1, kind
            assert (box[2] - box[0]) >= 0.8 * (r - l) * size[0] or (box[3] - box[1]) >= 0.8 * (b - t) * size[1], kind


def test_only_nhl_teams_get_the_favourite_team_logo():
    assert install.REFLECTION in install.logo_kinds(22) and install.REFLECTION in install.logo_kinds(31)
    assert install.REFLECTION not in install.logo_kinds(40) and install.REFLECTION not in install.logo_kinds(20073)


class SizedDisc(FakeDisc):
    """Templates in the game's real sizes (portraits 512 x 512 and 256 x 128, logos 256 / 128)."""
    SIZES = {'teamlogos': (256, 256), 'teamlogossmall': (128, 64), 'teamlogoswide': (256, 256),
             'teamlogoscalendar': (128, 128), 'teamlogosdynasty': (128, 128), 'teamlogosreflection': (256, 512)}

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
    assert len(written) == 2 * 2 + 6                    # 2 photos x 2 sizes, 6 logo kinds for an NHL team
    assert os.path.join('fe', 'ion', 'artassets', 'teamlogosreflection', 'r22.big') in written
    pic = bigf.ArtFile(open(os.path.join(game, 'fe', 'ion', 'artassets', 'playerheads', 'p8001_12000', 'p9857.big'),
                            'rb').read())
    assert dds.Header(pic.image()).width == 512
    assert open(theirs, 'rb').read() != b'a logo someone else put there'
    assert install.installed() == 10

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


def test_both_versions_of_the_game_get_the_pictures_and_lose_them_again(base_dir, tmp_path, monkeypatch):
    pytest.importorskip('PIL')
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    monkeypatch.setattr(install, 'Disc', SizedDisc)
    fetched = []
    monkeypatch.setattr(install, '_download', lambda url: fetched.append(url) or head_photo())
    eu, na = r.game_folder('BLES02153'), r.game_folder('BLUS31540')
    photos = {9857: 'https://photo/mcdavid.png'}
    assert install.install(r, 'BLES02153', photos, {}, say=lambda m: None, also=['BLUS31540']) == (1, 0, 0)
    assert len(fetched) == 1                                  # made once, written into both games
    files = lambda game: sorted(os.path.relpath(os.path.join(rt, f), game) for rt, _, fs in os.walk(game) for f in fs)
    assert files(eu) == files(na) and len(files(eu)) == 2
    assert install.installed() == 4
    assert install.install(r, 'BLES02153', photos, {}, say=lambda m: None) == (0, 1, 0)   # EU alone: there already
    install.remove(say=lambda m: None)
    assert files(eu) == files(na) == []


def test_pictures_are_downloaded_once_and_the_originals_are_always_kept(base_dir, tmp_path, monkeypatch):
    pytest.importorskip('PIL')
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    monkeypatch.setattr(install, 'Disc', SizedDisc)
    fetched = []
    monkeypatch.setattr(install, '_download', lambda url: fetched.append(url) or head_photo(
        background=(0, 0, 0, 0) if 'logo' in url else (240, 240, 240, 255)))
    game = r.game_folder('BLES02153')
    art = os.path.join(game, 'fe', 'ion', 'artassets')
    logo = os.path.join(art, 'teamlogos', 't22.big')
    os.makedirs(os.path.dirname(logo))
    with open(logo, 'wb') as f:
        f.write(b'the community pack logo')
    photos = {9857: 'https://photo/mcdavid.png', 20000: 'https://photo/new.png'}
    logos = {22: ('https://logo/uta.png', ((0, 0, 0), (110, 40, 120)))}
    quiet = lambda m: None

    install.install(r, 'BLES02153', photos, logos, say=quiet, pack=False)
    assert sorted(fetched) == ['https://logo/uta.png', 'https://photo/mcdavid.png', 'https://photo/new.png']
    install.remove(say=quiet)
    assert open(logo, 'rb').read() == b'the community pack logo'
    fetched.clear()                              # installed again: every picture comes from this PC
    install.install(r, 'BLES02153', photos, logos, say=quiet, pack=False)
    assert fetched == []

    # another pack's portrait put in after ours: it is kept too, and comes back with Restore
    mcdavid = os.path.join(art, 'playerheads', 'p8001_12000', 'p9857.big')
    with open(mcdavid, 'wb') as f:
        f.write(b'another pack')
    install.install(r, 'BLES02153', photos, logos, say=quiet, pack=False)
    assert open(mcdavid, 'rb').read() != b'another pack'
    newcomer = os.path.join(art, 'playerheads', 'p8001_12000', 'p20000.big')
    with open(newcomer, 'wb') as f:              # put there after ours, no copy kept: Restore leaves it
        f.write(b'mine')
    install.remove(say=quiet)
    assert open(logo, 'rb').read() == b'the community pack logo'
    assert open(mcdavid, 'rb').read() == b'another pack'
    assert open(newcomer, 'rb').read() == b'mine'

    # the list of installed files is lost: the logo there now is ours, but the kept original stays
    install.install(r, 'BLES02153', {}, logos, say=quiet, pack=False)
    os.remove(install._paths()[0])
    install.install(r, 'BLES02153', {}, logos, say=quiet, pack=False)
    install.remove(say=quiet)
    assert open(logo, 'rb').read() == b'the community pack logo'


def test_the_list_of_installed_files_of_version_0_4_is_still_read(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    path, _ = install._paths()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'game_dir': 'X:/rpcs3/dev_hdd0/game/BLES02153/USRDIR', 'files': {'a/b.big': {'source': 'u'}}}, f)
    assert install.load_manifest() == {'games': {'X:/rpcs3/dev_hdd0/game/BLES02153/USRDIR': {'a/b.big': {'source': 'u'}}}}
    assert install.installed() == 1


def test_custom_teams_get_city_keys_the_game_can_name(built_with_names):
    """A custom team shows the text under its shortname: keys like the game's own (LAS_VEGAS)."""
    res = built_with_names
    R, names = Roster(res.data), res.art[2]
    for t in range(222, 252):
        if not [i for i in range(R.U.cur_rec) if R.U.get(i, 'BSXd') == t]:
            continue
        key = R.T.get(t, 'shortname')
        assert key == key.upper() and ' ' not in key and key in names['cities'], (t, key)
    assert R.T.get(227, 'shortname') == 'LOS_ANGELES'        # the Kings copy's "NhlCityName_13" had no text
    pool = next(t for t in range(236, 252) if R.T.get(t, 'fullname') == '2026 Prospects 2')
    assert names['cities'][R.T.get(pool, 'shortname')] == '2026 Prospects 2'


@pytest.fixture(scope='module')
def built_with_names(base_bytes, data, tmp_path_factory, pack):
    d = Data(nhl_players=data.nhl_players, ea_ratings=data.ea_ratings, iihf=data.iihf, season_year=data.season_year,
             leagues=pack['leagues'], nhl_logos=pack.get('nhl_logos'))
    registry = portraits.Registry(str(tmp_path_factory.mktemp('art') / 'portrait_ids.json'))
    return pipeline.build(base_bytes, d, pipeline.steps_for(pack), art_registry=registry)


def test_the_editor_shows_the_picture_the_game_has(base_dir, tmp_path, monkeypatch):
    pytest.importorskip('PIL')
    from legacy_roster.editor import pictures

    class DiscWithMcDavid(SizedDisc):
        def find(self, inner):
            return make_art(512, 512)[0] if inner.endswith('/p9857.big') else None
    r = fake_rpcs3(base_dir, tmp_path, monkeypatch)
    monkeypatch.setattr(pictures, 'Disc', DiscWithMcDavid)
    shown = pictures.Pictures(r, 'BLES02153', pack=False)
    pic, caption = shown.current(9857, 1)
    assert pic.size == pictures.SIZE and caption == pictures.NOW               # the disc's own
    assert shown.current(9857, 0) == (None, pictures.NO_PHOTO)                  # no portrait: a silhouette
    assert pictures.Pictures(r, 'BLUS31540', pack=False).current(9857, 1) == (None, pictures.NO_GAME)


def test_logos_with_a_white_edge_are_drawn_from_espns_plain_logo(monkeypatch):
    """Testers, 0.8.0: Tampa Bay and Toronto came out all white on the favourite-team screen, because
    ESPN's logos for dark backgrounds are white silhouettes and the picture has a white edge too. The
    pictures with an edge (t, d, r) take the plain logo, the banner, watermark and calendar the dark one."""
    pytest.importorskip('PIL')
    from PIL import Image
    dark = 'https://a.espncdn.com/i/teamlogos/nhl/500-dark/tb.png'
    plain = 'https://a.espncdn.com/i/teamlogos/nhl/500/tb.png'
    assert install.plain_logo_url(dark) == plain and install.plain_logo_url('https://x/y.png') == 'https://x/y.png'
    asked = []

    class Pack:
        def logo(self, link):
            asked.append(link)
            return Image.new('RGBA', (64, 64), (255, 255, 255, 255) if 'dark' in link else (0, 40, 120, 255))

    monkeypatch.setattr(install, '_template_size', lambda template: (64, 64))
    monkeypatch.setattr(install, 'art_file', lambda template, img: img)
    monkeypatch.setattr(install, '_saturation', lambda template: 0.0)       # the game's own pictures are white too
    kinds = {('f', p): b'' for p in ('t', 's', 'w', 'c', 'd', 'r')}
    made = install.make_logo(dark, ((60, 60, 60), (20, 20, 20)), kinds, pack=Pack(), cache=False)
    assert sorted(asked) == [dark, plain]                     # each version read once
    navy = lambda kind: any(px[3] == 255 and px[2] > px[0] + 60 for px in zip(*[iter(made[('f', kind)].tobytes())] * 4))
    assert all(navy(k) for k in 'tdr') and not any(navy(k) for k in 'swc')     # navy, not white
    assert install.LOGO_DRAWING != '#2'                       # installed logos are drawn again


def test_calendar_and_wide_pictures_follow_the_games_own_colours(monkeypatch):
    """Toronto's calendar logo came out white: ESPN's dark logo is a white leaf, the game's own picture is blue.
    Tampa Bay's own calendar picture is white too, so it keeps the white logo."""
    pytest.importorskip('PIL')
    from PIL import Image
    dark = 'https://a.espncdn.com/i/teamlogos/nhl/500-dark/tor.png'
    plain = install.plain_logo_url(dark)

    class Pack:
        def logo(self, link):
            return Image.new('RGBA', (64, 64), (255, 255, 255, 255) if 'dark' in link else (0, 40, 120, 255))

    monkeypatch.setattr(install, '_template_size', lambda template: (64, 64))
    monkeypatch.setattr(install, 'art_file', lambda template, img: img)
    kinds = {('f', p): p.encode() for p in ('t', 's', 'w', 'c', 'd', 'r')}
    for coloured in (True, False):
        monkeypatch.setattr(install, '_saturation', lambda template, c=coloured: 0.8 if c else 0.0)
        made = install.make_logo(dark, ((60, 60, 60), (20, 20, 20)), kinds, pack=Pack(), cache=False)
        navy = lambda kind: any(a == 255 and b > r + 60 for r, g, b, a in zip(*[iter(made[('f', kind)].tobytes())] * 4))
        assert all(navy(k) for k in 'tdr') and not navy('s')            # the banner always keeps the dark one
        assert navy('c') == coloured and navy('w') == coloured
    assert install.LOGO_DRAWING == '#4'
