"""The DXT encoder of the 3D textures (art/dds.py; rpsgl.Rpsgl.replace uses it). The centre-ice logos, the number sheets
and the helmet decals are blended with their alpha, so their edges and their smaller mipmaps must keep both the alpha
and the colour; docs/notes/centre-ice-quality.md has the numbers. The pictures are made here; the tests with the look
pack (private/packs/looks.zip, never in git) or the game's disc (LEGACY_ROSTER_DISC, read only) skip without
them."""
import io
import os
import struct
import zipfile

import pytest

from legacy_roster.art import dds, rpsgl

PIL = pytest.importorskip('PIL')
from PIL import Image, ImageChops, ImageDraw, ImageStat  # noqa: E402

DISC = os.environ.get('LEGACY_ROSTER_DISC')
PACK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'private', 'packs', 'looks.zip')
ICE = (231, 233, 231)
BLUE = (12, 55, 145)


def levels(data, fmt, width, height, mips, crop=True):
    """The decoded mipmaps in `data` (the bytes of dds.mipmaps)."""
    out, pos, size = [], 0, 8 if fmt == 'DXT1' else 16
    for k in range(mips):
        lw, lh = max(1, width >> k), max(1, height >> k)
        n = max(1, lw // 4) * max(1, lh // 4) * size
        img = dds.decode(data[pos:pos + n], fmt, max(4, lw), max(4, lh))
        out.append(img.crop((0, 0, lw, lh)) if crop else img)
        pos += n
    assert pos == len(data)
    return out


def percentile(diff, mask, q):
    """The q-th percentile of a one-channel picture over the pixels `mask` marks."""
    hist = diff.histogram(mask)
    need, run = sum(hist) * q / 100, 0
    for v, n in enumerate(hist):
        run += n
        if run >= need:
            return v
    return 255


def alpha_error(got, want, q=99):
    """How far the alpha of `got` is from `want`'s (the q-th percentile over the pixels either shows)."""
    ga, wa = got.getchannel('A'), want.getchannel('A')
    shows = ImageChops.lighter(ga, wa).point(lambda v: 255 if v else 0)
    return percentile(ImageChops.difference(ga, wa), shows, q)


def edge_colour(img, of):
    """The mean colour in `img` of the pixels `of` shows in part (alpha 1-254): the edge of the logo."""
    edge = of.getchannel('A').point(lambda v: 255 if 0 < v < 255 else 0)
    return ImageStat.Stat(img.convert('RGB'), edge).mean


def soft_logo(size=256):
    """A blue disc with a white ring and a soft edge, ice-white under what is transparent (as looks.finish_centre leaves
    a centre-ice logo)."""
    big = size * 4

    def disc(a, b, fill, base=None):
        img = base or Image.new('L', (big, big), 0)
        ImageDraw.Draw(img).ellipse((big * a, big * a, big * b, big * b), fill=fill)
        return img
    mask = disc(0.15, 0.85, 255).resize((size, size), Image.BOX)
    ring = disc(0.38, 0.62, 0, disc(0.3, 0.7, 255)).resize((size, size), Image.BOX)
    rgb = Image.composite(Image.new('RGB', (size, size), (240, 240, 240)), Image.new('RGB', (size, size), BLUE), ring)
    rgb = Image.composite(rgb, Image.new('RGB', (size, size), ICE), mask.point(lambda v: 255 if v else 0))
    rgb.putalpha(mask)
    return rgb


def _alpha_of(block8):
    return [p[3] for row in dds.decode_dxt5(block8 + bytes(8), 4, 4) for p in row]


def _colours_of(c0, c1, bits):
    return [p[:3] for row in dds.decode_dxt5(bytes((255, 255)) + bytes(6) + struct.pack('<HHI', c0, c1, bits), 4, 4)
            for p in row]


# --- one block --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('values, off', [([3] * 8 + [250] * 8, 0),                # a hard edge: both ends exact
                                         ([0] * 6 + [255] * 6 + [128] * 4, 0),    # 0 and 255 exact, the middle too
                                         ([0, 255] * 8, 0),
                                         ([7] * 16, 0),
                                         (list(range(100, 196, 6)), 7),           # a ramp: within half a step
                                         ([0, 17, 34, 51] * 4, 4)])
def test_alpha_blocks_reach_the_ends_and_take_the_nearer_ramp(values, off):
    data, err = dds.alpha_block(bytes(values))
    got = _alpha_of(data)
    assert max(abs(a - b) for a, b in zip(got, values)) <= off
    assert err == sum((a - b) ** 2 for a, b in zip(got, values))


def test_colour_blocks_keep_the_colours_the_block_has():
    green, white = (30, 200, 30), (240, 240, 240)
    px = [green] * 8 + [white] * 8
    c0, c1, bits, _err = dds.colour_block([p[0] for p in px], [p[1] for p in px], [p[2] for p in px], [255] * 16)
    assert c0 > c1                                                             # four colours (DXT5 knows no other)
    for got, want in zip(_colours_of(c0, c1, bits), px):
        assert max(abs(a - b) for a, b in zip(got, want)) <= 8
    assert _colours_of(*dds.single_colour(255, 0, 0)) == [(255, 0, 0)] * 16
    # half of it transparent (weight 0): only the blue that shows counts
    px = [BLUE] * 8 + [ICE] * 8
    c0, c1, bits, _err = dds.colour_block([p[0] for p in px], [p[1] for p in px], [p[2] for p in px], [255] * 8 + [0] * 8)
    for got in _colours_of(c0, c1, bits)[:8]:
        assert max(abs(a - b) for a, b in zip(got, BLUE)) <= 2


@pytest.mark.parametrize('slack', [dds.COLOUR_SLACK, 0])          # 0: every block also encoded here (three colours)
def test_dxt1_keeps_one_bit_of_alpha(slack):
    img = Image.new('RGBA', (8, 8), (200, 40, 40, 255))
    for x in range(8):
        img.putpixel((x, 0), (200, 40, 40, 0))
        img.putpixel((x, 1), (90, 200, 40, 100))                  # below half: transparent
        img.putpixel((x, 2), (90, 200, 40, 140))                  # above: shows
    got = dds.decode(dds.encode_level(img, 'DXT1', colour_slack=slack), 'DXT1', 8, 8)
    for x in range(8):
        assert got.getpixel((x, 0))[3] == got.getpixel((x, 1))[3] == 0
        assert got.getpixel((x, 2))[3] == got.getpixel((x, 5))[3] == 255
        assert max(abs(a - b) for a, b in zip(got.getpixel((x, 2))[:3], (90, 200, 40))) <= 12
        assert max(abs(a - b) for a, b in zip(got.getpixel((x, 5))[:3], (200, 40, 40))) <= 12


def test_alpha_that_is_data_is_averaged_on_its_own():
    img = Image.new('RGBA', (2, 1))
    img.putpixel((0, 0), (255, 0, 0, 10))
    img.putpixel((1, 0), (0, 0, 255, 250))
    r, g, b, a = dds.shrink(img, (1, 1), coverage=False).getpixel((0, 0))     # a normal map: every channel alone
    assert 126 <= r <= 129 and 126 <= b <= 129 and a == 130
    r, g, b, a = dds.shrink(img, (1, 1)).getpixel((0, 0))                     # coverage: the colour that shows
    assert r < 20 and b > 230 and a == 130


# --- whole pictures ---------------------------------------------------------------------------------------------------
def test_a_soft_edged_logo_keeps_its_edge_and_its_colour_in_every_mipmap():
    img = soft_logo()
    data = dds.mipmaps(img, 'DXT5', 9)
    assert len(data) == sum(max(1, (256 >> k) // 4) ** 2 * 16 for k in range(9))
    got = levels(data, 'DXT5', 256, 256, 9)
    for k in range(4):                    # (Pillow's encoder alone: 19, 31, 39 and 50)
        want = img if k == 0 else dds.shrink(img, (256 >> k, 256 >> k))
        assert alpha_error(got[k], want) <= (12 if k < 3 else 20), k
        # no white halo: the half-transparent edge stays blue (the ice-white under the transparent part stays out)
        assert all(abs(a - b) <= 12 for a, b in zip(edge_colour(got[k], want), BLUE)), (k, edge_colour(got[k], want))


def test_the_smallest_mipmaps_hold_the_picture():
    data = dds.mipmaps(Image.new('RGBA', (16, 8), (200, 30, 30, 255)), 'DXT1', 5)
    for lv in levels(data, 'DXT1', 16, 8, 5, crop=False):     # 4 x 2, 2 x 1 and 1 x 1 are one block each, all of it
        for x in range(lv.width):                               # the picture (it was transparent black around it)
            for y in range(lv.height):
                r, g, b, a = lv.getpixel((x, y))
                assert a == 255 and max(abs(r - 200), abs(g - 30), abs(b - 30)) <= 8


def test_the_same_picture_gives_the_same_bytes():
    img = soft_logo()
    first = dds.mipmaps(img, 'DXT5', 9)
    dds._ALPHAS.clear()
    dds._COLOURS.clear()
    assert dds.mipmaps(img, 'DXT5', 9) == first                    # blocks remembered from before or not (rule 4)
    assert dds.mipmaps(img, 'DXT5', 9) == first


@pytest.fixture(scope='module')
def utah():
    if not os.path.exists(PACK):
        pytest.skip("no look pack (private/build_looks.py)")
    with zipfile.ZipFile(PACK) as z:
        if 'i/22.webp' not in z.namelist():
            pytest.skip("the look pack has no Utah centre ice")
        img = Image.open(io.BytesIO(z.read('i/22.webp')))
        img.load()
    return img.convert('RGBA')


def test_utahs_centre_ice_from_the_look_pack(utah):
    """The owner's picture (2026-10-18): Utah's centre ice at a slant had stair-step edges and blotches."""
    w, h = utah.size
    got = levels(dds.mipmaps(utah, 'DXT5', 11), 'DXT5', w, h, 11)
    for k in range(4):
        want = utah if k == 0 else dds.shrink(utah, (w >> k, h >> k))
        assert alpha_error(got[k], want) <= (12 if k == 0 else 18), k
        assert all(abs(a - b) <= 6 for a, b in zip(edge_colour(got[k], want), edge_colour(want, want))), k


# --- in the game's files ----------------------------------------------------------------------------------------------
@pytest.fixture(scope='module')
def disc():
    if not DISC or not os.path.exists(DISC):
        pytest.skip("no game disc (set LEGACY_ROSTER_DISC to your NHL Legacy disc image)")
    from legacy_roster.art.lab import Disc
    return Disc(DISC)


@pytest.mark.parametrize('inner', ['rendering/icesurface/centerlogo_22_cm.rpsgl', 'rendering/jersey/texlib_1_22_3.rpsgl'])
def test_every_raster_keeps_its_size_and_mipmaps_and_comes_out_the_same_twice(disc, inner):
    raw = disc.render(inner)
    made = []
    for _ in range(2):
        f = rpsgl.Rpsgl(raw)
        before = {k: dict(r) for k, r in f.rasters.items()}
        for name in f.rasters:                       # colour maps (DXT1), normal maps, number sheet, centre ice (DXT5)
            f.replace(name, f.image(name))
        assert f.rasters == before
        out = f.build()
        assert {k: dict(r) for k, r in rpsgl.Rpsgl(out).rasters.items()} == before
        assert len(rpsgl.unpack(out)) == len(rpsgl.unpack(raw))
        made.append(out)
    assert made[0] == made[1]
    back, own = rpsgl.Rpsgl(made[0]), rpsgl.Rpsgl(raw)
    for name, r in own.rasters.items():
        if r['format'] == 'DXT5' and not name.endswith('_nm'):           # coverage: the game's own picture comes back
            assert alpha_error(back.image(name), own.image(name)) <= 12, name


# --- the centre ice: opaque or clear, as the game's own (lab round 32) ------------------------------------------------
def test_flatten_draws_a_pixel_opaque_in_the_colour_it_shows_over_the_ice():
    img = Image.new('RGBA', (4, 1))
    for x, a in enumerate((0, 40, 200, 255)):
        img.putpixel((x, 0), BLUE + (a,))
    flat = dds.flatten(img, ICE)
    assert [flat.getpixel((x, 0))[3] for x in range(4)] == [0, 0, 255, 255]
    assert flat.getpixel((2, 0))[:3] == tuple(round((b * 200 + i * 55) / 255) for b, i in zip(BLUE, ICE))
    assert flat.getpixel((3, 0))[:3] == BLUE


def test_the_centre_ice_is_opaque_or_clear_in_every_mipmap_and_looks_the_same_over_the_ice():
    """The game draws the ice logo with its alpha as coverage: a pixel short of opaque (the pack's soft edges, its many
    254s) showed a hatch of the ice in the lab. Every level is flattened onto the ice's white."""
    img = soft_logo(256)
    got = levels(dds.mipmaps(img, 'DXT5', 9, flat=ICE), 'DXT5', 256, 256, 9)
    for k, level in enumerate(got[:4]):                  # 256 to 32 pixels; smaller ones are a few blocks
        assert set(level.getchannel('A').getdata()) <= {0, 255}, k
        want = img if k == 0 else dds.shrink(img, level.size)
        over = [Image.alpha_composite(Image.new('RGBA', level.size, ICE + (255,)), p).convert('L') for p in (level, want)]
        assert ImageStat.Stat(ImageChops.difference(*over)).mean[0] < 3, k


def test_utahs_centre_ice_file_is_flattened(utah, disc):
    from legacy_roster.art import looks
    out = rpsgl.Rpsgl(looks.centre_file(disc.render(looks.CENTRE.format(a=22)), 22, None, None, None, utah))
    r = out.rasters['centerlogo_22_cm']
    data = bytes(out.data[r['at']:r['at'] + r['size']])
    for k, level in enumerate(levels(data, 'DXT5', r['width'], r['height'], r['mips'])[:4]):
        assert set(level.getchannel('A').getdata()) <= {0, 255}, k
