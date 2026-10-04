"""The DDS images inside the art files: portraits are DXT5, logos plain 32-bit.

Only what the art files use is handled: one surface, no mipmaps unless the template has them (new
images keep the template's header, so sizes and formats always match what the game expects).
Pixels are rows of (r, g, b, a) tuples.
"""
import struct


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


def _alpha_block(alphas):
    a0, a1 = max(alphas), min(alphas)
    if a0 == a1:
        return bytes((a0, a1)) + b'\0' * 6
    # eight-step ramp between a0 and a1 (codes 0, 1 are the ends, 2-7 the steps between)
    ramp = [a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
    bits = 0
    for i, a in enumerate(alphas):
        code = min(range(8), key=lambda c: abs(ramp[c] - a))
        bits |= code << (3 * i)
    return bytes((a0, a1)) + bits.to_bytes(6, 'little')


def _color_block(colors):
    lum = lambda c: c[0] * 299 + c[1] * 587 + c[2] * 114
    hi, lo = max(colors, key=lum), min(colors, key=lum)
    c0, c1 = _rgb565(hi), _rgb565(lo)
    if c0 < c1:
        c0, c1 = c1, c0
        hi, lo = lo, hi
    if c0 == c1:
        return struct.pack('<HHI', c0, c1, 0)
    p0, p1 = _unpack565(c0), _unpack565(c1)
    palette = [p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)), tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))]
    bits = 0
    for i, c in enumerate(colors):
        code = min(range(4), key=lambda k: sum((x - y) ** 2 for x, y in zip(palette[k], c[:3])))
        bits |= code << (2 * i)
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
