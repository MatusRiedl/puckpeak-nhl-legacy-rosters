"""The game's text file (fe/loc/nhl_<language>.db): read it, change texts, write it back.

Team names in the menus come from here, not from the roster (FORMAT.md section 7): for a team
whose art code (`ttOk.artabbr`) is CHOM the game asks for NHLTeamName_CHOM, NHLCityName_CHOM,
TXT_NICKNAME_CHOM, TXT_NICKNAME_ALT_CHOM and X_XLA_TEAM_CHOM; a custom team's name is the text
whose key is its `shortname` (LAS_VEGAS -> "Las Vegas"; the update writes such keys in the game's
own style, layout.city_key). A corrected copy goes into the game's
folder on RPCS3's hard disk, where the game reads it before the disc's (install.py).

The file is an EA "DB" with one table, LanguageStrings: per text a 32-bit key hash (CRC-32 of the
upper-case key, initial value 0xFFFFFFFF, no final inversion; records sorted by it) and two
Huffman-compressed strings, the key and the text, stored after the records. The game keeps its
keys in their own case (NHLTeamName_CHOM, ChangeDay); an added key is stored exactly as asked
for. In the game (owner, 2026-10-04) texts changed under the game's own keys showed, while texts
added under "2026 PROSPECTS 2" for a custom team whose shortname was "2026 Prospects 2" did not;
custom teams now use keys in the game's style (COACHELLA_VALLEY), which read the same in any case.
About 11,700 of the game's own records carry a hash that is not that of their key under any rule
tried (they are found by hash only, from the game's code); they are kept as they are.

    tail    the Huffman tree: node n is the 2-byte entries 2n and 2n+1 (0 / 1 bit), an entry
            (k, 0) leads to node k, (0, c) is the byte c; node 0 is the root
            then each string at its record's offset: its length in bytes (1 byte for the key,
            2 for the text, big-endian), then the bits, most significant first, in bits // 8 + 1
            bytes (a string whose bits fill whole bytes gets one more, zero, byte)
            (offset 0xFFFFFFFF: no string)
            then zeros to a multiple of 8, then the CRC-32/MPEG-2 of the table from 0x28 on
    header  +0x10: where the strings end
"""
import heapq
import struct
import zlib

from ..tdb import crc32_mpeg2

NO_STRING = 0xFFFFFFFF
TEAM_KEYS = {'full': 'NHLTeamName_{}', 'city': 'NHLCityName_{}', 'nick': 'TXT_NICKNAME_{}',
             'nick_alt': 'TXT_NICKNAME_ALT_{}', 'abbr': 'X_XLA_TEAM_{}'}


# which texts apply_names writes; a change rewrites every installed text file once. '#2': the lines
# of the team screens (TEAMLINE1/2, NICKLINE2, Abbr3, the NHL slots' numbered texts), 0.8.1
NAMES_VERSION = '#2'
LANGUAGES = ('eng_us', 'fre_fr', 'ger_de', 'swe_se', 'fin_fi', 'cze_cz', 'rus_ru')


def key_hash(key):
    return zlib.crc32(key.upper().encode('utf-8'), 0xFFFFFFFF) ^ 0xFFFFFFFF


def select_lines(full, city, nick, mark=''):
    """The two lines the team screens show for a team, in the game's own way: a city first and then
    the nickname ('Tampa Bay' / 'Lightning®'), a nickname first and then the city for a name that
    ends in its city ('Piráti' / 'Chomutov'), the whole name on the big line when it has no city
    ('' / 'MODO Hockey')."""
    full, city, nick = (full or '').strip(), (city or '').strip(), (nick or '').strip()
    if city and full.lower().startswith(city.lower() + ' '):
        rest = full[len(city):].strip()
        if len(rest) >= 3:                      # not "Timrå" + "IK"
            return city, rest + mark
    if city and full.lower().endswith(' ' + city.lower()):
        rest = full[:-len(city)].strip()
        if len(rest) >= 3:
            return rest, city
    return '', full + mark


def apply_names(loc, names):
    """Put the roster's team names into a text file (`names` from portraits.names()). A club whose
    name the game already has is left as it is. Returns how many texts changed."""
    changed = 0
    plain = lambda s: (s or '').replace('®', '').replace('™', '').strip().lower()
    marked = names.get('marked', ())
    for art, full, city, nick, abbr in names.get('teams', []):
        if not art or not full:
            continue
        if art in names.get('force', ()) or plain(loc.get(TEAM_KEYS['full'].format(art))) != plain(full):
            loc.set_team(art, full=full, city=city or full, nick=nick, abbr=abbr)
            line1, line2 = select_lines(full, city, nick, '®' if art in marked else '')
            loc.set_select_lines(art, line1, line2, abbr=abbr)
            changed += 1
    for slot, (full, city, nick, abbr) in sorted((int(s), v) for s, v in names.get('numbered', {}).items()):
        # the NHL slots the community gave to newer teams also have texts under their number
        line1, line2 = select_lines(full, city, nick, '®')
        loc.set_existing(f"NHLTeamName_{slot}", full)
        loc.set_select_lines(slot, line1, line2, abbr=abbr, city=city)
        changed += 1
    for key, text in sorted(names.get('cities', {}).items()):
        if loc.get(key) is None:
            loc.set(key, text)
            changed += 1
    return changed


class LocFile:
    def __init__(self, data):
        self.raw = bytes(data)
        d = self.raw
        if d[:2] != b'DB' or struct.unpack_from('>I', d, 0x10)[0] != 1:
            raise ValueError("not a text database of the game")
        self.db_header = bytearray(d[:0x18])
        self.index = bytes(d[0x18:0x20])
        dbsize = struct.unpack_from('>I', d, 8)[0]
        t = d[0x20:dbsize]
        self.header = bytearray(t[:0x28])
        nf = t[0x1C]
        self.field_defs = bytes(t[0x28:0x28 + nf * 16])
        self.rec_len, n = struct.unpack_from('>I', t, 8)[0], struct.unpack_from('>H', t, 0x16)[0]
        r0 = 0x28 + nf * 16
        records = t[r0:r0 + n * self.rec_len]
        tail = t[r0 + n * self.rec_len:]
        self.tree = self._tree_bytes(tail)
        self.entries = []        # [hash, key, text, key_absent, text_absent]
        for i in range(n):
            a, b, h = struct.unpack_from('>III', records, i * self.rec_len)
            self.entries.append([h, self._read(tail, a, 1), self._read(tail, b, 2), a == NO_STRING, b == NO_STRING])
        self.by_hash = {e[0]: e for e in self.entries}
        self._by_key = None

    @classmethod
    def blank(cls, texts):
        """A text file of this layout holding `texts` {key: text} (for tests; the game's own files
        are always the starting point otherwise)."""
        self = cls.__new__(cls)
        # 'DB', version, size (+8), one table (+0x10), header CRC (+0x14)
        self.db_header = bytearray(b'DB\x00\x08\x01\x00\x00\x00' + bytes(8) + struct.pack('>I', 1) + bytes(4))
        self.index = b'GJCv' + bytes(4)
        self.header = bytearray(struct.pack('>10I', 0, 0x42, 16, 0x7f, 0, 0, 0xffff, 0x3000000, 0, 0))
        self.header[0x1C] = 3
        self.field_defs = (struct.pack('>II4sI', 13, 0, b'VhAs', 800) + struct.pack('>II4sI', 14, 32, b'bYbZ', 32000)
                           + struct.pack('>II4sI', 3, 64, b'jKhj', 32))
        self.rec_len = 16
        self.entries = [[key_hash(k), k, v, False, False] for k, v in texts.items()]
        self.by_hash = {e[0]: e for e in self.entries}
        self._by_key = None
        self.tree = self._new_tree()
        return self

    # --- reading -------------------------------------------------------------------------------------
    @staticmethod
    def _tree_bytes(tail):
        """The tree: the entries reachable from node 0 decide how long it is."""
        seen, todo, top = set(), [0], 0
        while todo:
            n = todo.pop()
            if n in seen:
                continue
            seen.add(n)
            top = max(top, n)
            for k in (0, 1):
                e = tail[4 * n + 2 * k:4 * n + 2 * k + 2]
                if e[0]:
                    todo.append(e[0])
        return bytes(tail[:4 * (top + 1)])

    def _read(self, tail, off, width):
        if off == NO_STRING:
            return ''
        n = int.from_bytes(tail[off:off + width], 'big')
        out, bit, node, tree = bytearray(), (off + width) * 8, 0, self.tree
        while len(out) < n:
            b = (tail[bit >> 3] >> (7 - (bit & 7))) & 1
            bit += 1
            e0, e1 = tree[4 * node + 2 * b], tree[4 * node + 2 * b + 1]
            if e0 == 0:
                out.append(e1)
                node = 0
            else:
                node = e0
        return out.decode('utf-8', 'replace')

    def get(self, key):
        e = self.by_hash.get(key_hash(key))
        return e[2] if e else None

    # --- changing ---------------------------------------------------------------------------------------
    def set(self, key, text):
        """Change a text, or add it when the game has no text under that key. An added key is
        stored exactly as given: the game looks it up in that case (see the module notes)."""
        h = key_hash(key)
        e = self.by_hash.get(h)
        if e is None:
            e = [h, key, text, False, False]
            self.entries.append(e)
            self.by_hash[h] = e
            if self._by_key is not None:
                self._by_key[key.upper()] = e
        else:
            e[2], e[4] = text, False

    def set_team(self, art, full=None, city=None, nick=None, abbr=None):
        for part, value in (('full', full), ('city', city), ('nick', nick), ('nick_alt', nick), ('abbr', abbr)):
            if value:
                self.set(TEAM_KEYS[part].format(art), value)

    def set_existing(self, key, text):
        """Change the text under a key the game has, found by the key as stored (not by hash: the
        Select Teams lines have hashes that are not the CRC of their key, so `set` would add a text
        the game never asks for). Does nothing, and says False, when the game has no such key."""
        if self._by_key is None:
            self._by_key = {e[1].upper(): e for e in self.entries if not e[3]}
        e = self._by_key.get(key.upper())
        if e is None:
            return False
        e[2], e[4] = text, False
        return True

    def set_select_lines(self, key_tail, line1, line2, abbr=None, city=None):
        """The texts the team screens (Play Now "Select Teams", Season) read: TEAMLINE1/2 are the small
        line above and the big line of a team's name, NICKLINE2 the big line again, Abbr3 the short
        code, CITYLINE1 and NHLCityName a city, under `key_tail` (a team's art code, or an NHL slot number)."""
        for key, text in ((f"TEAMLINE1_{key_tail}", line1), (f"TEAMLINE2_{key_tail}", line2),
                          (f"NICKLINE2_{key_tail}", line2), (f"NHLTeamName_Abbr3_{key_tail}", abbr),
                          (f"CITYLINE1_{key_tail}", city), (f"NHLCityName_{key_tail}", city)):
            if text is not None:
                self.set_existing(key, text)

    # --- writing -------------------------------------------------------------------------------------------
    def _codes(self, tree):
        codes, todo = {}, [(0, '')]
        while todo:
            node, prefix = todo.pop()
            for k in (0, 1):
                e0, e1 = tree[4 * node + 2 * k], tree[4 * node + 2 * k + 1]
                if e0 == 0:
                    codes[e1] = prefix + str(k)
                else:
                    todo.append((e0, prefix + str(k)))
        return codes

    def _new_tree(self):
        """A Huffman tree for every byte the texts use, in the file's layout (needed only when a
        new text uses a byte the game's own tree lacks)."""
        freq = {}
        for e in self.entries:
            for s in (e[1], e[2]):
                for c in s.encode('utf-8'):
                    freq[c] = freq.get(c, 0) + 1
        heap = [(n, k, ('leaf', c)) for k, (c, n) in enumerate(sorted(freq.items()))]
        heapq.heapify(heap)
        k = len(heap)
        while len(heap) > 1:
            a, b = heapq.heappop(heap), heapq.heappop(heap)
            heapq.heappush(heap, (a[0] + b[0], k, ('node', a[2], b[2])))
            k += 1
        root = heap[0][2]
        order, queue = [], [root]                    # number the inner nodes breadth first
        while queue:
            n = queue.pop(0)
            order.append(n)
            queue += [c for c in n[1:] if c[0] == 'node']
        number = {id(n): i for i, n in enumerate(order)}
        if len(order) > 255:
            raise ValueError("too many different characters for the game's text file")
        out = bytearray()
        for n in order:
            for c in n[1:]:
                out += bytes((0, c[1])) if c[0] == 'leaf' else bytes((number[id(c)], 0))
        return bytes(out)

    def build(self):
        used = {c for e in self.entries for s in (e[1], e[2]) for c in s.encode('utf-8')}
        tree = self.tree
        codes = self._codes(tree)
        if not used <= set(codes):
            tree = self._new_tree()
            codes = self._codes(tree)
        data = bytearray(tree)
        records = bytearray()

        def put(text, width, absent):
            if absent and not text:
                return NO_STRING
            off = len(data)
            raw = text.encode('utf-8')
            bits = ''.join(codes[c] for c in raw)
            data.extend(len(raw).to_bytes(width, 'big'))
            bits += '0' * (8 - len(bits) % 8)       # the game always pads with 1-8 bits (bits // 8 + 1 bytes)
            data.extend(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
            return off
        for e in sorted(self.entries, key=lambda e: e[0]):
            a = put(e[1], 1, e[3])
            b = put(e[2], 2, e[4])
            rec = bytearray(self.rec_len)
            struct.pack_into('>III', rec, 0, a, b, e[0])
            records += rec
        end = len(data)
        data += bytes(-len(data) % 8)
        h = bytearray(self.header)
        n = len(self.entries)
        struct.pack_into('>HH', h, 0x14, n, n)
        struct.pack_into('>I', h, 0x10, end)
        struct.pack_into('>I', h, 0x24, crc32_mpeg2(h[4:0x24]))
        table = bytearray(h + self.field_defs + records + data)
        struct.pack_into('>I', table, 0, crc32_mpeg2(self.index))     # chain: the table index
        table += struct.pack('>I', crc32_mpeg2(table[0x28:]))
        dbh = bytearray(self.db_header)
        struct.pack_into('>I', dbh, 8, 0x20 + len(table))
        struct.pack_into('>I', dbh, 0x14, crc32_mpeg2(dbh[:0x14]))
        return bytes(dbh) + self.index + bytes(table)
