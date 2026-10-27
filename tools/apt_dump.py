"""Print what an Apt UI movie of the game holds (the in-game overlays, the menus). Read only; nothing is written.

    python tools/apt_dump.py <file.big | unpacked movie> [--const <constant part>] [--disc <iso>] [--tree] [--frames]

<file.big> is a BIGF archive (art/menus.py `Bigf`): part '0' the movie, part '1' its constant file, and one part per
picture and per shape, named by its character's number + 1 (image 1 -> part '2', shape 2 -> part '3'). A picture part
is a RefPack'd DDS; a shape's part is its geometry. With --disc the file is read from the disc image instead
(fe/ion/game/overlays/<name> in cacheoverlay.big, else any EB archive entry ending in <name>). An unpacked movie
(RefPack'd or not) can be given alone; --const names its constant file, else the movie is found by its signature.

The PS3 movie, as far as this tool reads it (big-endian, "Apt Data:1:7:4"; the layout of OpenSAGE's Apt reader,
src/OpenSage.Game/Data/Apt, with 8 more bytes per character):

  character    u32 type, u32 0x09876543, u32 image (a shape: the image character it draws, else 0), u32 0, then:
    1 shape    bounds left, top, right, bottom (4 floats), u32 geometry (its own number)
    2 text     box (4 floats: left, top and, as OpenSAGE reads them, width, height), u32 font character,
               u32 alignment (0 left, 1 right, 2 centre), u32 colour 0xAARRGGBB, float height,
               u32 read only, u32 multiline, u32 word wrap, -> initial text, -> variable name
    3 font     -> name, u32 glyph count, -> glyphs
    4 button   (not read)
    5 sprite   frames (count, ->), u32 0
    7 image    u32 texture (its own number)
    9 movie    frames (count, ->), u32, characters (count, ->), u32 width, height, ms per frame,
               imports (count, -> 16-byte items: -> movie, -> name, character, 0), exports (count, ->)
  frame        u32 item count, -> item pointers; an item starts with u32 type:
    1 action (-> code)   2 frame label (-> name, flags, frame)   3 place object   4 remove object (depth)
    5 background colour   8 init action (sprite, -> code)
  place object (64 bytes) u32 flags (1 move, 2 character, 4 matrix, 8 colour, 16 ratio, 32 name, 64 clip depth,
               128 clip actions), depth, character, matrix a b c d, x, y, tint 0xAARRGGBB, add 0xAARRGGBB,
               ratio, -> name, clip depth (-1 none: a mask hides depths up to it), -> clip actions
  geometry     u32 size, u32 count, u32 0, offsets of the batches (from the part's start); a batch: u32 size,
               u32 count, u32 0, offsets of its entries (from the batch); an entry:
               u32 size, u32 kind (0 / 1 texture, 2 solid, 3 line), u32 0, float line width,
               u32 colour 0xAARRGGBB, u32 image character, 2 x u32 0, texture matrix a b c d tx ty
               (texture pixel = matrix x shape point + t), u32 triangles, u32 -> vertices (from the entry,
               16-byte aligned), then 3 vertices per triangle of 32 bytes (x, y, six floats 0)

A point of a shape lands on the screen at  parent matrix x (a b c d) x point + (x, y), down the --tree path.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from legacy_roster.art import refpack  # noqa: E402
from legacy_roster.art.menus import Bigf  # noqa: E402

SIGNATURE = 0x09876543
TYPES = {1: 'shape', 2: 'text', 3: 'font', 4: 'button', 5: 'sprite', 6: 'sound', 7: 'image', 8: 'morph',
         9: 'movie', 10: 'static text', 11: 'none', 12: 'video'}
KINDS = {0: 'texture', 1: 'texture/1', 2: 'solid', 3: 'line'}
ALIGN = {0: 'left', 1: 'right', 2: 'centre', 3: 'justify'}
MOVE, CHARACTER, MATRIX, COLOUR, RATIO, NAME, CLIP, ACTIONS = 1, 2, 4, 8, 16, 32, 64, 128


def unpack(data):
    return refpack.decompress(data) if data[:2] == refpack.MAGIC else bytes(data)


def colour(v):
    return f"#{v & 0xffffff:06x}/{v >> 24}"          # rgb hex / alpha 0-255


def num(f):
    return f"{f:.3f}".rstrip('0').rstrip('.') if abs(f - round(f)) > 1e-3 else str(int(round(f)))


class Place:
    """One place-object item."""

    def __init__(self, apt, at):
        u = apt.u32
        self.flags, self.depth, self.char = u(at + 4), u(at + 8), u(at + 12)
        self.matrix = struct.unpack_from('>6f', apt.data, at + 16)
        self.tint, self.add = u(at + 40), u(at + 44)
        self.name = apt.text(u(at + 52)) if self.flags & NAME else None
        self.clip = struct.unpack_from('>i', apt.data, at + 56)[0]

    def where(self):
        a, b, c, d, x, y = self.matrix
        out = f"at ({num(x)}, {num(y)})"
        if (round(a, 2), round(b, 2), round(c, 2), round(d, 2)) != (1, 0, 0, 1):
            out += f" m=({num(a)} {num(b)} {num(c)} {num(d)})"
        return out


class Apt:
    def __init__(self, movie, const=None, parts=None):
        self.data = unpack(movie)
        self.parts = parts or {}                    # {name: bytes} of the BIGF, unpacked on demand
        if const is not None:
            const = unpack(const)
            if not const.startswith(b'Apt constant file'):
                raise ValueError("not an Apt constant file")
            self.root = struct.unpack_from('>I', const, 0x14)[0]
        else:
            self.root = self._find_root()
        if self.u32(self.root) != 9 or self.u32(self.root + 4) != SIGNATURE:
            raise ValueError("no Apt movie character where the constant file says")
        count, table = self.u32(self.root + 0x1c), self.u32(self.root + 0x20)
        self.chars = [self.u32(table + 4 * i) for i in range(count)]

    def _find_root(self):
        sig = struct.pack('>II', 9, SIGNATURE)
        at = self.data.find(sig)
        while at >= 0 and at % 4:
            at = self.data.find(sig, at + 1)
        if at < 0:
            raise ValueError("no Apt movie character found (give --const)")
        return at

    def u32(self, at):
        return struct.unpack_from('>I', self.data, at)[0]

    def text(self, at):
        return self.data[at:self.data.index(b'\0', at)].decode('latin1') if at else None

    def kind(self, cid):
        at = self.chars[cid] if 0 <= cid < len(self.chars) else 0
        return self.u32(at) if at else None

    def frames(self, cid):
        at = self.chars[cid]
        count, table = self.u32(at + 0x10), self.u32(at + 0x14)
        for f in range(count):
            n, items = self.u32(table + 8 * f), self.u32(table + 8 * f + 4)
            yield f, [self.u32(items + 4 * k) for k in range(n)]

    def places(self, cid):
        """{(depth, character): (first frame, Place)} of every character placed in a sprite / the movie, and how
        many items only move or recolour what is there."""
        found, moves = {}, 0
        for f, items in self.frames(cid):
            for it in items:
                if self.u32(it) != 3:
                    continue
                p = Place(self, it)
                if p.flags & CHARACTER:
                    found.setdefault((p.depth, p.char), (f, p))
                else:
                    moves += 1
        return found, moves

    # ---- what a character is ----------------------------------------------------------------------------
    def picture(self, image):
        """'part N WxH' of an image character's DDS part."""
        dds = self.parts.get(str(image + 1))
        if dds is None:
            return f"part {image + 1} (none)"
        dds = unpack(dds)
        if dds[:4] != b'DDS ':
            return f"part {image + 1} (not a DDS)"
        h, w = struct.unpack_from('<II', dds, 12)
        return f"part {image + 1} {w}x{h}"

    def geometry(self, gid):
        """[(kind, colour, image, matrix, triangles, (left, top, right, bottom))] of a shape's geometry part."""
        g = self.parts.get(str(gid + 1))
        if g is None:
            return None
        g = unpack(g)
        u = lambda at: struct.unpack_from('>I', g, at)[0]          # noqa: E731
        out = []
        for i in range(u(4)):
            batch = u(12 + 4 * i)
            for j in range(u(batch + 4)):
                e = batch + u(batch + 12 + 4 * j)
                tris, verts = u(e + 0x38), e + u(e + 0x3c)
                n = tris * (2 if u(e + 4) == 3 else 3)
                pts = [struct.unpack_from('>2f', g, verts + 32 * k) for k in range(n)]
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                box = (min(xs), min(ys), max(xs), max(ys)) if pts else None
                out.append((u(e + 4), u(e + 0x10), u(e + 0x14), struct.unpack_from('>6f', g, e + 0x20), tris, box))
        return out

    def describe(self, cid):
        at = self.chars[cid] if 0 <= cid < len(self.chars) else 0
        if not at:
            return "(empty)"
        t, u = self.u32(at), self.u32
        name = TYPES.get(t, f"type {t}")
        if t == 1:
            box = struct.unpack_from('>4f', self.data, at + 0x10)
            out = f"shape {cid} box {num(box[0])},{num(box[1])}-{num(box[2])},{num(box[3])}"
            for kind, col, image, m, tris, gbox in self.geometry(u(at + 0x20)) or ():
                out += f" | {KINDS.get(kind, kind)} {colour(col)} {tris} tri"
                if kind in (0, 1):
                    out += f" image {image} ({self.picture(image)})"
                    if (round(m[0], 2), round(m[1], 2), round(m[2], 2), round(m[3], 2)) != (1, 0, 0, 1):
                        out += f" tex m=({num(m[0])} {num(m[1])} {num(m[2])} {num(m[3])})"
                    if abs(m[4]) > 0.01 or abs(m[5]) > 0.01:
                        out += f" tex t=({num(m[4])}, {num(m[5])})"
                if gbox:
                    out += f" [{num(gbox[0])},{num(gbox[1])}-{num(gbox[2])},{num(gbox[3])}]"
            return out
        if t == 2:
            box = struct.unpack_from('>4f', self.data, at + 0x10)
            font, align, col = u(at + 0x20), u(at + 0x24), u(at + 0x28)
            height = struct.unpack_from('>f', self.data, at + 0x2c)[0]
            flags = ''.join(c for c, v in zip('RMW', (u(at + 0x30), u(at + 0x34), u(at + 0x38))) if v)
            fname = self.text(u(self.chars[font] + 0x10)) if self.kind(font) == 3 else '?'
            return (f"text {cid} box {num(box[0])},{num(box[1])} {num(box[2])}x{num(box[3])} {colour(col)} "
                    f"{ALIGN.get(align, align)} font {font} '{fname}' {num(height)}px {flags or '-'} "
                    f"var={self.text(u(at + 0x40))!r} text={self.text(u(at + 0x3c))!r}")
        if t == 3:
            return f"font {cid} '{self.text(u(at + 0x10))}'"
        if t == 5:
            return f"sprite {cid} ({u(at + 0x10)} frames)"
        if t == 7:
            return f"image {cid} -> {self.picture(u(at + 0x10))}"
        if t == 9:
            return f"movie {cid} {u(at + 0x24)}x{u(at + 0x28)} ({u(at + 0x10)} frames)"
        return f"{name} {cid}"

    def imports(self):
        n, table = self.u32(self.root + 0x30), self.u32(self.root + 0x34)
        return [(self.text(self.u32(table + 16 * i)), self.text(self.u32(table + 16 * i + 4)),
                 self.u32(table + 16 * i + 8)) for i in range(n)]

    def exports(self):
        n, table = self.u32(self.root + 0x38), self.u32(self.root + 0x3c)
        return [(self.text(self.u32(table + 8 * i)), self.u32(table + 8 * i + 4)) for i in range(n)]


def print_tree(apt, cid, indent, path, origin, seen):
    found, moves = apt.places(cid)
    if moves and indent:
        print(f"{'  ' * indent}({moves} move / colour items)")
    for (depth, char), (frame, p) in sorted(found.items()):
        a, b, c, d, x, y = p.matrix
        oa, ob, oc, od, ox, oy = origin
        here = (oa * a + oc * b, ob * a + od * b, oa * c + oc * d, ob * c + od * d,
                oa * x + oc * y + ox, ob * x + od * y + oy)
        extra = f" frame {frame}" if frame else ''
        if p.clip >= 0:
            extra += f" MASK to depth {p.clip}"
        if p.flags & COLOUR and (p.tint != 0xffffffff or p.add):
            extra += f" tint {colour(p.tint)} add {colour(p.add)}"
        label = f" '{p.name}'" if p.name else ''
        print(f"{'  ' * indent}d{depth}{label} {p.where()} screen ({num(here[4])}, {num(here[5])}){extra}: "
              f"{apt.describe(char)}")
        if apt.kind(char) == 5 and char not in path:
            if char in seen:
                print(f"{'  ' * (indent + 1)}(sprite {char} as above)")
                continue
            seen.add(char)
            print_tree(apt, char, indent + 1, path | {char}, here, seen)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('file', help="a UI file (.big), an unpacked movie, or with --disc a file name on the disc")
    ap.add_argument('--const', help="the constant file of an unpacked movie")
    ap.add_argument('--disc', help="read <file> from this disc image (cacheoverlay.big first)")
    ap.add_argument('--tree', action='store_true', help="the display tree from the movie down (first placements)")
    ap.add_argument('--frames', action='store_true', help="every frame item of every sprite")
    args = ap.parse_args(argv)

    if args.disc:
        from legacy_roster.art.disc import EbArchive, IsoImage
        iso = IsoImage(args.disc)
        raw = None
        for arc_name in ['cacheoverlay.big'] + sorted({p.rsplit('/', 1)[1] for p in iso.files if p.endswith('.big')}):
            try:
                arc = EbArchive.open(iso, arc_name)
            except (FileNotFoundError, ValueError):
                continue
            hit = [n for n in arc.entries if n.lower().endswith('/' + args.file.lower())]
            if hit:
                raw = arc.read(hit[0])
                print(f"{arc_name}: {hit[0]}")
                break
        if raw is None:
            sys.exit(f"{args.file} is not on the disc")
    else:
        raw = open(args.file, 'rb').read()
    const = open(args.const, 'rb').read() if args.const else None
    parts = {}
    if raw[:4] == b'BIGF':
        big = Bigf(raw)
        parts = {n: raw[o:o + s] for n, o, s in big.parts}
        trailer = raw[big.end:]
        print(f"BIGF: {len(big.parts)} parts, {len(raw)} bytes, trailer {trailer.hex() or 'missing'}")
        movie, const = parts['0'], const or parts['1']
    else:
        movie = raw
    apt = Apt(movie, const, parts)
    root = apt.root
    print(f"movie at {root:#x} of {len(apt.data)} bytes: {apt.describe(0)}, {len(apt.chars)} characters, "
          f"{apt.u32(root + 0x2c)} ms per frame")
    for mname, name, char in apt.imports():
        print(f"import {char}: {name} from {mname}")
    for name, char in apt.exports():
        print(f"export {char}: {name}")

    print("\ncharacters:")
    for cid in range(1, len(apt.chars)):
        at = apt.chars[cid]
        extra = f"  (+8={apt.u32(at + 8)} +12={apt.u32(at + 12)})" if at and apt.u32(at + 12) else ''
        print(f"  {cid:4} @{at:#07x} {apt.describe(cid)}{extra}")

    if args.frames:
        for cid in range(len(apt.chars)):
            if apt.kind(cid) not in (5, 9):
                continue
            print(f"\n{apt.describe(cid)}:")
            for f, items in apt.frames(cid):
                for it in items:
                    t = apt.u32(it)
                    if t == 3:
                        p = Place(apt, it)
                        what = apt.describe(p.char).split(' |')[0] if p.flags & CHARACTER else 'move'
                        col = f" tint {colour(p.tint)} add {colour(p.add)}" if p.flags & COLOUR else ''
                        clip = f" mask to {p.clip}" if p.clip >= 0 else ''
                        name = f" '{p.name}'" if p.name else ''
                        print(f"  f{f} d{p.depth}{name} flags {p.flags:#x} {p.where()}{col}{clip}: {what}")
                    elif t == 2:
                        print(f"  f{f} label '{apt.text(apt.u32(it + 4))}'")
                    elif t == 4:
                        print(f"  f{f} remove d{apt.u32(it + 4)}")
                    elif t == 1:
                        print(f"  f{f} action @{apt.u32(it + 4):#x}")
                    elif t == 8:
                        print(f"  f{f} init action sprite {apt.u32(it + 4)} @{apt.u32(it + 8):#x}")
                    elif t == 5:
                        print(f"  f{f} background {colour(apt.u32(it + 4))}")

    if args.tree:
        print("\ntree (first placement of each character; screen = accumulated x, y):")
        print_tree(apt, 0, 1, {0}, (1, 0, 0, 1, 0, 0), set())
        if not apt.places(0)[0]:  # a library movie (line_change): its exported sprites
            for name, char in apt.exports():
                if apt.kind(char) == 5:
                    print(f"  export '{name}': {apt.describe(char)}")
                    print_tree(apt, char, 2, {0, char}, (1, 0, 0, 1, 0, 0), set())


if __name__ == '__main__':
    main()
