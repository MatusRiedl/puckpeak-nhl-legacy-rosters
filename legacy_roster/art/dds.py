"""The DDS images inside the art files (portraits are DXT5, logos plain 32-bit) and the DXT encoder of the 3D textures
(art/rpsgl.py).

Only what the art files use is handled: one surface, no mipmaps unless the template has them (new
images keep the template's header, so sizes and formats always match what the game expects).
Pixels are rows of (r, g, b, a) tuples.

The encoder (docs/notes/centre-ice-quality.md). Pillow's own DXT encoder is fast but rough: its DXT5 alpha always uses
the six-step ramp between the block's lowest and highest alpha and never reaches either end (an edge of 0 and 255 comes
out 52 and 200), and its colour ends are the lowest and highest 5:6:5 numbers, which can put a colour into a block that
none of its pixels has (green and white came out purple). `encode_level` lets Pillow encode a picture, decodes it again
and encodes the blocks it got wrong once more here (`colour_block`, `alpha_block`: ends from the pixels' main axis and a
least-squares refinement, both alpha ramps, colours weighted by how much each pixel shows). `mipmaps` makes the smaller
levels: weighted by alpha where alpha is coverage, and with the colours next to a visible pixel taken from it (no light
or dark fringe once the game blends the levels). Everything here gives the same bytes every time (rule 4).
"""
import io
import re
import struct
from operator import mul as _mul


class Header:
    def __init__(self, dds):
        if dds[:4] != b'DDS ':
            raise ValueError("not a DDS image")
        self.raw = bytes(dds[:128])
        (self.height, self.width, self.pitch, self.depth, self.mipmaps) = struct.unpack_from('<5I', dds, 12)
        self.pf_flags, fourcc, self.bits = struct.unpack_from('<I4sI', dds, 80)
        self.masks = struct.unpack_from('<4I', dds, 92)          # r, g, b, a
        self.fourcc = fourcc.decode('latin1') if self.pf_flags & 4 else None

    @property
    def data_size(self):
        """Bytes of pixel data for the top surface."""
        if self.fourcc in ('DXT1',):
            return max(1, self.width // 4) * max(1, self.height // 4) * 8
        if self.fourcc in ('DXT3', 'DXT5'):
            return max(1, self.width // 4) * max(1, self.height // 4) * 16
        return self.width * self.height * self.bits // 8


def _rgb565(c):
    r, g, b = c[:3]
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def _unpack565(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return (r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31


# --- one block --------------------------------------------------------------------------------------------------------
E5 = [(i * 255 + 15) // 31 for i in range(32)]          # a 5-bit and a 6-bit number as the 0-255 value the game sees
E6 = [(i * 255 + 31) // 63 for i in range(64)]
Q5 = [(v * 31 + 127) // 255 for v in range(256)]
Q6 = [(v * 63 + 127) // 255 for v in range(256)]


def _match_table(levels):
    """For each value 0-255 the two ends (hi, lo) whose 2:1 mix comes nearest to it: a block of one colour is then exact
    or one off, where the nearest 5:6:5 colour can be eight off."""
    ex = [(i * 255 + (levels // 2)) // levels for i in range(levels + 1)]
    out = []
    for v in range(256):
        best = None
        for hi in range(levels + 1):
            for lo in range(max(0, hi - 2), hi + 1):
                err = abs((2 * ex[hi] + ex[lo]) // 3 - v)
                if best is None or err < best[0]:
                    best = (err, hi, lo)
        out.append((best[1], best[2]))
    return out


M5 = _match_table(31)
M6 = _match_table(63)
_STEP4 = (0, 2, 3, 1)               # index of the palette entry 0, 1/3, 2/3, 1 of the way from the first end to the second
_T4 = (0.0, 1.0, 1 / 3, 2 / 3)      # ... and back
_STEP3 = (0, 2, 1)                  # the three-colour mode of DXT1: the ends and their middle (index 3 is transparent)
_T3 = (0.0, 1.0, 0.5)


def _q(v):
    v = int(v + 0.5)
    return 0 if v < 0 else 255 if v > 255 else v


def single_colour(r, g, b):
    """(c0, c1, index bits) of a block of one colour, in the four-colour mode (c0 > c1) or with both ends equal."""
    rh, rl = M5[r]
    gh, gl = M6[g]
    bh, bl = M5[b]
    c0, c1 = rh << 11 | gh << 5 | bh, rl << 11 | gl << 5 | bl
    return (c0, c1, 0xAAAAAAAA) if c0 != c1 else (c0, c1, 0)


_SHIFT2 = tuple(range(0, 32, 2))


def _err_of(rs, gs, bs, ws, colour):
    r0, g0, b0 = colour
    err = 0
    for i in range(16):
        w = ws[i]
        if w:
            er, eg, eb = rs[i] - r0, gs[i] - g0, bs[i] - b0
            err += w * (er * er + eg * eg + eb * eb)
    return err


def _fit(rs, gs, bs, ws, clear, c0, c1):
    """(c0, c1, bits, error) with the ends c0, c1 (5:6:5): four colours (c0 > c1) or, when `clear` marks pixels that
    must be transparent (DXT1), three colours and transparent (c0 <= c1). Equal ends: every shown pixel takes index 0."""
    three = clear is not None
    if (c0 < c1) != three and c0 != c1:
        c0, c1 = c1, c0
    r0, g0, b0 = E5[c0 >> 11], E6[(c0 >> 5) & 63], E5[c0 & 31]
    if c0 == c1:
        bits = 0
        if three:
            for i in range(16):
                if clear[i]:
                    bits |= 3 << (2 * i)
        return c0, c1, bits, _err_of(rs, gs, bs, ws, (r0, g0, b0))
    r1, g1, b1 = E5[c1 >> 11], E6[(c1 >> 5) & 63], E5[c1 & 31]
    if three:
        n, step = 2, _STEP3
        pal = ((r0, g0, b0), (r1, g1, b1), ((r0 + r1) // 2, (g0 + g1) // 2, (b0 + b1) // 2))
    else:
        n, step = 3, _STEP4
        pal = ((r0, g0, b0), (r1, g1, b1), ((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3),
               ((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3))
    dr, dg, db = r1 - r0, g1 - g0, b1 - b0
    k = n / (dr * dr + dg * dg + db * db)
    dr, dg, db = dr * k, dg * k, db * k
    off = 0.5 - (r0 * dr + g0 * dg + b0 * db)
    bits = err = 0
    for sh, r, g, b, w in zip(_SHIFT2, rs, gs, bs, ws):
        s = int(r * dr + g * dg + b * db + off)
        idx = 0 if s <= 0 else 1 if s >= n else step[s]
        bits |= idx << sh
        if w:
            p = pal[idx]
            er, eg, eb = r - p[0], g - p[1], b - p[2]
            err += w * (er * er + eg * eg + eb * eb)
    if three:                                                   # (a transparent pixel weighs nothing)
        for sh, c in zip(_SHIFT2, clear):
            if c:
                bits |= 3 << sh
    return c0, c1, bits, err


def colour_block(rs, gs, bs, ws, clear=None):
    """(c0, c1, index bits, error) of the colour half of a block: 16 red, green and blue values, the weight of each
    pixel (0: it does not count; a DXT5 coverage texture weighs by alpha), `clear` (DXT1 only) the pixels that are
    transparent. The ends lie on the main axis of the pixels' colours and are refined once by least squares."""
    sw = sum(ws)
    if sw:
        wr, wg, wb = list(map(_mul, ws, rs)), list(map(_mul, ws, gs)), list(map(_mul, ws, bs))
        sr, sg, sb = sum(wr), sum(wg), sum(wb)
        srr, sgg, sbb = sum(map(_mul, wr, rs)), sum(map(_mul, wg, gs)), sum(map(_mul, wb, bs))
        srg, srb, sgb = sum(map(_mul, wr, gs)), sum(map(_mul, wr, bs)), sum(map(_mul, wg, bs))
    else:                                                       # nothing shows
        if clear is not None:
            return 0, 0, 0xFFFFFFFF, 0
        c0, c1, bits = single_colour(rs[0], gs[0], bs[0])
        return c0, c1, bits, 0
    mr, mg, mb = sr / sw, sg / sw, sb / sw
    crr, cgg, cbb = srr / sw - mr * mr, sgg / sw - mg * mg, sbb / sw - mb * mb
    if crr + cgg + cbb < 0.25 and clear is None:                # one colour
        c0, c1, bits = single_colour(_q(mr), _q(mg), _q(mb))
        r0, g0, b0 = E5[c0 >> 11], E6[(c0 >> 5) & 63], E5[c0 & 31]
        if c0 != c1:
            r1, g1, b1 = E5[c1 >> 11], E6[(c1 >> 5) & 63], E5[c1 & 31]
            r0, g0, b0 = (2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3
        return c0, c1, bits, _err_of(rs, gs, bs, ws, (r0, g0, b0))
    crg, crb, cgb = srg / sw - mr * mg, srb / sw - mr * mb, sgb / sw - mg * mb
    if crr >= cgg and crr >= cbb:                               # the main axis: power iteration from the longest row
        vr, vg, vb = crr, crg, crb
    elif cgg >= cbb:
        vr, vg, vb = crg, cgg, cgb
    else:
        vr, vg, vb = crb, cgb, cbb
    for _ in range(3):
        vr, vg, vb = crr * vr + crg * vg + crb * vb, crg * vr + cgg * vg + cgb * vb, crb * vr + cgb * vg + cbb * vb
        m = max(abs(vr), abs(vg), abs(vb))
        if not m:
            break
        vr, vg, vb = vr / m, vg / m, vb / m
    n2 = vr * vr + vg * vg + vb * vb
    if n2 < 1e-12:
        vr, vg, vb, n2 = 1.0, 1.0, 1.0, 3.0
    proj = [r * vr + g * vg + b * vb for r, g, b, w in zip(rs, gs, bs, ws) if w]
    lo, hi = min(proj), max(proj)
    base = mr * vr + mg * vg + mb * vb
    lo, hi = (lo - base) / n2, (hi - base) / n2
    c0 = Q5[_q(mr + hi * vr)] << 11 | Q6[_q(mg + hi * vg)] << 5 | Q5[_q(mb + hi * vb)]
    c1 = Q5[_q(mr + lo * vr)] << 11 | Q6[_q(mg + lo * vg)] << 5 | Q5[_q(mb + lo * vb)]
    best = _fit(rs, gs, bs, ws, clear, c0, c1)
    if best[3] > 8 * sw and best[0] != best[1]:              # more than a little off: refine
        # least squares: the ends that fit the chosen indices best
        bits, ts = best[2], (_T3 if clear is not None else _T4)
        nt = len(ts)
        A = B = C = xr = xg = xb = yr = yg = yb = 0.0
        for sh, r, g, b, w in zip(_SHIFT2, rs, gs, bs, ws):
            idx = (bits >> sh) & 3
            if w and idx < nt:
                t = ts[idx]
                wt = w * t
                wu = w - wt
                A += wu - wu * t
                B += wu * t
                C += wt * t
                xr += wu * r
                xg += wu * g
                xb += wu * b
                yr += wt * r
                yg += wt * g
                yb += wt * b
        det = A * C - B * B
        if det > 1e-6:
            c0 = Q5[_q((C * xr - B * yr) / det)] << 11 | Q6[_q((C * xg - B * yg) / det)] << 5 | Q5[_q((C * xb - B * yb) / det)]
            c1 = Q5[_q((A * yr - B * xr) / det)] << 11 | Q6[_q((A * yg - B * xg) / det)] << 5 | Q5[_q((A * yb - B * xb) / det)]
            cand = _fit(rs, gs, bs, ws, clear, c0, c1)
            if cand[3] < best[3]:
                best = cand
    return best


CODE8 = (0, 2, 3, 4, 5, 6, 7, 1)    # the code of each step of the eight-step alpha ramp, from the first end to the second
CODE6 = (0, 2, 3, 4, 5, 1)          # ... of the six-step ramp (code 6 is 0, code 7 is 255)


def _alpha_fit(al, first, second, six):
    """(squared error, code bits) of the 16 alpha values on the ramp from `first` to `second`."""
    n = 5 if six else 7
    codes = CODE6 if six else CODE8
    levels = [((n - j) * first + j * second) // n for j in range(n + 1)]
    k = n / (second - first)
    off = 0.5 - first * k
    bits = err = 0
    for i in range(16):
        a = al[i]
        j = int(a * k + off)
        j = 0 if j < 0 else n if j > n else j
        e = levels[j] - a
        if e < 0:
            e = -e
        if six and (a < e or 255 - a < e):
            if a < 255 - a:
                bits |= 6 << (3 * i)
                err += a * a
            else:
                bits |= 7 << (3 * i)
                err += (255 - a) * (255 - a)
            continue
        bits |= codes[j] << (3 * i)
        err += e * e
    return err, bits


_STEP_OF8 = (0, 7, 1, 2, 3, 4, 5, 6)     # the step of each code (CODE8 backwards)
_STEP_OF6 = (0, 5, 1, 2, 3, 4, -1, -1)   # ... of CODE6; codes 6 and 7 (0 and 255) are no step


def _alpha_ends(al, bits, six):
    """The ends that fit the steps `bits` chose best (least squares), None when they say nothing new."""
    n, step_of = (5, _STEP_OF6) if six else (7, _STEP_OF8)
    A = B = C = X = Y = 0.0
    for i in range(16):
        j = step_of[(bits >> (3 * i)) & 7]
        if j < 0:
            continue
        v = j / n
        u = 1.0 - v
        a = al[i]
        A += u * u
        B += u * v
        C += v * v
        X += u * a
        Y += v * a
    det = A * C - B * B
    if det < 1e-9:
        return None
    f, s = _q((C * X - B * Y) / det), _q((A * Y - B * X) / det)
    if f == s:
        return None
    if (f < s) != six:
        f, s = s, f
    return f, s


def alpha_block(al):
    """(8 bytes, squared error) of the alpha half of a DXT5 block (`al`: 16 values): the eight-step ramp between the
    highest and lowest value, or, when the block holds 0 or 255, the six-step ramp between the values in between with
    0 and 255 exact, whichever is nearer; then its ends refined by least squares."""
    al = bytes(al)
    lo, hi = min(al), max(al)
    if lo == hi:
        return bytes((lo, lo, 0, 0, 0, 0, 0, 0)), 0
    inner = al.translate(None, b'\x00\xff') if lo == 0 or hi == 255 else None
    if inner == b'':                                            # only 0 and 255: exact
        bits = 0
        for i in range(16):
            bits |= (7 if al[i] else 6) << (3 * i)
        return bytes((0, 255)) + bits.to_bytes(6, 'little'), 0
    best = None
    if inner is not None:
        l6, h6 = min(inner), max(inner)
        if l6 == h6:
            h6 = l6 + 1 if l6 < 254 else l6
            l6 = h6 - 1
        best = _alpha_fit(al, l6, h6, True) + (l6, h6, True)
    if best is None or best[0] > 256 and not (lo == 0 and hi == 255 and h6 - l6 <= 182):
        cand = _alpha_fit(al, hi, lo, False) + (hi, lo, False)
        if best is None or cand[0] < best[0]:
            best = cand
    err, bits, first, second, six = best
    for _ in range(2):
        if err <= 144:                                          # good enough: about 3 off per pixel
            break
        ends = _alpha_ends(al, bits, six)
        if ends is None:
            break
        cand = _alpha_fit(al, ends[0], ends[1], six)
        if cand[0] >= err:
            break
        err, bits = cand
        first, second = ends
    return bytes((first, second)) + bits.to_bytes(6, 'little'), err


def _alpha_block(alphas):
    return alpha_block(bytes(alphas))[0]


def _color_block(colors):
    # weighed by alpha, and a transparent pixel a little (a block nothing shows of keeps its colours too)
    c0, c1, bits, _err = colour_block([c[0] for c in colors], [c[1] for c in colors], [c[2] for c in colors],
                                      [(c[3] if len(c) > 3 else 255) + 1 for c in colors])
    return struct.pack('<HHI', c0, c1, bits)


def encode_dxt5(pixels, width, height):
    """DXT5 blocks for an image of `width` x `height` (multiples of 4)."""
    out = bytearray()
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            block = [pixels[by + y][bx + x] for y in range(4) for x in range(4)]
            out += _alpha_block([c[3] for c in block]) + _color_block(block)
    return bytes(out)


def decode_dxt5(data, width, height):
    pixels = [[None] * width for _ in range(height)]
    pos = 0
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            a0, a1 = data[pos], data[pos + 1]
            abits = int.from_bytes(data[pos + 2:pos + 8], 'little')
            ramp = [a0, a1] + ([((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)] if a0 > a1 else
                               [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255])
            c0, c1, cbits = struct.unpack_from('<HHI', data, pos + 8)
            p0, p1 = _unpack565(c0), _unpack565(c1)
            palette = [p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)), tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))]
            for i in range(16):
                y, x = divmod(i, 4)
                pixels[by + y][bx + x] = palette[(cbits >> (2 * i)) & 3] + (ramp[(abits >> (3 * i)) & 7],)
            pos += 16
    return pixels


# --- whole pictures (Pillow) ------------------------------------------------------------------------------------------
COLOUR_SLACK = 12     # a block is encoded again here when Pillow got a pixel's colour more than this far off ...
ALPHA_SLACK = 3       # ... or its alpha


def _pillow_encode(img, fmt):
    buf = io.BytesIO()
    img.save(buf, 'DDS', pixel_format=fmt)
    return buf.getvalue()[128:]


def decode(data, fmt, width, height):
    """The Pillow RGBA picture of `width` x `height` DXT1 / DXT5 blocks."""
    from PIL import Image
    hdr = bytearray(128)
    hdr[0:4] = b'DDS '
    struct.pack_into('<7I', hdr, 4, 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, height, width, 0, 0, 1)
    struct.pack_into('<II4s', hdr, 76, 32, 4, fmt.encode())
    struct.pack_into('<I', hdr, 108, 0x1000)
    img = Image.open(io.BytesIO(bytes(hdr) + bytes(data[:(width // 4) * (height // 4) * (8 if fmt == 'DXT1' else 16)])))
    img.load()
    return img.convert('RGBA')


def _block_max(img):
    """The largest value of each 4 x 4 block of a one-channel picture, as a picture a quarter of its size."""
    from PIL import Image, ImageChops
    m = ImageChops.lighter(img, ImageChops.offset(img, -1, 0))
    m = ImageChops.lighter(m, ImageChops.offset(m, -2, 0))
    m = ImageChops.lighter(m, ImageChops.offset(m, 0, -1))
    m = ImageChops.lighter(m, ImageChops.offset(m, 0, -2))
    w, h = img.size
    return ImageChops.offset(m, 2, 2).resize((w // 4, h // 4), Image.NEAREST)


def _over(threshold):
    return lambda v: 255 if v > threshold else 0


_SET = re.compile(rb'[^\x00]')


def _marked(img, threshold):
    """The positions of the pixels of a one-channel picture above `threshold`."""
    return [m.start() for m in _SET.finditer(img.point(_over(threshold)).tobytes())]


def _block_at(data, p, row):
    return data[p:p + 16] + data[p + row:p + row + 16] + data[p + 2 * row:p + 2 * row + 16] + data[p + 3 * row:p + 3 * row + 16]


def encode_level(img, fmt, coverage=True, colour_slack=COLOUR_SLACK, alpha_slack=ALPHA_SLACK):
    """The DXT1 or DXT5 blocks of the Pillow picture `img` (sides multiples of 4). `coverage`: alpha says how much of a
    pixel shows (its colour counts as much); otherwise alpha is data of its own (normal maps) and every colour counts.
    DXT1 keeps one bit of alpha: below 128 transparent. Pillow encodes first; each block it got more than the slack off
    is encoded here as well and the nearer of the two kept. A slack of None leaves Pillow's blocks as they are."""
    from PIL import ImageChops
    img = img.convert('RGBA')
    w, h = img.size
    sa = img.getchannel('A')
    if fmt == 'DXT1':
        low, _high = sa.getextrema()
        img = img.copy()
        sa = sa.point(lambda v: 255 if v >= 128 else 0) if low < 128 else sa.point(lambda v: 255)
        img.putalpha(sa)
    out = bytearray(_pillow_encode(img, fmt))
    if colour_slack is None and alpha_slack is None:
        return bytes(out)
    dec = decode(out, fmt, w, h)
    sr, sg, sb, _ = img.split()
    dr, dg, db, da = dec.split()
    size, coff = (16, 8) if fmt == 'DXT5' else (8, 0)
    picks = {}
    if colour_slack is not None:
        ec = ImageChops.lighter(ImageChops.lighter(ImageChops.difference(sr, dr), ImageChops.difference(sg, dg)),
                                ImageChops.difference(sb, db))
        if coverage or fmt == 'DXT1':
            ec = ImageChops.multiply(ec, sa)
        for i in _marked(_block_max(ec), colour_slack):
            picks[i] = 1
    if fmt == 'DXT1' or alpha_slack is not None:
        alpha_off = _block_max(ImageChops.difference(sa, da))
        if fmt == 'DXT1':                                       # a transparent pixel Pillow missed (or made up)
            for i in _marked(alpha_off, 0):
                picks[i] = picks.get(i, 0) | 1
        else:
            for i in _marked(alpha_off, alpha_slack):
                picks[i] = picks.get(i, 0) | 2
    if not picks:
        return bytes(out)
    src, got = img.tobytes(), dec.tobytes()
    bw, row = w // 4, w * 4
    kind = b'1' if fmt == 'DXT1' else b'c' if coverage else b'd'
    for idx, what in picks.items():
        by, bx = divmod(idx, bw)
        p = by * 4 * row + bx * 16
        px, old = _block_at(src, p, row), _block_at(got, p, row)
        al = px[3::4]
        if what & 1:
            key = px + kind
            mine = _COLOURS.get(key)
            if mine is None:
                mine = _colour_of(px, al, fmt, coverage)
                _remember(_COLOURS, key, mine)
            new, err, ws = mine
            if new is not None:
                if fmt == 'DXT1' and old[3::4] != al:          # Pillow's block shows the wrong pixels
                    out[idx * size + coff:idx * size + coff + 8] = new
                elif err < _err_of_pixels(px, old, ws):
                    out[idx * size + coff:idx * size + coff + 8] = new
        if what & 2:
            mine = _ALPHAS.get(al)
            if mine is None:
                mine = alpha_block(al)
                _remember(_ALPHAS, al, mine)
            out[idx * size:idx * size + 8] = mine[0]       # (nearer than Pillow's but in 1 block of 400, by a hair)
    return bytes(out)


# blocks already encoded, by their pixels: the jerseys' number sheets share one alpha, the logos their edges. Pure
# functions of the pixels, so the bytes do not depend on what was encoded before.
_ALPHAS = {}
_COLOURS = {}
_ROOM = 1 << 17


def _remember(memo, key, value):
    if len(memo) >= _ROOM:
        memo.clear()
    memo[key] = value


_ONES = b'\x01' * 16


def _colour_of(px, al, fmt, coverage):
    """(the 8 bytes of a colour half, its error, the pixels' weights) for the 16 RGBA pixels `px`; bytes None when DXT1's
    transparent pixels would not come out right."""
    if fmt == 'DXT1':
        clear = [a < 128 for a in al] if 0 in al else None
        ws = bytes(0 if c else 1 for c in clear) if clear else _ONES
    else:
        clear, ws = None, (al if coverage else _ONES)
    c0, c1, bits, err = colour_block(px[0::4], px[1::4], px[2::4], ws, clear)
    if fmt == 'DXT1' and not all((((bits >> (2 * i)) & 3) == 3 and c0 <= c1) == (al[i] < 128) for i in range(16)):
        return None, err, ws
    return struct.pack('<HHI', c0, c1, bits), err, ws


def _err_of_pixels(px, got, ws):
    err = 0
    for i in range(16):
        w = ws[i]
        if w:
            o = 4 * i
            er, eg, eb = px[o] - got[o], px[o + 1] - got[o + 1], px[o + 2] - got[o + 2]
            err += w * (er * er + eg * eg + eb * eb)
    return err


def bleed(img, band=3):
    """`img` with the colour of each transparent pixel within `band` pixels of one that shows taken from the pixels that
    show around it (pushed down and pulled up the picture's own alpha-weighted halvings); the other transparent pixels
    keep theirs. The game blends a texture with its alpha, so the colour under a transparent pixel next to the logo is
    seen at the logo's edge once the GPU filters between pixels and mipmaps."""
    from PIL import Image, ImageChops, ImageFilter
    alpha = img.getchannel('A')
    if alpha.getextrema()[0] > 0:
        return img
    shows = alpha.point(_over(0))
    if shows.getextrema()[1] == 0:
        return img
    steps = [img]
    while steps[-1].width > 1 or steps[-1].height > 1:
        p = steps[-1]
        steps.append(p.resize((max(1, p.width // 2), max(1, p.height // 2)), Image.BOX))
    fill = steps[-1].convert('RGB')
    for p in reversed(steps[:-1]):
        fill = Image.composite(p.convert('RGB'), fill.resize(p.size, Image.BILINEAR), p.getchannel('A').point(_over(0)))
    near = shows.filter(ImageFilter.BoxBlur(band)).point(_over(0))
    rgb = Image.composite(fill, img.convert('RGB'), ImageChops.subtract(near, shows))
    rgb.putalpha(alpha)
    return rgb


def shrink(img, size, coverage=True):
    """`img` made `size` with a box filter. Where alpha is coverage the colours are weighted by it (a transparent pixel's
    colour does not leak into the edge), and the pixels left transparent keep the plain average of the colours under
    them; where alpha is data every channel is averaged on its own."""
    return _shrinker(img.convert('RGBA'), coverage)(size)


def _shrinker(img, coverage):
    from PIL import Image
    if not coverage:
        channels = img.split()
        return lambda size: Image.merge('RGBA', [c.resize(size, Image.BOX) for c in channels])
    if img.getchannel('A').getextrema()[0] == 255:
        return lambda size: img.resize(size, Image.BOX)
    plain = img.convert('RGB')

    def make(size):
        out = img.resize(size, Image.BOX)                       # Pillow weights the colours by alpha
        alpha = out.getchannel('A')
        if alpha.getextrema()[0] == 0:
            rgb = Image.composite(out.convert('RGB'), plain.resize(size, Image.BOX), alpha.point(_over(0)))
            rgb.putalpha(alpha)
            out = rgb
        return out
    return make


FLAT_CUT = 64           # flatten: alpha from which a pixel is drawn (128 broke thin lines into dots in the small levels)


def flatten(img, ground, cut=FLAT_CUT):
    """`img` (RGBA) as the game's own centre ices are: opaque where alpha is at least `cut`, there in its colour mixed
    with `ground` by its alpha (what blending it over that colour would show), clear elsewhere. In lab round 32 a pixel
    short of opaque showed a hatch of the ice through it (the pack's logos have wide soft edges and many 254s, Utah's ring
    came out hatched; most likely alpha drawn as coverage, not proven); the game's own are an opaque ice-white disc."""
    from PIL import Image
    img = img.convert('RGBA')
    alpha = img.getchannel('A')
    out = Image.composite(img.convert('RGB'), Image.new('RGB', img.size, tuple(ground)), alpha)
    out.putalpha(alpha.point(lambda v: 255 if v >= cut else 0))
    return out


def mipmaps(img, fmt, mips, coverage=True, colour_slack=COLOUR_SLACK, alpha_slack=ALPHA_SLACK, flat=None):
    """The blocks of `img` and its `mips` - 1 smaller levels, one after the other, as the game's textures store them
    (a level smaller than 4 pixels is one block holding it repeated). `flat`: every level flattened onto that colour
    (flatten), made from the unflattened picture."""
    from PIL import Image
    img = img.convert('RGBA')
    w, h = img.size
    smaller = _shrinker(img, coverage)
    out = bytearray()
    for k in range(mips):
        lw, lh = max(1, w >> k), max(1, h >> k)
        level = img if k == 0 else smaller((lw, lh))
        if lw < 4 or lh < 4:                                    # the last levels are one block
            tile = Image.new('RGBA', (4, 4))
            for y in range(0, 4, lh):
                for x in range(0, 4, lw):
                    tile.paste(level, (x, y))
            level = tile
        if flat is not None:
            level = flatten(level, flat)
        if coverage and fmt == 'DXT5':
            level = bleed(level)
        out += encode_level(level, fmt, coverage, colour_slack, alpha_slack)
    return bytes(out)


def encode_rgba32(pixels, header):
    """Plain 32-bit pixels in the channel order the template's masks give."""
    shifts = [(m & -m).bit_length() - 1 for m in header.masks]
    out = bytearray()
    for row in pixels:
        for c in row:
            out += struct.pack('<I', sum(v << s for v, s in zip(c, shifts)))
    return bytes(out)


def decode_rgba32(data, header):
    shifts = [(m & -m).bit_length() - 1 for m in header.masks]
    rows = []
    for y in range(header.height):
        row = []
        for x in range(header.width):
            v = struct.unpack_from('<I', data, (y * header.width + x) * 4)[0]
            row.append(tuple((v >> s) & 255 for s in shifts))
        rows.append(row)
    return rows


def build(template, pixels):
    """A DDS like `template` (the bytes of an existing one) holding `pixels` (its own size)."""
    h = Header(template)
    if len(pixels) != h.height or len(pixels[0]) != h.width:
        raise ValueError(f"the image must be {h.width} x {h.height}")
    body = encode_dxt5(pixels, h.width, h.height) if h.fourcc == 'DXT5' else encode_rgba32(pixels, h)
    rest = template[128 + h.data_size:]        # smaller surfaces (mipmaps), if the template has them
    if rest:
        raise ValueError("templates with mipmaps are not supported yet")
    return h.raw + body


def read(dds):
    """(width, height, pixels) of a DDS from an art file."""
    h = Header(dds)
    body = dds[128:128 + h.data_size]
    pixels = decode_dxt5(body, h.width, h.height) if h.fourcc == 'DXT5' else decode_rgba32(body, h)
    return h.width, h.height, pixels
