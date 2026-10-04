"""Read files out of the NHL Legacy game disc (the player's own copy) without extracting it.

Two layers:
  * IsoImage      -- a decrypted PS3 disc image (ISO 9660 / Joliet)
  * EbArchive     -- EA "EB" v3 archives (boot.big, cache.big, nocache.big, cacheboot.big, ...)

EB v3 layout (big-endian):
  0x00 "EB", u16 version (3), u32 file count, u32 0x400, u32 names offset, u32 names size,
       u8 file-name record length, u8 folder-name record length, u16 folder count
  0x30 file table: per file u32 offset (in 16-byte units), u32 packed size (0 = stored),
       u32 size, u32 name hash; followed by one byte per file
  names: per file u16 folder index + name; then (16-byte aligned) the folder names
"""
import os
import struct

SECTOR = 2048


class IsoImage:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'rb')
        pvd = svd = None
        for k in range(16, 32):
            self.f.seek(k * SECTOR)
            d = self.f.read(SECTOR)
            if d[1:6] != b'CD001' or d[0] == 255:
                break
            if d[0] == 1:
                pvd = d
            elif d[0] == 2 and d[88:91] in (b'%/@', b'%/C', b'%/E'):
                svd = d
        if pvd is None:
            raise ValueError("not an ISO 9660 image")
        self.joliet = svd is not None
        vd = svd or pvd
        self.files = {}  # '/PS3_GAME/USRDIR/boot.big' -> (offset, size)
        self._walk(struct.unpack_from('<I', vd, 158)[0], struct.unpack_from('<I', vd, 166)[0], '')

    def _records(self, lba, size):
        self.f.seek(lba * SECTOR)
        data = self.f.read(size)
        pos = 0
        while pos < len(data):
            n = data[pos]
            if n == 0:  # records never span sectors
                pos = (pos // SECTOR + 1) * SECTOR
                continue
            r = data[pos:pos + n]
            pos += n
            name = r[33:33 + r[32]]
            if name in (b'\x00', b'\x01'):
                continue
            text = name.decode('utf-16-be') if self.joliet else name.decode('latin1')
            yield text.split(';')[0], struct.unpack_from('<I', r, 2)[0], struct.unpack_from('<I', r, 10)[0], r[25]

    def _walk(self, lba, size, path):
        last = None
        for name, ext, length, flags in self._records(lba, size):
            p = f"{path}/{name}"
            if flags & 2:
                self._walk(ext, length, p)
            elif last == p:  # files over 4 GB continue in further extents
                off, sz = self.files[p]
                self.files[p] = (off, sz + length)
            else:
                self.files[p] = (ext * SECTOR, length)
                last = p

    def find(self, suffix):
        """Full path of the file whose path ends with `suffix` (case-insensitive)."""
        s = suffix.lower().replace('\\', '/')
        hits = [p for p in self.files if p.lower().endswith(s)]
        if not hits:
            raise FileNotFoundError(suffix)
        return hits[0]

    def read(self, path, offset=0, size=None):
        off, sz = self.files[path]
        self.f.seek(off + offset)
        return self.f.read(sz - offset if size is None else size)

    def region(self, path):
        """(file object, absolute offset, size) -- for reading an archive in place."""
        off, sz = self.files[path]
        return self.f, off, sz


class EbArchive:
    def __init__(self, fileobj, base=0):
        self.f, self.base = fileobj, base
        h = self._at(0, 0x30)
        if h[:2] != b'EB' or struct.unpack_from('>H', h, 2)[0] != 3:
            raise ValueError("not an EB v3 archive")
        count = struct.unpack_from('>I', h, 4)[0]
        names_off, names_size = struct.unpack_from('>II', h, 12)
        fnl, dnl, ndirs = h[20], h[21], struct.unpack_from('>H', h, 22)[0]
        table = self._at(0x30, count * 16)
        names = self._at(names_off, names_size)
        d0 = (count * fnl + 15) // 16 * 16
        dirs = [names[d0 + i * dnl:d0 + (i + 1) * dnl].split(b'\0')[0].decode('latin1') for i in range(ndirs)]
        self.entries = {}  # 'db/nhlng-meta.xml' -> (offset, size, packed size)
        for i in range(count):
            rec = names[i * fnl:(i + 1) * fnl]
            off, packed, size, _hash = struct.unpack_from('>IIII', table, i * 16)
            folder = dirs[struct.unpack_from('>H', rec, 0)[0]]
            name = rec[2:].split(b'\0')[0].decode('latin1')
            self.entries[f"{folder}/{name}" if folder else name] = (off * 16, size, packed)

    @classmethod
    def open(cls, source, name):
        """`source` is a disc image path, an IsoImage, or a folder containing the .big files."""
        if isinstance(source, IsoImage) or (isinstance(source, str) and os.path.isfile(source)):
            iso = source if isinstance(source, IsoImage) else IsoImage(source)
            f, off, _ = iso.region(iso.find('/USRDIR/' + name))
            return cls(f, off)
        for root, _dirs, files in os.walk(source):
            for fn in files:
                if fn.lower() == name.lower():
                    return cls(open(os.path.join(root, fn), 'rb'))
        raise FileNotFoundError(name)

    def _at(self, off, n):
        self.f.seek(self.base + off)
        return self.f.read(n)

    def read(self, name):
        off, size, packed = self.entries[name]
        if packed:
            raise NotImplementedError(f"{name} is stored compressed")
        return self._at(off, size)
