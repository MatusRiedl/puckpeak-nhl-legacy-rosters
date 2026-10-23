"""Check the game patch (legacy_roster/gamepatch.py) against the game's decrypted program: every patched address must
hold the word the patch expects the game to have, and each old / new word is shown as an instruction (capstone, when
installed: pip install capstone).

    python tools/audit_patch.py <EBOOT.ELF>

The ELF is the decrypted EBOOT of NHL Legacy EU 01.00 (made with RPCS3's Utilities > Decrypt PS3 Binaries); it stays on
the PC that has the game and is never shipped. Exit code 1 when a word does not match.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from legacy_roster import gamepatch  # noqa: E402


def segments(data):
    """[(vaddr, file offset, size in the file)] of an ELF64 big-endian file."""
    if data[:4] != b'\x7fELF' or data[4] != 2 or data[5] != 2:
        raise SystemExit("not a 64-bit big-endian ELF (decrypt the EBOOT first)")
    phoff, = struct.unpack_from('>Q', data, 0x20)
    phentsize, phnum = struct.unpack_from('>HH', data, 0x36)
    out = []
    for n in range(phnum):
        p_type, _, p_offset, p_vaddr, _, p_filesz = struct.unpack_from('>IIQQQQ', data, phoff + n * phentsize)
        if p_type == 1 and p_filesz:
            out.append((p_vaddr, p_offset, p_filesz))
    return out


def word_at(data, segs, addr):
    for vaddr, off, size in segs:
        if vaddr <= addr < vaddr + size:
            return struct.unpack_from('>I', data, off + addr - vaddr)[0]
    return None


def disasm():
    try:
        import capstone
    except ImportError:
        return lambda word, addr: '(pip install capstone to see the instruction)'
    md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)

    def show(word, addr):
        found = list(md.disasm(struct.pack('>I', word), addr))
        return f"{found[0].mnemonic} {found[0].op_str}" if found else '(not an instruction)'
    return show


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    data = open(argv[1], 'rb').read()
    segs = segments(data)
    show = disasm()
    bad = 0
    hooks = gamepatch.hooks()
    for addr, old in hooks:
        have = word_at(data, segs, addr)
        ok = have == old
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} 0x{addr:08x}  game 0x{old:08x} {show(old, addr)}"
              + ('' if ok else f"   (the file has {'nothing' if have is None else f'0x{have:08x}'})"))
    for addr, old, new, why in gamepatch.writes():
        same_kind = new == gamepatch.NOP or (old ^ new) & 0xffff0000 == 0 or addr in gamepatch.OTHER_INSTRUCTIONS
        bad += not same_kind
        print(f"{'   ' if same_kind else 'BAD'} 0x{addr:08x}  ours 0x{new:08x} {show(new, addr):28}  {why}"
              + ('' if same_kind else '   (more than the number changed)')
              + ('   (another instruction)' if addr in gamepatch.OTHER_INSTRUCTIONS else '')
              + ('   (data: the number is what counts)' if addr in gamepatch.DATA_WORDS else ''))
    for addr, code in gamepatch.caves():
        print(f"    our code for 0x{addr:08x} (then back to 0x{addr + 4:08x}):")
        for n, (word, what) in enumerate(code):
            print(f"      +{n * 4:02x}  0x{word:08x} {show(word, 0x10000 + n * 4):28}  {what}")
    print(f"{len(hooks)} replaced instructions, {bad} problems")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
