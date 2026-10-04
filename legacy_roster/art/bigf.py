"""The game's art files (portraits, logos): a small "BIGF" archive around an EA Apt UI movie.

    0x00 'BIGF'
    0x04 u32 little-endian: end of the last part
    0x08 u32 big-endian: number of parts
    0x0C u32 big-endian: size of the header and part table
    0x10 per part: u32 offset, u32 size (big-endian), NUL-terminated name
    then the parts, aligned, and a short trailer

The parts of an art file: '0' Apt data, a 288-byte Apt part, empty markers 'sg1' / 'sg2', the image
(RefPack-compressed DDS) and '1' the Apt constant file. Their names are the movie's own ids and
differ from file to file, so a new art file is always made from an existing one of the same kind
(a template from the player's own copy of the game) with only the image swapped.
"""
import struct

from . import refpack


class ArtFile:
    def __init__(self, data):
        if data[:4] != b'BIGF':
            raise ValueError("not a BIGF art file")
        self.raw = bytes(data)
        count, self.header_size = struct.unpack_from('>II', data, 8)
        self.parts = []                     # [(name, offset, size)]
        pos = 16
        for _ in range(count):
            off, size = struct.unpack_from('>II', data, pos)
            end = data.index(b'\0', pos + 8)
            self.parts.append((data[pos + 8:end].decode('latin1'), off, size))
            pos = end + 1
        self.end = struct.unpack_from('<I', data, 4)[0]

    def part(self, name):
        return next(self.raw[o:o + s] for n, o, s in self.parts if n == name)

    @property
    def image_part(self):
        """The name of the part holding the image: the RefPack stream that unpacks to a DDS (the Apt
        data part may be RefPack-compressed too)."""
        if not hasattr(self, '_image'):
            self._image = None
            for n, o, s in self.parts:
                if s and self.raw[o:o + 2] == refpack.MAGIC:
                    data = refpack.decompress(self.raw[o:o + s])
                    if data[:4] == b'DDS ':
                        self._image = (n, data)
                        break
            if self._image is None:
                raise ValueError("no image in this art file")
        return self._image[0]

    def image(self):
        """The image as a DDS file (bytes)."""
        self.image_part
        return self._image[1]

    def with_image(self, dds):
        """A copy of this art file with another DDS image of the same kind. Every part before the
        image keeps its place; the ones after move by however much the image grew or shrank,
        keeping their alignment."""
        name = self.image_part
        packed = refpack.compress(dds)
        _, img_off, img_size = next(p for p in self.parts if p[0] == name)
        shift = _align(img_off + len(packed), 64) - _align(img_off + img_size, 64)
        out = bytearray(self.raw[:img_off])
        table = []
        for n, o, s in self.parts:
            if n == name:
                table.append((n, o, len(packed)))
            elif o > img_off or (o == img_off and s == 0 and n != name and self._after_image(n)):
                table.append((n, o + shift, s))
            else:
                table.append((n, o, s))
        out += packed
        tail = [(n, o, s) for n, o, s in table if o >= img_off + len(packed) and n != name]
        for n, o, s in sorted(tail, key=lambda t: t[1]):
            out += b'\0' * (o - len(out))
            old = next(p for p in self.parts if p[0] == n)
            out += self.raw[old[1]:old[1] + old[2]]
        end = max(o + s for _n, o, s in table)
        trailer = self.raw[self.end:]
        out += b'\0' * (end - len(out)) + trailer
        struct.pack_into('<I', out, 4, end)
        pos = 16
        for n, o, s in table:
            struct.pack_into('>II', out, pos, o, s)
            pos += 8 + len(n) + 1
        return bytes(out)

    def _after_image(self, name):
        """For an empty part that shares the image's offset: does it come after the image in the table?"""
        names = [n for n, _o, _s in self.parts]
        return names.index(name) > names.index(self.image_part)


def _align(n, a):
    return (n + a - 1) // a * a
