"""PARAM.SFO reader/writer.

Layout (little-endian): "\\0PSF", version, key-table offset, data-table offset, entry count, then
16-byte index entries (key offset u16, format u16, length u32, max length u32, data offset u32).
Strings may be changed to any value that fits their max length; the file size never changes.
"""
import struct

FMT_STRING = 0x0204   # NUL-terminated UTF-8
FMT_SPECIAL = 0x0004  # UTF-8 without terminator
FMT_INT = 0x0404


class Sfo:
    def __init__(self, data):
        self.b = bytearray(data)
        magic, _ver, kstart, dstart, n = struct.unpack_from('<4sIIII', self.b, 0)
        if magic != b'\0PSF':
            raise ValueError("not a PARAM.SFO file")
        self.entries = {}  # key -> (index position, format, length, max length, data offset)
        for i in range(n):
            pos = 20 + i * 16
            koff, fmt, dlen, dmax, doff = struct.unpack_from('<HHIII', self.b, pos)
            key = self.b[kstart + koff:self.b.index(0, kstart + koff)].decode()
            self.entries[key] = (pos, fmt, dlen, dmax, dstart + doff)

    @classmethod
    def new(cls, items, version=0x101):
        """A PARAM.SFO made from scratch: `items` [(key, format, value bytes, max length)], in
        the order they are stored (the key table is padded to four bytes, as the game's are)."""
        keys = b''.join(k.encode() + b'\0' for k, *_ in items)
        keys += b'\0' * (-len(keys) % 4)
        kstart = 20 + 16 * len(items)
        dstart = kstart + len(keys)
        index, data, koff = bytearray(), bytearray(), 0
        for key, fmt, value, dmax in items:
            index += struct.pack('<HHIII', koff, fmt, len(value), dmax, len(data))
            data += value + b'\0' * (dmax - len(value))
            koff += len(key) + 1
        return cls(struct.pack('<4sIIII', b'\0PSF', version, kstart, dstart, len(items)) + index + keys + data)

    @classmethod
    def load(cls, path):
        with open(path, 'rb') as f:
            return cls(f.read())

    def get(self, key, default=None):
        if key not in self.entries:
            return default
        _pos, fmt, dlen, _dmax, off = self.entries[key]
        raw = bytes(self.b[off:off + dlen])
        if fmt in (FMT_STRING, FMT_SPECIAL):
            return raw.rstrip(b'\0').decode('utf-8', 'replace')
        return raw

    def max_len(self, key):
        """Longest string (in UTF-8 bytes) the entry can hold."""
        return self.entries[key][3] - 1

    def set_str(self, key, value):
        pos, fmt, _dlen, dmax, off = self.entries[key]
        if fmt != FMT_STRING:
            raise ValueError(f"{key} is not a string entry")
        enc = value.encode('utf-8') + b'\0'
        if len(enc) > dmax:
            raise ValueError(f"{key}: '{value}' is longer than {dmax - 1} bytes")
        self.b[off:off + dmax] = enc + b'\0' * (dmax - len(enc))
        struct.pack_into('<I', self.b, pos + 4, len(enc))
        self.entries[key] = (pos, fmt, len(enc), dmax, off)

    def to_bytes(self):
        return bytes(self.b)

    def save(self, path):
        with open(path, 'wb') as f:
            f.write(self.b)
