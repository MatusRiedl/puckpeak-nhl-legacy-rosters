"""Find every place the game patch names (gamepatch.port_addresses) in the program of update 1.01 and write
legacy_roster/patch101.py, the table gamepatch.at() reads.

    python tools/port_patch.py <EBOOT 1.00.ELF> <EBOOT 1.01.ELF> [--write]

Both ELFs are decrypted programs (RPCS3's Utilities > Decrypt PS3 Binaries; 1.01's EBOOT.BIN is in the update's
USRDIR). They stay on the PC that has the game and are never shipped. 1.01 is 1.00 with a few functions grown, so a place
is found by its neighbourhood:
  * code: the same words around it (branch displacements left out), unique near the place; else the same with the
    displacements of loads, stores and lis / addi left out too (data moved); else the most words alike in a wider window,
    when clearly best or as far moved as its neighbours;
  * data: the code that builds the address with lis + a load or addi, found in 1.01 and read back there; else the same
    words around it (words that look like addresses left out, if need be);
  * function descriptors (the login entry's data word): the descriptor of the moved function.
Each place must hold the same word as in 1.00 (a branch: displacement aside), and every word the 1.01 patch expects must
be in the 1.01 program. Exit code 1 when a place is not found or does not check out; nothing is written then.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from legacy_roster import gamepatch  # noqa: E402
from audit_patch import ppu_hash, segments  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'legacy_roster', 'patch101.py')
SPAN = 0x8000                       # 1.01 moved every place by 0 .. 0x2030 bytes
D_FORM = set(range(32, 56)) | {12, 13, 14, 58, 62}
DATA = set(gamepatch.DATA_WORDS) | set(gamepatch.CAVE_DATA)


class Program:
    def __init__(self, path):
        with open(path, 'rb') as f:
            self.data = f.read()
        self.segs = segments(self.data)
        self.hash = ppu_hash(self.data)
        entry, = struct.unpack_from('>Q', self.data, 0x18)
        self.toc = self.word(entry + 4)             # the entry's descriptor: function, TOC

    def word(self, addr):
        for vaddr, off, size in self.segs:
            if vaddr <= addr < vaddr + size:
                return struct.unpack_from('>I', self.data, off + addr - vaddr)[0]
        return None

    def lis_pairs(self):
        """{address of the second word: address built} of every lis rX followed within 4 words by a load, store or
        addi / addic on rX."""
        vaddr, off, size = self.segs[0]
        words = struct.unpack_from(f'>{size // 4}I', self.data, off)
        found = {}
        for i, hi in enumerate(words):
            if hi >> 26 != 15 or hi >> 16 & 31:
                continue
            reg = hi >> 21 & 31
            for j in range(i + 1, min(i + 5, len(words))):
                lo = words[j]
                if lo >> 26 in D_FORM and lo >> 16 & 31 == reg:
                    low = lo & 0xffff
                    found[vaddr + 4 * j] = ((hi & 0xffff) << 16) + (low - 0x10000 if low & 0x8000 else low) & 0xffffffff
                    break
        return found


def branch_mask(word):
    op = word >> 26
    if op == 18:
        return word & 0xfc000003
    if op == 16:
        return word & 0xffff0003
    return word


def loose_mask(word):
    return word & 0xffff0000 if word >> 26 in D_FORM | {15} else branch_mask(word)


def address_mask(word):
    return 0 if 0x10000 <= word < 0x2400000 else word


def window(prog, addr, k, mask):
    return [mask(prog.word(addr + 4 * j) or 0) for j in range(-k, k + 1)]


def search(old, new, addr, k, mask, span=SPAN):
    want = window(old, addr, k, mask)
    return [b for b in range(addr - span, addr + span, 4)
            if mask(new.word(b) or 0) == want[k] and window(new, b, k, mask) == want]


def score(old, new, a, b, k=24):
    x, y = window(old, a, k, loose_mask), window(new, b, k, loose_mask)
    return sum(p == q for p, q in zip(x, y)) / len(x)


class Porter:
    def __init__(self, old, new):
        self.old, self.new = old, new
        self.moves = {}                 # code places: (1.01 address or None, how); the found ones guide the rest
        self.refs = self.calls = None

    def callers(self, addr):
        """{1.01 address: how many} of the 1.00 function `addr` as the moved callers call it (bl)."""
        if self.calls is None:
            vaddr, off, size = self.old.segs[0]
            self.calls = {}
            for i, w in enumerate(struct.unpack_from(f'>{size // 4}I', self.old.data, off)):
                if w >> 26 == 18 and w & 3 == 1:
                    site = vaddr + 4 * i
                    disp = w & 0x3fffffc
                    self.calls.setdefault(site + (disp - 0x4000000 if disp & 0x2000000 else disp), []).append(site)
        votes = {}
        for site in self.calls.get(addr, [])[:40]:
            hits = search(self.old, self.new, site, 10, branch_mask)
            if len(hits) == 1 and self.new.word(hits[0]) >> 26 == 18:
                target = gamepatch._target(hits[0], self.new.word(hits[0]) & ~1)
                votes[target] = votes.get(target, 0) + 1
        return votes

    def code(self, addr):
        """(1.01 address or None, how) of the 1.00 code address `addr`."""
        if addr in self.moves:
            return self.moves[addr]
        self.moves[addr] = found = self._code(addr)
        return found

    def _code(self, addr):
        hits = search(self.old, self.new, addr, 10, branch_mask)
        if len(hits) == 1:
            return hits[0], 'same words'
        votes = self.callers(addr)
        if len(votes) == 1:
            (moved, n), = votes.items()
            return moved, f'where {n} moved caller(s) call it'
        if len(votes) > 1:
            return None, f"its callers call different places: {', '.join(hex(v) for v in votes)}"
        hits = search(self.old, self.new, addr, 12, loose_mask)
        if len(hits) == 1:
            return hits[0], 'same words, data moved'
        known = {a: m for a, (m, _) in self.moves.items() if m is not None}
        near = sorted(known, key=lambda x: abs(x - addr))[:6]
        hint = known[near[0]] - near[0] if near else 0
        deltas = {known[x] - x for x in near} | set(range(-0x1000, 0x3000, 4))
        best = sorted(((score(self.old, self.new, addr, addr + d), d == hint, d) for d in deltas), reverse=True)
        (s1, _, d1), (s2, _, _) = best[0], best[1]
        if s1 >= 0.9 and (s1 - s2 >= 0.1 or d1 == hint):
            return addr + d1, f'most alike ({s1:.2f}, next {s2:.2f}' + (', as far as its neighbour)' if s1 - s2 < 0.1 else ')')
        return None, f'not found (best {s1:.2f} at {d1:+#x}, next {s2:.2f})'

    def data(self, addr):
        """(1.01 address or None, how) of the 1.00 data address `addr`."""
        if self.refs is None:
            print("Reading which code builds which address...")
            self.refs = self.old.lis_pairs(), self.new.lis_pairs()
        old_refs, new_refs = self.refs
        built = {}
        for site in [s for s, v in old_refs.items() if v == addr][:40]:
            moved, _ = self.code(site)
            if moved in new_refs:
                built[new_refs[moved]] = built.get(new_refs[moved], 0) + 1
        if len(built) > 1:
            return None, f"the code builds different addresses: {', '.join(hex(v) for v in built)}"
        same = []
        for k, mask in ((10, branch_mask), (6, branch_mask), (4, branch_mask), (8, address_mask)):
            same = search(self.old, self.new, addr, k, mask)
            if len(same) == 1:
                break
        if built:
            (moved, n), = built.items()
            if len(same) == 1 and same[0] != moved:
                return None, f"the code builds 0x{moved:x}, the same words are at 0x{same[0]:x}"
            return moved, f'built by {n} piece(s) of code'
        if len(same) == 1:
            return same[0], 'same words'
        return None, f'{len(same)} places with the same words'

    def descriptor(self, addr):
        """(1.01 address or None, how) of the function descriptor `addr` (function, TOC): the nearest descriptor of the
        moved function with the same TOC (descriptors of one function are alike)."""
        func, toc = self.old.word(addr), self.old.word(addr + 4)
        if toc != self.old.toc:
            return None, 'not a function descriptor'
        moved, _ = self.code(func)
        if moved is None:
            return None, f'its function 0x{func:x} not found'
        vaddr, off, size = self.new.segs[1]
        hits = [vaddr + i for i in range(0, size - 7, 4)
                if struct.unpack_from('>II', self.new.data, off + i) == (moved, self.new.toc)]
        if not hits:
            return None, 'no descriptor of the moved function'
        return min(hits, key=lambda h: abs(h - addr)), f'descriptor of the moved function 0x{moved:x}'


def port(old, new, say=print):
    """{1.00 address: 1.01 address} of gamepatch.port_addresses(), or None when one is missing or differs."""
    wanted = sorted(gamepatch.port_addresses())
    descriptors = {w for a, was, now, _ in gamepatch.writes() if a in gamepatch.VALUE_ADDRESSES for w in (was, now)}
    porter = Porter(old, new)
    kinds = {a: 'descriptor' if a in descriptors else 'data' if a in DATA or a >= new.segs[1][0] else 'code'
             for a in wanted}
    for a in wanted:                        # the exact ones first: they guide the rest
        if kinds[a] == 'code':
            hits = search(old, new, a, 10, branch_mask)
            if len(hits) == 1:
                porter.moves[a] = hits[0], 'same words'
    found, bad = {}, 0
    for a in wanted:
        b, how = getattr(porter, kinds[a])(a)
        if b is None:
            bad += 1
            say(f"MISSING 0x{a:08x} ({kinds[a]}): {how}")
            continue
        same = (kinds[a] == 'descriptor' or old.word(a) == new.word(b) if kinds[a] != 'code'
                else branch_mask(old.word(a)) == branch_mask(new.word(b)))
        bad += not same
        found[a] = b
        say(f"{'ok ' if same else 'BAD'} 0x{a:08x} -> 0x{b:08x} ({b - a:+#x}) {kinds[a]}: {how}"
            + ('' if same else f"   (1.00 0x{old.word(a):08x}, 1.01 0x{new.word(b):08x})"))
    for b in {b for b in found.values() if list(found.values()).count(b) > 1}:
        bad += 1
        say(f"BAD 0x{b:08x} is the 1.01 place of more than one: {', '.join(hex(a) for a in found if found[a] == b)}")
    # a place told apart from its look-alikes only by its neighbour's move: every word from that neighbour to it alike
    sure = {a: b for a, b in found.items() if kinds[a] == 'code' and 'neighbour' not in porter.moves[a][1]}
    for a in (a for a in found if kinds[a] == 'code' and 'neighbour' in porter.moves[a][1]):
        delta = found[a] - a
        sides = [x for x in sure if sure[x] - x == delta and abs(x - a) < 0x4000]
        if not any(all(loose_mask(old.word(w)) == loose_mask(new.word(w + delta))
                       for w in range(min(x, a), max(x, a) + 4, 4)) for x in sides):
            bad += 1
            say(f"BAD 0x{a:08x}: no neighbour moved by {delta:+#x} with every word alike up to it")
    return None if bad else found


def check(new, table, say=print):
    """Does every word the 1.01 patch says the game has (gamepatch.hooks('01.01') with `table`) match the program?"""
    was = gamepatch.at
    gamepatch.at = lambda addr, version='01.00': addr if version == '01.00' else table[addr]
    try:
        bad = [(a, w, new.word(a)) for a, w in gamepatch.hooks('01.01') if new.word(a) != w]
    finally:
        gamepatch.at = was
    for a, w, have in bad:
        say(f"BAD 1.01 word at 0x{a:08x}: the patch says 0x{w:08x}, the program has 0x{have or 0:08x}")
    return not bad


def module_text(table):
    pairs = [f"0x{a:08x}: 0x{b:08x}," for a, b in sorted(table.items())]
    rows = ["    " + " ".join(pairs[i:i + 4]) for i in range(0, len(pairs), 4)]
    return ('"""Update 1.01\'s address of every place the game patch names (gamepatch.port_addresses), by its 1.00 '
            'address.\nMade by tools/port_patch.py from the two decrypted programs; do not edit by hand."""\n'
            "ADDRESSES = {\n" + "\n".join(rows) + "\n}\n")


def main(argv):
    args = [a for a in argv[1:] if a != '--write']
    if len(args) != 2:
        raise SystemExit(__doc__)
    old, new = Program(args[0]), Program(args[1])
    if old.hash not in gamepatch.HASHES.values():
        raise SystemExit(f"{args[0]} is not NHL Legacy 1.00 (PPU hash {old.hash})")
    if new.hash != gamepatch.UPDATE_HASH:
        raise SystemExit(f"{args[1]} is not NHL Legacy 1.01 (PPU hash {new.hash})")
    table = port(old, new)
    if table is None or not check(new, table):
        print("Not written: fix the places above first.")
        return 1
    print(f"{len(table)} places found, every 1.01 word checks out")
    if '--write' in argv:
        with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
            f.write(module_text(table))
        print(f"Written: {os.path.normpath(OUT)}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
