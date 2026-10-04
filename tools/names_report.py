"""Which team slots of a roster show an old name: full name, short name and abbreviation against
the current real club (NHL from layout.py, every other league from tools/club_slots.json).

    python tools/names_report.py [<roster folder>]     default: the base roster the tests use

Read only. Club slots are renamed by their league's update step; the NHL slots 22/30/31 keep
"Arizona Coyotes", "Green / Red" and "Black / Blue" in the save (Utah, Seattle and Vegas show
through custom slots 229/228/226) until the art test shows where the game takes NHL names from.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from legacy_roster import layout as L  # noqa: E402
from legacy_roster.roster import Roster  # noqa: E402

NHL_SHORT = {'UTA': 'Utah', 'SEA': 'Seattle', 'VGK': 'Vegas'}


def expected():
    """slot -> (full, short, abbr) of the club that belongs there now."""
    out = {}
    names = {code: name for name, code in L.NHL_TEAM_NAMES.items()}
    for code, slot in L.API_TO_SLOT.items():
        # the game's own NHL abbreviations (LA, NJ, SJ, TB) are kept; only the moved teams are checked
        changed = code in NHL_SHORT
        out[slot] = (names.get(code), NHL_SHORT.get(code), code if changed else None)
    with open(os.path.join(ROOT, 'tools', 'club_slots.json'), encoding='utf-8') as f:
        conf = {k: v for k, v in json.load(f).items() if not k.startswith('_')}
    for league in conf.values():
        for part in (league['parts'].values() if 'parts' in league else [league]):
            for slot, club in part['slots'].items():
                out[int(slot)] = (club['full'], club['short'], club['abbr'])
    return out


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('LEGACY_ROSTER_BASE') or \
        os.path.join(ROOT, 'work', 'backup', 'BLES021530202')
    R = Roster(os.path.join(base, 'SYS-DATA'))
    T = R.T
    rows = 0
    for slot, (full, short, abbr) in sorted(expected().items()):
        have = (R.team_name(slot), T.get(slot, 'shortname'), T.get(slot, 'abbrname'))
        want = (full, short, abbr)
        if any(w and h.replace('®', '').replace('™', '') != w for h, w in zip(have, want)):
            rows += 1
            print(f"{slot:3d} {L.LEAGUE_NAMES[T.get(slot, 'league')]:<16} save: {' | '.join(have)}")
            print(f"{'':20} now:  {' | '.join(w or '-' for w in want)}")
    print(f"{rows} slots with an old name, short name or abbreviation")


if __name__ == '__main__':
    main()
