"""Build the data pack the updater ships with and downloads (legacy_roster/data/datapack.json.gz).

    python tools/build_datapack.py                     rebuild from the caches in tools/cache
    python tools/build_datapack.py --refresh ratings   crawl nhlratings.net first (slow, polite)
    python tools/build_datapack.py --refresh iihf      download the IIHF roster PDFs first
    python tools/build_datapack.py --refresh shl,chl   fetch club leagues first (a league or one part: ohl)
    python tools/build_datapack.py --research DIR      reuse the lab's research folder as the cache

The pack holds everything the updater does not fetch live:
    ea_ratings   EA ratings of NHL players
    iihf         rosters for the national teams the base roster leaves empty
    leagues      club rosters per league, already placed into the game's team slots (tools/club_slots.json)
    nhl          a snapshot of the NHL rosters, used only when the user is offline
    nhl_last     everyone who played in the NHL last season (birthdate, size, hand, team now): who is
                 retired and who is an unsigned free agent (refreshed with nhl)
    drafts       every NHL draft pick since FIRST_DRAFT (refreshed with nhl)

Before writing, every part is compared with the pack being replaced: a part that is gone or has
lost more than 40% of its entries stops the build (a feed that changed its layout looks like that).
Pass --accept-drops when the drop is real.
"""
import argparse
import datetime
from collections import Counter
import functools
import gzip
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from legacy_roster import datasource  # noqa: E402
from legacy_roster.layout import API_TO_SLOT  # noqa: E402
from providers import czech, ea_ratings, hockeytech, iihf, liiga, nhl_facts, penny_del, sportality, swiss, wiki_logo  # noqa: E402

# one feed per part of a league (club_slots.json); a part's cache is tools/cache/<part>.json
FEEDS = {'liiga': liiga.fetch, 'extraliga': czech.fetch,
         'shl': functools.partial(sportality.fetch, league='shl'),
         'del': penny_del.fetch, 'nl': swiss.fetch,
         'norway': functools.partial(sportality.fetch, league='norway'),
         'ahl': functools.partial(hockeytech.fetch, client='ahl'),
         'ohl': functools.partial(hockeytech.fetch, client='ohl'),
         'qmjhl': functools.partial(hockeytech.fetch, client='lhjmq'),
         'whl': functools.partial(hockeytech.fetch, client='whl')}
CACHE = os.path.join(ROOT, 'tools', 'cache')
OUT = os.path.join(ROOT, 'legacy_roster', 'data', 'datapack.json.gz')
SLOTS = os.path.join(ROOT, 'tools', 'club_slots.json')
SEASON = 2026
MIN_FULL_RATINGS = 300          # fewer fully rated players means the ratings parser broke (Oct 2026: 373)
MAX_DROP = 0.4                  # a part that loses more than this share of its entries stops the build
MIN_AGE, MAX_AGE = 15, 45       # club players outside these ages are typos in the feed
LEAGUE_MIN_AGE = {'ahl': 17}    # juniors may be 15 (exceptional status), AHL players not
MAX_SHARED_PHOTO = 3            # this many players with the same photo link: it is a placeholder
# ESPN's logos for dark backgrounds (the game's menus are dark): only Tampa Bay's and Washington's differ
# from the plain ones, and those two were hard to see (testers, 0.7.0)
NHL_LOGO = "https://a.espncdn.com/i/teamlogos/nhl/500-dark/{}.png"
FIRST_DRAFT = 2005              # the oldest players still playing were drafted about then
ESPN_CODE = {'UTA': 'utah', 'TBL': 'tb', 'NJD': 'nj', 'SJS': 'sj', 'LAK': 'la'}


def file_date(path):
    return f"{datetime.datetime.fromtimestamp(os.path.getmtime(path)):%Y-%m-%d}"


def wiki_logo_of(title):
    """A club's logo link from Wikipedia, remembered in tools/cache/logos.json (None if none)."""
    cache = os.path.join(CACHE, 'logos.json')
    known = {}
    if os.path.exists(cache):
        with open(cache, encoding='utf-8') as f:
            known = json.load(f)
    if title not in known:
        try:
            known[title] = wiki_logo.logo_url(title)
        except Exception as err:          # rate limited or offline: try again next build
            print(f"logo of {title}: {err}")
            return None
        os.makedirs(CACHE, exist_ok=True)
        with open(cache, 'w', encoding='utf-8') as f:
            json.dump(known, f, ensure_ascii=False, indent=0, sort_keys=True)
    if not known[title]:
        print(f"logo of {title}: none on Wikipedia (give the club a 'logo' or 'wiki' in club_slots.json)")
    return known[title]


def nhl_logos():
    """NHL.com team code -> logo link. NHL.com has SVG only; ESPN publishes the same marks as PNG."""
    return {abbr: NHL_LOGO.format(ESPN_CODE.get(abbr, abbr.lower())) for abbr in API_TO_SLOT}


def parts_of(conf, key):
    """[(part key, league_id, slots)] of a league in club_slots.json."""
    if 'parts' in conf:
        return [(p, v['league_id'], v['slots']) for p, v in conf['parts'].items()]
    return [(key, conf['league_id'], conf['slots'])]


def build_league(key, conf, refresh):
    """The pack entry of one club league from its parts' caches (fetched first if asked), or None."""
    teams, left_out, extra, former, dates = [], [], [], [], []
    for part, league_id, slots in parts_of(conf, key):
        cache = os.path.join(CACHE, f"{part}.json")
        if key in refresh or part in refresh:
            os.makedirs(CACHE, exist_ok=True)
            clubs = FEEDS[part](SEASON, sources=[c['source'] for c in slots.values()])
            with open(cache, 'w', encoding='utf-8') as f:
                json.dump(clubs, f, ensure_ascii=False)
        if not os.path.exists(cache):
            return None
        with open(cache, encoding='utf-8') as f:
            clubs = json.load(f)
        feed_logos = clubs.pop('_logos', {})
        former += clubs.pop('_former', [])      # last season's players on no list now: their photos
        sources = [c['source'] for c in slots.values()]
        if len(set(sources)) != len(sources):
            sys.exit(f"{part}: a club is mapped to two slots in club_slots.json")
        def plausible(club_name, roster):
            players = []
            for p in roster:
                if SEASON - MAX_AGE <= p['birth'][0] <= SEASON - LEAGUE_MIN_AGE.get(part, MIN_AGE):
                    players.append(p)
                else:           # a typo in the feed (born 2011 in the AHL): left out rather than guessed
                    print(f"{part}: {club_name}: left out {p['first']} {p['last']}, birthdate {p['birth']} "
                          "is not possible")
            return players

        for slot, club in sorted(slots.items(), key=lambda kv: int(kv[0])):
            if club['source'] not in clubs:
                sys.exit(f"{part}: no club named {club['source']!r} in the feed (clubs: {sorted(clubs)})")
            players = plausible(club['full'], clubs[club['source']])
            logo = club.get('logo') or feed_logos.get(club['source']) or wiki_logo_of(club.get('wiki') or club['full'])
            teams.append({'slot': int(slot), 'league_id': club.get('league_id', league_id), 'full': club['full'],
                          'short': club['short'], 'abbr': club['abbr'], 'art': club['art'], 'logo': logo,
                          'players': players})
        for name in sorted(set(clubs) - set(sources)):
            left_out.append(name)
            # no slot in the game: kept for a player's own custom team of that name (clubs.own_teams)
            extra.append({'league_id': league_id, 'full': name, 'short': name, 'abbr': name[:3].upper(),
                          'art': name[:3].upper(), 'logo': feed_logos.get(name), 'players': plausible(name, clubs[name])})
        dates.append(file_date(cache))
    # a picture several players share is a feed's "no photo" placeholder, not a photo
    shared = Counter(p.get('photo') for t in teams for p in t['players'] if p.get('photo'))
    shared.update(p['photo'] for p in former)
    for t in teams + extra:
        t['players'] = [dict(p, photo=None) if shared[p.get('photo')] >= MAX_SHARED_PHOTO else p for p in t['players']]
    former = [p for p in former if shared[p['photo']] < MAX_SHARED_PHOTO]
    entry = {'label': conf['label'], 'country': conf.get('country'), 'teams': teams, 'left_out': left_out,
             'extra': extra, 'former': former}
    if 'parts' not in conf:
        entry['league_id'] = conf['league_id']
    source = {'label': f"{conf['label']} rosters", 'date': min(dates), 'count': sum(len(t['players']) for t in teams)}
    return entry, source


def check_drops(old, new, accept):
    """Stop when a part of the previous pack is missing or much smaller now."""
    problems = []
    for key, src in (old.get('sources') or {}).items():
        now = new['sources'].get(key)
        if now is None:
            problems.append(f"{key}: in the previous pack ({src['count']} entries), missing now")
        elif src['count'] and now['count'] < (1 - MAX_DROP) * src['count']:
            problems.append(f"{key}: {now['count']} entries, the previous pack had {src['count']}")
    full = sum(1 for p in new.get('ea_ratings') or [] if len(p['attrs']) >= 10)
    if 'ea_ratings' in new and full < MIN_FULL_RATINGS:
        problems.append(f"ea_ratings: only {full} players with full attributes (expected {MIN_FULL_RATINGS} or more)")
    if problems and not accept:
        sys.exit("Not written -- a feed may have changed its layout:\n   " + "\n   ".join(problems) +
                 "\nCheck the provider; if the drop is real, run again with --accept-drops.")
    for p in problems:
        print(f"accepted: {p}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--refresh', default='',
                    help="comma list: ratings, iihf, nhl (also nhl_last and drafts), or a league (liiga, extraliga, shl, del, nl, norway, ahl, "
                         "chl) or one part of it (ohl, qmjhl, whl)")
    ap.add_argument('--research', help="lab research folder to use as the cache (work/research)")
    ap.add_argument('--accept-drops', action='store_true', help="write the pack even if a part shrank or vanished")
    ap.add_argument('--out', default=OUT)
    args = ap.parse_args()
    refresh = {x.strip() for x in args.refresh.split(',') if x.strip()}
    ratings_cache = os.path.join(args.research, 'nhl27') if args.research else os.path.join(CACHE, 'nhl27')
    iihf_cache = os.path.join(args.research, 'iihf2026') if args.research else os.path.join(CACHE, 'iihf')
    pack = {'format': datasource.PACK_FORMAT, 'season': SEASON, 'sources': {},
            'generated': f"{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%dT%H:%M:%SZ}"}

    if 'ratings' in refresh:
        ea_ratings.crawl(ratings_cache)
    if os.path.isdir(ratings_cache):
        players = ea_ratings.compact(ea_ratings.parse(ratings_cache))
        pack['ea_ratings'] = players
        pack['sources']['ea_ratings'] = {
            'label': f"EA {ea_ratings.GAME} ratings", 'date': file_date(os.path.join(ratings_cache, '_slugs.json')),
            'count': len(players)}
        full = sum(1 for p in players if len(p['attrs']) >= 10)
        print(f"ratings: {len(players)} players ({full} with full attributes)")

    if 'iihf' in refresh or os.path.isdir(iihf_cache):
        rosters = iihf.fetch(iihf_cache)
        pack['iihf'] = rosters
        pack['sources']['iihf'] = {'label': "IIHF rosters", 'date': file_date(os.path.join(iihf_cache, 'AUT.pdf')),
                                   'count': sum(len(v) for v in rosters.values())}

    # club leagues: the feed's clubs are put into the game's team slots as tools/club_slots.json says
    with open(SLOTS, encoding='utf-8') as f:
        slot_map = {k: v for k, v in json.load(f).items() if not k.startswith('_')}
    pack['leagues'] = {}
    for key, conf in slot_map.items():
        built = build_league(key, conf, refresh)
        if built is None:
            continue
        pack['leagues'][key], pack['sources'][key] = built
        if built[0]['left_out']:
            print(f"{key}: no slot for {', '.join(built[0]['left_out'])}")

    nhl_cache = os.path.join(CACHE, 'nhl.json')
    if 'nhl' in refresh:
        os.makedirs(CACHE, exist_ok=True)
        with open(nhl_cache, 'w', encoding='utf-8') as f:
            json.dump(datasource.fetch_nhl_teams(SEASON, print, fresh=True), f, ensure_ascii=False)
    if os.path.exists(nhl_cache):
        with open(nhl_cache, encoding='utf-8') as f:
            teams = json.load(f)
        pack['nhl'] = teams
        pack['nhl_logos'] = nhl_logos()
        pack['sources']['nhl'] ={'label': "NHL.com rosters (offline copy)", 'date': file_date(nhl_cache),
                                  'count': sum(len(t.get(g, [])) for t in teams.values()
                                               for g in ('forwards', 'defensemen', 'goalies'))}

    # NHL facts for every player: who played last season (retired or unsigned) and the drafts
    for key, fetch in (('nhl_last', lambda: nhl_facts.last_season(SEASON)),
                       ('drafts', lambda: nhl_facts.drafts(FIRST_DRAFT, SEASON))):
        cache = os.path.join(CACHE, f"{key}.json")
        if 'nhl' in refresh or key in refresh:
            os.makedirs(CACHE, exist_ok=True)
            with open(cache, 'w', encoding='utf-8') as f:
                json.dump(fetch(), f, ensure_ascii=False)
        if os.path.exists(cache):
            with open(cache, encoding='utf-8') as f:
                pack[key] = json.load(f)
            label = "NHL.com: last season's players" if key == 'nhl_last' else f"NHL drafts since {FIRST_DRAFT}"
            pack['sources'][key] = {'label': label, 'date': file_date(cache), 'count': len(pack[key])}

    if os.path.exists(args.out):
        check_drops(datasource.read_pack(args.out), pack, args.accept_drops)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    raw = json.dumps(pack, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    with gzip.GzipFile(args.out, 'wb', mtime=0) as f:
        f.write(raw)
    print(f"{args.out}: {os.path.getsize(args.out) / 1024:.0f} KB ({len(raw) / 1024:.0f} KB of JSON)")
    for key, src in pack['sources'].items():
        print(f"   {key}: {src['count']} entries, dated {src['date']}")


if __name__ == '__main__':
    main()
