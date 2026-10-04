"""Minimal text extraction for IIHF roster PDFs (stats.iihf.com/hydra/...).

The PDFs draw text with embedded TrueType subset fonts (Identity-H, no ToUnicode), so glyph
ids are mapped back to characters through each embedded font's own 'cmap' table.
rows(path) -> list of text rows, each a list of (x, text) cells sorted left to right.
"""
import base64
import re
import struct
import zlib


def _objects(pdf):
    return {int(m.group(1)): m.group(2) for m in re.finditer(rb'(\d+) 0 obj(.*?)endobj', pdf, re.S)}


def _stream(obj):
    m = re.search(rb'stream\r?\n(.*?)\r?\nendstream', obj, re.S)
    data = m.group(1)
    head = obj[:m.start()]
    if b'ASCII85Decode' in head:
        data = data.strip()
        data = base64.a85decode(data[:-2] if data.endswith(b'~>') else data, adobe=False)
    if b'FlateDecode' in head:
        data = zlib.decompress(data)
    return data


def _ref(obj, key):
    m = re.search(rb'/' + key + rb'\s*\[?\s*(\d+) 0 R', obj)
    return int(m.group(1)) if m else None


def _tables(ttf):
    num = struct.unpack_from('>H', ttf, 4)[0]
    return {ttf[12 + i * 16:16 + i * 16]: struct.unpack_from('>II', ttf, 20 + i * 16) for i in range(num)}


def _glyphs(ttf):
    t = _tables(ttf)
    long_loca = struct.unpack_from('>h', ttf, t[b'head'][0] + 50)[0]
    ng = struct.unpack_from('>H', ttf, t[b'maxp'][0] + 4)[0]
    lo, go = t[b'loca'][0], t[b'glyf'][0]
    locs = [struct.unpack_from('>I', ttf, lo + 4 * i)[0] if long_loca else struct.unpack_from('>H', ttf, lo + 2 * i)[0] * 2
            for i in range(ng + 1)]
    return [ttf[go + locs[i]:go + locs[i + 1]] for i in range(ng)]


_REF = {}


def _by_outline(subset_ttf, bold):
    """Subset fonts without a cmap: match each glyph's outline bytes against Windows' Arial."""
    key = 'bd' if bold else ''
    if key not in _REF:
        ref = open(f"C:/Windows/Fonts/arial{key}.ttf", 'rb').read()
        rg = _glyphs(ref)
        _REF[key] = {}
        for g, ch in _ttf_glyph_to_char(ref).items():
            if g < len(rg) and rg[g] and rg[g] not in _REF[key]:
                _REF[key][rg[g]] = ch
    return {i: _REF[key][g] for i, g in enumerate(_glyphs(subset_ttf)) if g in _REF[key]}


def _ttf_glyph_to_char(ttf):
    tables = _tables(ttf)
    off, _ = tables[b'cmap']
    n = struct.unpack_from('>H', ttf, off + 2)[0]
    rev = {}
    for i in range(n):
        plat, enc, sub = struct.unpack_from('>HHI', ttf, off + 4 + i * 8)
        so = off + sub
        if struct.unpack_from('>H', ttf, so)[0] != 4:
            continue
        segx2 = struct.unpack_from('>H', ttf, so + 6)[0]
        seg = segx2 // 2
        ends = struct.unpack_from(f'>{seg}H', ttf, so + 14)
        starts = struct.unpack_from(f'>{seg}H', ttf, so + 16 + segx2)
        deltas = struct.unpack_from(f'>{seg}h', ttf, so + 16 + 2 * segx2)
        ro_pos = so + 16 + 3 * segx2
        ranges = struct.unpack_from(f'>{seg}H', ttf, ro_pos)
        for k in range(seg):
            for c in range(starts[k], ends[k] + 1):
                if c == 0xFFFF:
                    continue
                if ranges[k] == 0:
                    g = (c + deltas[k]) & 0xFFFF
                else:
                    gp = ro_pos + 2 * k + ranges[k] + 2 * (c - starts[k])
                    g = struct.unpack_from('>H', ttf, gp)[0]
                    g = (g + deltas[k]) & 0xFFFF if g else 0
                if g and g not in rev:
                    rev[g] = chr(c)
    return rev


def rows(path):
    pdf = open(path, 'rb').read()
    objs = _objects(pdf)
    fonts = {}
    for num, obj in objs.items():
        for name, ref in re.findall(rb'/(F\d+)\s+(\d+) 0 R', obj):
            fobj = objs.get(int(ref), b'')
            if b'/Type0' in fobj:
                desc = objs[_ref(fobj, b'DescendantFonts')]
                fd = objs[_ref(desc, b'FontDescriptor')]
                ttf = _stream(objs[_ref(fd, b'FontFile2')])
                cmap = _ttf_glyph_to_char(ttf) if b'cmap' in _tables(ttf) else _by_outline(ttf, b'Bold' in fd)
                fonts[name.decode()] = ('cid', cmap)
            elif b'/Type /Font' in fobj:
                fonts[name.decode()] = ('simple', None)
    cells = []
    for num, obj in objs.items():
        if b'/Contents' not in obj:
            continue
        content = _stream(objs[_ref(obj, b'Contents')]).decode('latin1')
        font, x, y = None, 0.0, 0.0
        for tok in re.finditer(r'/(F\d+) [\d.]+ Tf|1 0 0 1 ([\d.\-]+) ([\d.\-]+) Tm|\[(.*?)\] TJ|\((.*?)\) Tj', content, re.S):
            if tok.group(1):
                font = fonts.get(tok.group(1), ('simple', None))
            elif tok.group(2):
                x, y = float(tok.group(2)), float(tok.group(3))
            else:
                parts = []
                if tok.group(4) is not None:
                    for h, n in re.findall(r'<([0-9a-fA-F]+)>|(-?[\d.]+)', tok.group(4)):
                        if h:
                            if font and font[0] == 'cid':
                                parts.append(''.join(font[1].get(int(h[i:i + 4], 16), '?') for i in range(0, len(h), 4)))
                            else:
                                parts.append(bytes.fromhex(h).decode('cp1252'))
                        elif n and float(n) < -200:
                            parts.append(' ')
                else:
                    parts.append(tok.group(5))
                cells.append((round(-y, 1), x, ''.join(parts)))
    out, row, cur = [], [], None
    for y, x, t in sorted(cells):
        if cur is not None and abs(y - cur) > 2:
            out.append(sorted(row))
            row = []
        cur = y
        row.append((x, t))
    if row:
        out.append(sorted(row))
    return out


if __name__ == '__main__':
    import sys
    for r in rows(sys.argv[1]):
        print(' | '.join(t for _, t in r))
