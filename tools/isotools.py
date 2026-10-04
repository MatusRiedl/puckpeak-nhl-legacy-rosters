"""List or read files of the NHL Legacy game disc (maintainer tool; the code is legacy_roster/art/disc.py).

    python tools/isotools.py <game.iso | game folder> <archive.big> [name-filter]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from legacy_roster.art.disc import EbArchive, IsoImage  # noqa: E402,F401  (decode_schema.py imports them from here)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit("usage: python tools/isotools.py <game.iso | game folder> <archive.big> [name-filter]")
    arc = EbArchive.open(sys.argv[1], sys.argv[2])
    flt = sys.argv[3].lower() if len(sys.argv) > 3 else ''
    for nm, (off, size, packed) in sorted(arc.entries.items()):
        if flt in nm.lower():
            print(f"{size:10d}  {nm}")
