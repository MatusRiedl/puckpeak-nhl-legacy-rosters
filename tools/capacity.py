"""How much room an update needs and leaves: player records per position, prospect-pool places.

    python tools/capacity.py                          every league in the bundled data pack
    python tools/capacity.py --leagues liiga,shl      only these club leagues
    python tools/capacity.py --base <roster folder>   another base roster (default: as the tests)

Builds in memory (offline: the pack's NHL snapshot) and writes nothing. Run it before adding a
league and record the numbers in docs/ROADMAP.md ("Capacity").
"""
import argparse
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from legacy_roster import datasource, pipeline  # noqa: E402
from legacy_roster.builder import Builder, Data  # noqa: E402
from legacy_roster.leagues import pools  # noqa: E402
from legacy_roster.roster import Roster  # noqa: E402

POSITIONS = ('C', 'LW', 'RW', 'D', 'G')


def records(donors):
    return [len(donors.blank[p]) for p in range(5)], [len(donors.spare[p]) for p in range(5)]


def row(label, values):
    return f"  {label:<28}" + "".join(f"{v:>7}" for v in values) + f"{sum(values):>8}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--base', default=os.environ.get('LEGACY_ROSTER_BASE')
                    or os.path.join(ROOT, 'work', 'backup', 'BLES021530202'))
    ap.add_argument('--leagues', help="comma list of club leagues (default: all in the pack)")
    args = ap.parse_args()
    pack = datasource.read_pack(datasource.BUNDLED_PACK)
    leagues = args.leagues.split(',') if args.leagues else [k for k in pipeline.LEAGUE_ORDER if k in pack['leagues']]
    with open(os.path.join(args.base, 'SYS-DATA'), 'rb') as f:
        base = f.read()
    data = Data(nhl_players=datasource.flatten_nhl(pack['nhl']), ea_ratings=pack['ea_ratings'], iihf=pack['iihf'],
                season_year=pack['season'], leagues={k: pack['leagues'][k] for k in leagues})
    before = records(Builder(Roster(base), data).donors)
    result = pipeline.build(base, data, steps=list(pipeline.CORE_STEPS) + leagues)
    after = records(result.builder.donors)
    b = result.builder
    created = Counter(b.P.get(r, 'aljv') for r in b.created)

    print(f"Leagues: {', '.join(leagues)}   (checks: {'passed' if result.ok else 'FAILED'})")
    print(f"  {'':<28}" + "".join(f"{p:>7}" for p in POSITIONS) + f"{'total':>8}")
    print(row("blank records before", before[0]))
    print(row("reusable records before", before[1]))
    print(row("new players created", [created[p] for p in range(5)]))
    print(row("blank records left", after[0]))
    print(row("reusable records left", after[1]))
    for key in leagues:
        s = b.league_stats.get(key, {})
        print(f"  {pipeline.LEAGUE_NAMES[key]}: {s.get('created', 0)} created, "
              f"{s.get('moved', 0) + s.get('added', 0)} moved in, {s.get('left', 0)} left, "
              f"{s.get('skipped: no free record', 0)} skipped (no record), "
              f"{s.get('pool players moved', 0)} pool players displaced, "
              f"{s.get('kept to fill the line-up', 0) + s.get('signed to fill the line-up', 0)} "
              f"line-up fillers, {s.get('clubs without a full line-up', 0)} clubs without a full line-up")
    R = Roster(result.data)
    spare = [t for t in pools.SPARE_SLOTS if R.T.get(t, 'active')]
    held = sum(1 for e in range(R.U.cur_rec) if R.U.get(e, 'team') in spare)
    print(f"  Prospect pools: {len(spare)} of {len(pools.SPARE_SLOTS)} spare slots in use, {held} players, "
          f"{getattr(b, 'pool_released', 0)} became free agents")
    print(f"  Free agents: {R.Q.cur_rec}")
    if not result.ok:
        print("Problems:\n   " + "\n   ".join(result.problems[:20]))


if __name__ == '__main__':
    main()
