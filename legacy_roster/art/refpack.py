"""EA RefPack ("QFS") compression, used for the images inside the game's art files.

Stream: 0x10 0xFB, the unpacked size (3 bytes, big-endian), then commands. Each command copies
0-3 (or a run of up to 112) literal bytes from the stream and then, for copy commands, a run of
earlier output:

    0xxxxxxx yyyyyyyy                    copy 3-10 bytes from up to 1,024 back, 0-3 literals first
    10xxxxxx yyyyyyyy yyyyyyyy           copy 4-67 bytes from up to 16,384 back
    110xxxxx yyyyyyyy yyyyyyyy zzzzzzzz  copy 5-1,028 bytes from up to 131,072 back
    111xxxxx (0xE0-0xFB)                 4-112 literals
    111111xx (0xFC-0xFF)                 0-3 literals, end
"""

MAGIC = b'\x10\xfb'


def unpacked_size(data):
    if data[:2] != MAGIC:
        raise ValueError("not a RefPack stream")
    return int.from_bytes(data[2:5], 'big')


def decompress(data):
    size = unpacked_size(data)
    out = bytearray()
    pos = 5
    while len(out) < size:
        b0 = data[pos]
        if b0 < 0x80:
            b1 = data[pos + 1]
            pos += 2
            lit, length, back = b0 & 3, ((b0 & 0x1C) >> 2) + 3, ((b0 & 0x60) << 3) + b1 + 1
        elif b0 < 0xC0:
            b1, b2 = data[pos + 1], data[pos + 2]
            pos += 3
            lit, length, back = (b1 >> 6) & 3, (b0 & 0x3F) + 4, ((b1 & 0x3F) << 8) + b2 + 1
        elif b0 < 0xE0:
            b1, b2, b3 = data[pos + 1], data[pos + 2], data[pos + 3]
            pos += 4
            lit, length, back = b0 & 3, ((b0 & 0x0C) << 6) + b3 + 5, ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif b0 < 0xFC:
            n = ((b0 & 0x1F) + 1) << 2
            out += data[pos + 1:pos + 1 + n]
            pos += 1 + n
            continue
        else:
            n = b0 & 3
            out += data[pos + 1:pos + 1 + n]
            break
        out += data[pos:pos + lit]
        pos += lit
        start = len(out) - back
        for k in range(length):            # byte by byte: a copy may overlap what it writes
            out.append(out[start + k])
    if len(out) != size:
        raise ValueError(f"RefPack stream gave {len(out)} bytes, header says {size}")
    return bytes(out)


def _literals(out, data, start, end):
    """Emit data[start:end] as literal runs, leaving 0-3 bytes for the next command. Returns the new start."""
    while end - start >= 4:
        n = min((end - start) & ~3, 112)
        out.append(0xE0 + (n >> 2) - 1)
        out += data[start:start + n]
        start += n
    return start


def compress(data):
    """RefPack-compress `data` (greedy matching, deterministic)."""
    data = bytes(data)
    n = len(data)
    if n >= 1 << 24:
        raise ValueError("too large for a 3-byte RefPack size")
    out = bytearray(MAGIC + n.to_bytes(3, 'big'))
    last = {}                               # 3-byte sequence -> last position it started at
    pos = lit = 0
    while pos + 3 <= n:
        key = data[pos:pos + 3]
        cand = last.get(key)
        last[key] = pos
        length = 0
        if cand is not None and pos - cand <= 131072:
            limit = min(1028, n - pos)
            length = 3
            while length < limit and data[cand + length] == data[pos + length]:
                length += 1
        back = pos - cand if length else 0
        if length < 3 or (length == 3 and back > 1024) or (length == 4 and back > 16384):
            pos += 1
            continue
        lit = _literals(out, data, lit, pos)
        k = pos - lit                       # 0-3 literals ride along with the copy
        if length <= 10 and back <= 1024:
            out += bytes(((((back - 1) >> 3) & 0x60) | ((length - 3) << 2) | k, (back - 1) & 0xFF))
        elif length <= 67 and back <= 16384:
            out += bytes((0x80 | (length - 4), (k << 6) | ((back - 1) >> 8), (back - 1) & 0xFF))
        else:
            out += bytes((0xC0 | (((back - 1) >> 12) & 0x10) | (((length - 5) >> 6) & 0x0C) | k,
                          ((back - 1) >> 8) & 0xFF, (back - 1) & 0xFF, (length - 5) & 0xFF))
        out += data[lit:pos]
        for p in range(pos + 1, min(pos + length, n - 2)):     # remember the copied stretch too
            last[data[p:p + 3]] = p
        pos += length
        lit = pos
    lit = _literals(out, data, lit, n)
    out.append(0xFC + (n - lit))
    out += data[lit:n]
    return bytes(out)
