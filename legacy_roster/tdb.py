"""NHL Legacy (PS3, BLES02153 / BLUS31540) roster save reader/writer.

SYS-DATA layout (big-endian unless noted):
  0x00  16-byte magic, e.g. "PS3RosterFile"
  0x10  CRC-32 (standard zlib) over [0x1C, end of file)
  0x14  version (4), 0x18 zero, 0x1C compressed flag, 0x20 unknown
  0x24  section size
  0x28  CRC-32/BZIP2 over [0x2C, 0x2C + section size)
  0x2C  section: u32 LE zlib length + zlib stream (or raw DB when uncompressed), zero padded

Inside is an EA "TDB" database: "DB" header (CRC-32/MPEG-2 over bytes 0..0x14), a table
index, then per table a 40-byte header (CRC-32/MPEG-2 over header bytes 4..0x24), 16-byte
field definitions and fixed-length, big-endian bit-packed records.
Each table's first 4 bytes chain the tables together: CRC-32/MPEG-2 of the table index for
the first table, of the previous table's bytes from 0x28 on for the others; the last table
ends with the CRC of its own bytes from 0x28 on. The game silently rejects a roster whose
chain is broken.

Table and field names in the file are scrambled 4-character tags. The game's own schema
(db/nhlng-meta.xml on the disc) gives their real names; when schema_names is available every
table accepts either the tag or the real name (`t.get(i, 'lastname')` == `t.get(i, 'RMbQ')`).
"""
import csv
import os
import struct
import sys
import zlib

try:
    from .schema_names import FIELDS as _FIELD_NAMES, TABLES as _TABLE_NAMES
except ImportError:  # schema not generated yet: tags only
    _FIELD_NAMES, _TABLE_NAMES = {}, {}

ROSTER_MAGIC = b'PS3RosterFile'

_CRC_TABLE = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if _c & 0x80000000 else (_c << 1) & 0xFFFFFFFF
    _CRC_TABLE.append(_c)


def crc32_mpeg2(data, crc=0xFFFFFFFF):
    for x in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ _CRC_TABLE[((crc >> 24) ^ x) & 0xFF]
    return crc


def crc32_bzip2(data):
    return crc32_mpeg2(data) ^ 0xFFFFFFFF


class Field:
    def __init__(self, ftype, offset, name, bits):
        self.type, self.offset, self.name, self.bits = ftype, offset, name, bits
        # the bytes of a record that hold this field, and the shift inside them
        self.b0 = offset // 8
        self.b1 = (offset + bits + 7) // 8
        self.shift = self.b1 * 8 - offset - bits
        self.mask = (1 << bits) - 1

    @property
    def is_string(self):
        return self.type == 0


class Table:
    def __init__(self, name, raw):
        self.name = name
        self.header = bytearray(raw[:0x28])
        self.rec_len = struct.unpack_from('>I', raw, 8)[0]
        self.max_rec, self.cur_rec = struct.unpack_from('>HH', raw, 0x14)
        nf = raw[0x1C]
        self.field_defs = bytes(raw[0x28:0x28 + nf * 16])
        self.fields = {}
        for k in range(nf):
            t, off, nm, bits = struct.unpack_from('>II4sI', self.field_defs, k * 16)
            self.fields[nm.decode('latin1')] = Field(t, off, nm.decode('latin1'), bits)
        r0 = 0x28 + nf * 16
        self.records = bytearray(raw[r0:r0 + self.max_rec * self.rec_len])
        self.tail = bytes(raw[r0 + self.max_rec * self.rec_len:])
        self.rec_bits = self.rec_len * 8
        # real names from the game's schema: 'lastname' -> 'RMbQ'
        self.real_name = _TABLE_NAMES.get(name, name)
        self.alias = {real: tag for tag, real in _FIELD_NAMES.get(name, {}).items() if tag in self.fields}

    def field(self, fname):
        """Field by tag ('RMbQ') or real name ('lastname')."""
        f = self.fields.get(fname)
        if f is None:
            f = self.fields[self.alias[fname]]
        return f

    def has(self, fname):
        return fname in self.fields or fname in self.alias

    # --- record access -------------------------------------------------
    def get(self, i, fname):
        f = self.fields.get(fname) or self.field(fname)
        a = i * self.rec_len
        if f.type == 0:
            raw = self.records[a + f.offset // 8:a + (f.offset + f.bits) // 8]
            return raw.split(b'\0', 1)[0].decode('utf-8', 'replace')
        return (int.from_bytes(self.records[a + f.b0:a + f.b1], 'big') >> f.shift) & f.mask

    def set(self, i, fname, value):
        f = self.fields.get(fname) or self.field(fname)
        a = i * self.rec_len
        if f.type == 0:
            n = f.bits // 8
            enc = value.encode('utf-8')
            if len(enc) >= n:
                raise ValueError(f"{self.name}.{fname}: '{value}' longer than {n - 1} bytes")
            s = f.offset // 8
            self.records[a + s:a + s + n] = enc + b'\0' * (n - len(enc))
            return
        if not 0 <= value <= f.mask:
            raise ValueError(f"{self.name}.{fname}: {value} does not fit in {f.bits} bits")
        v = int.from_bytes(self.records[a + f.b0:a + f.b1], 'big')
        v = (v & ~(f.mask << f.shift)) | (value << f.shift)
        self.records[a + f.b0:a + f.b1] = v.to_bytes(f.b1 - f.b0, 'big')

    def row(self, i):
        return {n: self.get(i, n) for n in self.fields}

    def rows(self):
        return [self.row(i) for i in range(self.cur_rec)]

    def column(self, fname):
        """All current values of one field (much faster than get() in a loop over other code)."""
        return [self.get(i, fname) for i in range(self.cur_rec)]

    def find(self, **match):
        return [i for i in range(self.cur_rec) if all(self.get(i, k) == v for k, v in match.items())]

    def record_bytes(self, i):
        a = i * self.rec_len
        return bytes(self.records[a:a + self.rec_len])

    def add_record(self, values=None, template=None):
        """Append a record (copy of `template` index if given) and return its index."""
        if self.cur_rec >= self.max_rec:
            raise ValueError(f"{self.name}: table full ({self.max_rec})")
        i = self.cur_rec
        a = i * self.rec_len
        if template is not None:
            ta = template * self.rec_len
            self.records[a:a + self.rec_len] = self.records[ta:ta + self.rec_len]
        else:
            self.records[a:a + self.rec_len] = bytes(self.rec_len)
        self.cur_rec += 1
        for k, v in (values or {}).items():
            self.set(i, k, v)
        return i

    def delete_record(self, i):
        """Remove record `i`, shifting later records down (table order is not significant)."""
        if not 0 <= i < self.cur_rec:
            raise IndexError(f"{self.name}: no record {i}")
        a, end = i * self.rec_len, self.cur_rec * self.rec_len
        self.records[a:end - self.rec_len] = self.records[a + self.rec_len:end]
        self.records[end - self.rec_len:end] = bytes(self.rec_len)
        self.cur_rec -= 1

    # --- serialisation -------------------------------------------------
    def build(self):
        h = bytearray(self.header)
        struct.pack_into('>HH', h, 0x14, self.max_rec, self.cur_rec)
        struct.pack_into('>I', h, 0x24, crc32_mpeg2(h[4:0x24]))
        return bytes(h) + self.field_defs + bytes(self.records) + self.tail


class RosterFile:
    def __init__(self, path=None, data=None):
        self.path = path
        if data is None:
            with open(path, 'rb') as f:
                data = f.read()
        self.raw = bytes(data)
        b = self.raw
        self.magic = b[:0x10]
        if len(b) < 0x30:
            raise ValueError("file too short to be a save")
        self.compressed = struct.unpack_from('>I', b, 0x1C)[0] != 0
        self.section_size = struct.unpack_from('>I', b, 0x24)[0]
        stored = struct.unpack_from('>I', b, 0x28)[0]
        if crc32_bzip2(b[0x2C:0x2C + self.section_size]) != stored:
            raise ValueError("section CRC mismatch -- not a supported save")
        if self.compressed:
            zlen = struct.unpack_from('<I', b, 0x2C)[0]
            self.zlib_len = zlen
            db = zlib.decompress(b[0x30:0x30 + zlen])
        else:
            db = b[0x2C:0x2C + self.section_size]
        self._parse_db(db)

    @classmethod
    def from_db(cls, db, section_size, magic=ROSTER_MAGIC, version=4, counter=1):
        """A roster save around a bare database (the game's own, stock.py): a PS3RosterFile wrapper
        of `section_size`, compressed. Everything that depends on the content (sizes, the CRCs) is
        filled in by build()."""
        self = cls.__new__(cls)
        self.path = None
        raw = bytearray(0x2C + section_size)
        raw[:0x10] = magic.ljust(0x10, b'\0')
        struct.pack_into('>IIIII', raw, 0x14, version, 0, 1, counter, section_size)
        self.raw = bytes(raw)
        self.magic = self.raw[:0x10]
        self.compressed = True
        self.section_size = section_size
        self._parse_db(db)
        return self

    @property
    def is_roster(self):
        return self.magic.startswith(ROSTER_MAGIC)

    def _parse_db(self, db):
        self.db_header = bytearray(db[:0x18])
        if self.db_header[:2] != b'DB':
            raise ValueError("no DB header")
        if crc32_mpeg2(db[:0x14]) != struct.unpack_from('>I', db, 0x14)[0]:
            raise ValueError("DB header CRC mismatch")
        dbsize = struct.unpack_from('>I', db, 8)[0]
        n = struct.unpack_from('>I', db, 0x10)[0]
        start = 0x18 + n * 8
        index = [(db[0x18 + i * 8:0x1C + i * 8].decode('latin1'),
                  struct.unpack_from('>I', db, 0x1C + i * 8)[0]) for i in range(n)]
        self.order = [nm for nm, _ in index]
        self.tables = {}
        for i, (nm, off) in enumerate(index):
            end = start + (index[i + 1][1] if i + 1 < n else dbsize - start)
            t = Table(nm, db[start + off:end])
            if crc32_mpeg2(t.header[4:0x24]) != struct.unpack_from('>I', t.header, 0x24)[0]:
                raise ValueError(f"table {nm} header CRC mismatch")
            self.tables[nm] = t
        self.db_trailer = bytes(db[dbsize:])

    def __getitem__(self, name):
        return self.tables[name]

    def build_db(self):
        built = [bytearray(self.tables[nm].build()) for nm in self.order]
        # checksum chain: each table's first 4 bytes hold the CRC of what precedes it --
        # the table index for table 0, otherwise the previous table's bytes from 0x28 on.
        # The last table's 4-byte tail is the CRC of its own bytes from 0x28 on.
        index = bytearray()
        pos = 0
        for nm, raw in zip(self.order, built):
            index += nm.encode('latin1') + struct.pack('>I', pos)
            pos += len(raw)
        prev = bytes(index)
        for raw in built:
            struct.pack_into('>I', raw, 0, crc32_mpeg2(prev))
            prev = bytes(raw[0x28:])
        last = self.tables[self.order[-1]]
        if len(last.tail) == 4:
            struct.pack_into('>I', built[-1], len(built[-1]) - 4, crc32_mpeg2(built[-1][0x28:-4]))
        body = b''.join(built)
        h = bytearray(self.db_header)
        dbsize = 0x18 + len(index) + len(body)
        struct.pack_into('>I', h, 8, dbsize)
        struct.pack_into('>I', h, 0x10, len(self.order))
        struct.pack_into('>I', h, 0x14, crc32_mpeg2(h[:0x14]))
        return bytes(h) + bytes(index) + bytes(body) + self.db_trailer

    def build(self, level=6):
        db = self.build_db()
        if self.compressed:
            # level 6 / memLevel 9 reproduces the game's own output byte-for-byte
            c = zlib.compressobj(level, zlib.DEFLATED, 15, 9)
            z = c.compress(db) + c.flush()
            section = struct.pack('<I', len(z)) + z
        else:
            section = db
        if len(section) > self.section_size:
            raise ValueError("data no longer fits in the save section")
        section += b'\0' * (self.section_size - len(section))
        out = bytearray(self.raw)
        out[0x2C:0x2C + self.section_size] = section
        struct.pack_into('>I', out, 0x28, crc32_bzip2(section))
        struct.pack_into('>I', out, 0x10, zlib.crc32(out[0x1C:]))
        return bytes(out)

    def save(self, path, level=6):
        data = self.build(level)
        with open(path, 'wb') as f:
            f.write(data)
        return data

    def export_csv(self, folder, real_names=True):
        """Dump every table to <folder>/<tag>[_<realname>].csv (header: field(bits))."""
        os.makedirs(folder, exist_ok=True)
        for nm in self.order:
            t = self.tables[nm]
            names = sorted(t.fields, key=lambda n: t.fields[n].offset)
            real = _FIELD_NAMES.get(nm, {}) if real_names else {}
            fn = f"{nm}_{t.real_name}.csv" if real_names and t.real_name != nm else f"{nm}.csv"
            with open(os.path.join(folder, fn), 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['#'] + [f"{real.get(n, n)}({t.fields[n].bits})" for n in names])
                for i in range(t.cur_rec):
                    w.writerow([i] + [t.get(i, n) for n in names])


def check_chain(raw):
    """Verify the header CRC and the table checksum chain of a built save. Returns problems."""
    problems = []
    if struct.unpack_from('>I', raw, 0x10)[0] != zlib.crc32(raw[0x1C:]):
        problems.append("header CRC at 0x10 is wrong")
    db = zlib.decompress(raw[0x30:0x30 + struct.unpack_from('<I', raw, 0x2C)[0]])
    ntab = struct.unpack_from('>I', db, 0x10)[0]
    tstart, dbsize = 0x18 + ntab * 8, struct.unpack_from('>I', db, 8)[0]
    offs = [tstart + struct.unpack_from('>I', db, 0x1C + i * 8)[0] for i in range(ntab)] + [dbsize]
    prev = db[0x18:tstart]
    for k in range(ntab):
        a, e = offs[k], offs[k + 1]
        if struct.unpack_from('>I', db, a)[0] != crc32_mpeg2(prev):
            problems.append(f"table {db[0x18 + k * 8:0x1C + k * 8].decode('latin1')} checksum chain broken")
        prev = db[a + 0x28:e]
    if crc32_mpeg2(prev) != 0:  # last table ends with the CRC of its own body
        problems.append("last table's closing CRC is wrong")
    return problems


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == 'export':
        RosterFile(sys.argv[2]).export_csv(sys.argv[3] if len(sys.argv) > 3 else 'export')
    else:
        print("usage: python -m legacy_roster.tdb export <SYS-DATA> [out_folder]")
