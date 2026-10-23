"""LAB probe: which rows of the team equipment table (vbHh) paint a team's helmets. Writes a NEW roster file.

    python tools\\helmet_probe.py <SYS-DATA of a LAB roster> [-o <new file>] [--slot 22] [--team-value N]
                                 [--equipment N] [--variant N] [--era N] [--sozv]

Table vbHh (stockteamequipmenttable) holds 9 colour zones per (team, equipment, variant, brand, era) row; its `team` is
the team's slot + 1 (0: no team; docs/notes/equipment.md "Helmet colour source (0.21.0)"). The probe paints a team's
rows in loud colours, so one look at the team in the game says which row and zone colours what:

  stage 1 (default)        every row of the team, all 9 zones in one colour per equipment number
                           (1 green, 2 magenta, 3 yellow, 4 cyan, 5 orange, 8 blue, any other white)
  stage 2 (--equipment N)  only that equipment's rows, each zone in a colour of its own (zone 1 blue ... 9 white)
  --variant / --era        only the rows of that variant (jersey version) / era (which era a normal game uses is open)
  --sozv                   also the team's stock colours (sozv, by slot): colour 0 violet, 1 teal, 2 olive

None of the colours is red, so red left on a helmet comes from somewhere else. The legend is printed and written next to
the new file (<new file>.legend.txt). The input is only read; the new file never replaces an existing one and is never
written into an RPCS3 folder: copy it into a LAB roster save yourself (never the player's own rosters).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from legacy_roster.roster import Roster  # noqa: E402

TABLE = 'vbHh'
BY_EQUIPMENT = {1: ('green', (0, 255, 0)), 2: ('magenta', (255, 0, 255)), 3: ('yellow', (255, 255, 0)),
                4: ('cyan', (0, 255, 255)), 5: ('orange', (255, 128, 0)), 8: ('blue', (0, 0, 255))}
OTHER = ('white', (255, 255, 255))
BY_ZONE = {1: ('blue', (0, 0, 255)), 2: ('green', (0, 255, 0)), 3: ('magenta', (255, 0, 255)),
           4: ('yellow', (255, 255, 0)), 5: ('cyan', (0, 255, 255)), 6: ('orange', (255, 128, 0)),
           7: ('violet', (128, 0, 255)), 8: ('pink', (255, 128, 192)), 9: ('white', (255, 255, 255))}
SOZV = {0: ('violet', (128, 0, 255)), 1: ('teal', (0, 128, 128)), 2: ('olive', (128, 128, 0))}


def in_rpcs3(path):
    """The path lies in an RPCS3 folder (its dev_hdd0, or a folder that holds rpcs3.exe / RPCS3's config)."""
    path = os.path.abspath(path)
    if 'dev_hdd0' in path.replace('\\', '/').lower().split('/'):
        return True
    folder = os.path.dirname(path)
    while True:
        if any(os.path.exists(os.path.join(folder, n)) for n in ('rpcs3.exe', 'rpcs3', 'GuiConfigs')):
            return True
        up = os.path.dirname(folder)
        if up == folder:
            return False
        folder = up


def paint(R, team_value, equipment=None, variant=None, sozv_slot=None, era=None):
    """Paint the rows; returns the legend's lines."""
    E = R.f[TABLE]
    legend, counts = [], {}
    for row in range(E.cur_rec):
        if E.get(row, 'team') != team_value:
            continue
        eq = E.get(row, 'equipment')
        wanted = {'equipment': equipment, 'variant': variant, 'era': era}
        if any(want is not None and E.get(row, name) != want for name, want in wanted.items()):
            continue
        for zone in range(1, 10):
            _name, rgb = BY_ZONE[zone] if equipment is not None else BY_EQUIPMENT.get(eq, OTHER)
            for c, v in zip('rgb', rgb):
                E.set(row, f"zone{zone}_{c}", v)
        counts[eq] = counts.get(eq, 0) + 1
    legend.append(f"vbHh rows with team = {team_value}" + (f", equipment {equipment}" if equipment is not None else "")
                  + (f", variant {variant}" if variant is not None else "")
                  + (f", era {era}" if era is not None else "") + ":")
    for eq in sorted(counts):
        if equipment is None:
            legend.append(f"  equipment {eq}: {counts[eq]} rows, all zones {BY_EQUIPMENT.get(eq, OTHER)[0]}")
        else:
            legend.append(f"  equipment {eq}: {counts[eq]} rows; zones: " +
                          ', '.join(f"{z} {BY_ZONE[z][0]}" for z in range(1, 10)))
    if not counts:
        legend.append("  (none: nothing painted)")
    if sozv_slot is not None:
        S = R.f['sozv']
        for row in range(S.cur_rec):
            if S.get(row, 'team') == sozv_slot and S.get(row, 'colorid') in SOZV:
                name, rgb = SOZV[S.get(row, 'colorid')]
                for c, v in zip('rgb', rgb):
                    S.set(row, f"color_{c}", v)
                legend.append(f"sozv team {sozv_slot} colour {S.get(row, 'colorid')}: {name}")
    return legend


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('roster', help="SYS-DATA of a LAB roster (only read)")
    ap.add_argument('-o', '--out', help="the new file (default: next to the input, <input>.helmet-probe)")
    ap.add_argument('--slot', type=int, default=22, help="the team's slot (default 22: Utah)")
    ap.add_argument('--team-value', type=int, help="vbHh's team value to paint (default: slot + 1)")
    ap.add_argument('--equipment', type=int, help="stage 2: only this equipment number, a colour per zone")
    ap.add_argument('--variant', type=int, help="only this variant (jersey version)")
    ap.add_argument('--era', type=int, help="only this era (0, 1 or 2)")
    ap.add_argument('--sozv', action='store_true', help="also paint the slot's stock colours (sozv)")
    args = ap.parse_args(argv)
    out = args.out or args.roster + '.helmet-probe'
    if in_rpcs3(out):
        sys.exit(f"refused: {out} is inside an RPCS3 folder; write it elsewhere (-o) and copy it into a LAB save")
    if os.path.exists(out):
        sys.exit(f"refused: {out} exists; pick a new name (-o)")
    with open(args.roster, 'rb') as f:
        R = Roster(f.read())
    team_value = args.slot + 1 if args.team_value is None else args.team_value
    legend = [f"helmet probe of slot {args.slot} ({R.team_name(args.slot)}), from {os.path.basename(args.roster)}"]
    legend += paint(R, team_value, args.equipment, args.variant, args.slot if args.sozv else None, args.era)
    with open(out, 'wb') as f:
        f.write(R.f.build())
    with open(out + '.legend.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(legend) + '\n')
    print('\n'.join(legend))
    print(f"written: {out} (and {out}.legend.txt)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
