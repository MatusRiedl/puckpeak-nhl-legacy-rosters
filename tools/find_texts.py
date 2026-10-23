"""Find where a text the game shows comes from (maintainer tool; nothing is written anywhere).

    python tools/find_texts.py "<phrase>" ["<phrase>" ...] [--disc <iso | game folder>] [--game-dir <dir | file>]
                               [--loc-only] [--lang eng_us] [--deep] [--max 20]

Searches, without case:
  * the game's text files (fe/loc/nhl_<language>.db in cacheboot.big, and loose copies under a --game-dir): every key
    and text, printed as key, bytes, text (art/loc.py reads them);
  * every entry of every EB archive on the disc (*.big under USRDIR) as UTF-8, UTF-16LE and UTF-16BE, also inside the
    small BIGF archives (UI movies, art files: RefPack parts are unpacked, images skipped), Flash / GFx movies
    (CWS / CFX: zlib after 8 bytes) and chunkzip files; 3D textures (.rpsgl) only with --deep;
  * every file under each --game-dir (RPCS3's dev_hdd0/game/<TITLEID>, a savedata folder, a decrypted EBOOT.ELF) the
    same way, and lists files whose names hold tuner, news, motd, ticker or dynamic.

A phrase can also be a key name (TXT_OFFLINE_DYNAMIC_MSG_BODY_0): a UI movie or the program that names the key shows
where the text is used. --disc defaults to LEGACY_ROSTER_DISC. Standard library and the repo's art readers only.
"""
import argparse
import io
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from legacy_roster.art import refpack, rpsgl  # noqa: E402
from legacy_roster.art.disc import EbArchive, IsoImage  # noqa: E402
from legacy_roster.art.loc import LANGUAGES, LocFile  # noqa: E402

NAME_WORDS = ('tuner', 'news', 'motd', 'ticker', 'dynamic')
LOOSE_LIMIT = 256 << 20          # loose files larger than this are not read whole (speech, firmware)
SKIP_FILES = ('pbp_eng_samples.sbs', 'ps3updat.pup')
ENCODINGS = ('utf-8', 'utf-16-le', 'utf-16-be')


class Finder:
    def __init__(self, phrases, langs=None, deep=False, most=20):
        self.phrases = [p for p in phrases if p]
        self.langs = langs
        self.deep = deep
        self.most = most
        self.hits = 0
        # per encoding the lower-case pattern bytes; ASCII case is folded on the data with bytes.lower()
        self.patterns = [(p, enc, p.lower().encode(enc)) for p in self.phrases for enc in ENCODINGS]

    def say(self, *parts):
        self.hits += 1
        print(*parts, flush=True)

    # --- text files ----------------------------------------------------------------------------------
    def loc(self, data, label):
        try:
            loc = LocFile(data)
        except Exception:                       # not a text database: search it as bytes
            return False
        folded = [p.casefold() for p in self.phrases]
        for e in sorted(loc.entries, key=lambda e: e[1].upper()):
            key, text = e[1], e[2]
            if any(p in key.casefold() or p in text.casefold() for p in folded):
                one_line = text.replace('\r', ' ').replace('\n', ' / ')
                self.say(f"{label}  key {key}  ({len(text.encode('utf-8'))} bytes)  {one_line}")
        return True

    def wanted_lang(self, name):
        if not self.langs:
            return True
        return any(f"nhl_{lang}" in name.lower() for lang in self.langs)

    # --- bytes and containers ---------------------------------------------------------------------------
    def scan(self, data, label, name=''):
        """Search `data` (an entry or a file) and whatever it unpacks to."""
        low = name.lower()
        if data[:2] == b'DB' and ('/loc/' in low.replace('\\', '/') or os.path.basename(low).startswith('nhl_')):
            if not self.wanted_lang(low):
                return
            if self.loc(data, label):
                return
        if data[:4] == b'BIGF':
            if self.bigf(data, label):
                return
        if data[:2] == b'EB' and len(data) > 0x30 and struct.unpack_from('>H', data, 2)[0] == 3:
            try:
                arc = EbArchive(io.BytesIO(data))
            except Exception:
                arc = None
            if arc is not None:
                self.archive(arc, label)
                return
        if data[:3] in (b'CWS', b'CFX'):
            try:
                self.raw(zlib.decompress(data[8:]), label + ' (zlib)')
                return
            except zlib.error:
                pass
        if data[:8] == b'chunkzip':
            if low.endswith('.rpsgl') and not self.deep:
                return
            try:
                inner = rpsgl.unpack(data)
            except Exception:
                inner = None
            if inner is not None:
                self.scan(inner, label + ' (chunkzip)')
                return
        if data[:2] == refpack.MAGIC:
            sub = self.unrefpack(data)
            if sub is not None:
                self.scan(sub, label + ' (refpack)')
                return
        self.raw(data, label)

    def raw(self, data, label):
        low = bytes(data).lower()
        for phrase, enc, pat in self.patterns:
            pos, n = low.find(pat), 0
            while pos >= 0 and n < self.most:
                self.say(f"{label}  @0x{pos:x} {enc}  {context(data, pos, len(pat), enc)}")
                n += 1
                pos = low.find(pat, pos + 1)

    def unrefpack(self, data):
        """A RefPack stream unpacked, or None for an image (DDS) or a stream that is no RefPack after all."""
        try:
            if peek_refpack(data, 4) == b'DDS ':
                return None
            return refpack.decompress(data)
        except Exception:
            return None

    def bigf(self, data, label):
        """The parts of a small BIGF archive (UI movie, art file), each searched on its own."""
        try:
            count = struct.unpack_from('>I', data, 8)[0]
            pos, parts = 16, []
            for _ in range(count):
                off, size = struct.unpack_from('>II', data, pos)
                end = data.index(b'\0', pos + 8)
                parts.append((data[pos + 8:end].decode('latin1'), off, size))
                pos = end + 1
        except Exception:
            return False
        for part, off, size in parts:
            blob = data[off:off + size]
            if not blob:
                continue
            self.scan(blob, f"{label}!{part}", part)
        return True

    def archive(self, arc, label):
        for name in sorted(arc.entries):
            off, size, packed = arc.entries[name]
            if packed:                       # the disc's few packed entries are animations (.cba)
                continue
            if name.lower().endswith('.rpsgl') and not self.deep:
                continue
            self.scan(arc.read(name), f"{label}:{name}", name)


def peek_refpack(data, n):
    """The first `n` bytes a RefPack stream unpacks to (to skip images without unpacking them)."""
    out, pos = bytearray(), 5
    while len(out) < n:
        b0 = data[pos]
        if b0 < 0x80:
            lit, length, back, step = b0 & 3, ((b0 & 0x1C) >> 2) + 3, ((b0 & 0x60) << 3) + data[pos + 1] + 1, 2
        elif b0 < 0xC0:
            b1, b2 = data[pos + 1], data[pos + 2]
            lit, length, back, step = (b1 >> 6) & 3, (b0 & 0x3F) + 4, ((b1 & 0x3F) << 8) + b2 + 1, 3
        elif b0 < 0xE0:
            b1, b2, b3 = data[pos + 1], data[pos + 2], data[pos + 3]
            lit, length, back, step = b0 & 3, ((b0 & 0x0C) << 6) + b3 + 5, ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1, 4
        elif b0 < 0xFC:
            k = ((b0 & 0x1F) + 1) << 2
            out += data[pos + 1:pos + 1 + k]
            pos += 1 + k
            continue
        else:
            out += data[pos + 1:pos + 1 + (b0 & 3)]
            break
        pos += step
        out += data[pos:pos + lit]
        pos += lit
        start = len(out) - back
        for k in range(length):
            out.append(out[start + k])
    return bytes(out[:n])


def context(data, pos, size, enc, before=60, after=160):
    """The text around a hit, on one line."""
    unit = 1 if enc == 'utf-8' else 2
    a = max(0, pos - before * unit)
    a -= (pos - a) % unit
    chunk = bytes(data[a:pos + size + after * unit])
    text = chunk.decode(enc, 'replace')
    return ''.join(c if c.isprintable() else '.' for c in text)


def disc_archives(source):
    """(label, EbArchive) for every EB archive under USRDIR of a disc image or game folder, and loose small files."""
    if os.path.isfile(source):
        iso = IsoImage(source)
        for path in sorted(iso.files):
            if '/USRDIR/' not in path or os.path.basename(path).lower() in SKIP_FILES:
                continue
            f, off, size = iso.region(path)
            try:
                yield path, EbArchive(f, off), None
            except ValueError:
                if size <= LOOSE_LIMIT:
                    yield path, None, iso.read(path)
        return
    for root, _dirs, files in os.walk(source):
        for fn in sorted(files):
            path = os.path.join(root, fn)
            if fn.lower() in SKIP_FILES:
                continue
            try:
                yield path, EbArchive(open(path, 'rb')), None
            except (ValueError, struct.error):
                if os.path.getsize(path) <= LOOSE_LIMIT:
                    with open(path, 'rb') as f:
                        yield path, None, f.read()


def scan_dir(finder, top):
    """Every file under `top` (or `top` itself), and the names worth a look."""
    paths = [top] if os.path.isfile(top) else [os.path.join(r, f) for r, _d, fs in os.walk(top) for f in fs]
    for path in sorted(paths):
        name = os.path.basename(path)
        if any(w in name.lower() for w in NAME_WORDS):
            print(f"NAME  {path}  ({os.path.getsize(path)} bytes)", flush=True)
        if name.lower() in SKIP_FILES or os.path.getsize(path) > LOOSE_LIMIT:
            continue
        try:
            with open(path, 'rb') as f:
                head = f.read(4)
        except OSError as exc:
            print(f"SKIP  {path}: {exc}")
            continue
        if head[:2] == b'EB':
            try:
                finder.archive(EbArchive(open(path, 'rb')), path)
                continue
            except (ValueError, struct.error):
                pass
        with open(path, 'rb') as f:
            finder.scan(f.read(), path, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Find a text of the game on the disc and in RPCS3's game folders.")
    ap.add_argument('phrases', nargs='+', help="words to look for (any case); a key name works too")
    ap.add_argument('--disc', default=os.environ.get('LEGACY_ROSTER_DISC'), help="the game's disc image or folder")
    ap.add_argument('--game-dir', action='append', default=[],
                    help="a folder or file to search too (dev_hdd0/game/<TITLEID>, savedata, EBOOT.ELF); repeatable")
    ap.add_argument('--loc-only', action='store_true', help="only the text files")
    ap.add_argument('--lang', action='append', help=f"only these languages ({', '.join(LANGUAGES)}); repeatable")
    ap.add_argument('--deep', action='store_true', help="also unpack 3D textures (.rpsgl)")
    ap.add_argument('--max', type=int, default=20, help="hits per phrase per file (default 20)")
    args = ap.parse_args(argv)
    finder = Finder(args.phrases, args.lang, args.deep, args.max)
    if args.disc:
        for label, arc, loose in disc_archives(args.disc):
            if arc is None:
                if not args.loc_only:
                    finder.scan(loose, label, label)
                continue
            if args.loc_only:
                for name in sorted(n for n in arc.entries if '/loc/' in n and n.endswith('.db')):
                    if finder.wanted_lang(name):
                        finder.loc(arc.read(name), f"{label}:{name}")
                continue
            finder.archive(arc, label)
    elif not args.game_dir:
        ap.error("give --disc (or set LEGACY_ROSTER_DISC) or --game-dir")
    for top in args.game_dir:
        if args.loc_only:
            for root, _d, files in os.walk(top):
                for fn in sorted(files):
                    if fn.lower().startswith('nhl_') and fn.lower().endswith('.db') and finder.wanted_lang(fn):
                        with open(os.path.join(root, fn), 'rb') as f:
                            finder.loc(f.read(), os.path.join(root, fn))
            continue
        scan_dir(finder, top)
    print(f"{finder.hits} hit(s)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
