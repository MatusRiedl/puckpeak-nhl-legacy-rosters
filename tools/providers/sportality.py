"""SHL (Sweden) and EHL (Norway) rosters from the leagues' own websites (both run on Sportality).

The site's season filter names the season and the league's series; the regular-season schedule
lists the clubs; one request per club gives the roster (name, number, G/D/F, nationality) and one
request per player adds birthdate, height, weight and shooting side. Forwards are not split into
centre and wings; captains are not marked. Roster entries carry a portrait (a cut-out PNG); the
club logos are SVG only, so they come from Wikipedia (wiki_logo.py).
"""
from .web import ISO2, get_json

SITES = {'shl': ("https://www.shl.se", 'SHL'), 'norway': ("https://www.ehl.no", 'NTH')}
POSITION = {'GK': 'G', 'D': 'D', 'F': 'F'}
PHOTO_WIDTH = 400
HAND = {'left': 'L', 'right': 'R'}


def api(site, path):
    return get_json(f"{site}/api/sports-v2/{path}")


def clubs_of_season(site, series_code, season_year):
    """{club name: team id} of the league's regular season starting in `season_year`."""
    f = api(site, 'season-series-game-types-filter')
    season = next((s['uuid'] for s in f['season'] if s['code'] == str(season_year)), None)
    series = next((s['uuid'] for s in f['series'] if s['code'] == series_code), None)
    regular = next((g['uuid'] for g in f['gameType'] if g['code'] == 'regular'), None)
    if not (season and series and regular):
        raise ValueError(f"{site}: no {series_code} regular season {season_year} in the site's filter")
    games = api(site, f"game-schedule?seasonUuid={season}&seriesUuid={series}&gameTypeUuid={regular}")['gameInfo']
    clubs = {}
    for game in games:
        for side in ('homeTeamInfo', 'awayTeamInfo'):
            t = game[side]
            if t.get('uuid'):
                clubs[(t['names'].get('long') or t['names'].get('full') or t['code']).strip()] = t['uuid']
    return clubs


def photo_of(listed, width=PHOTO_WIDTH):
    """The link of a roster entry's portrait (a cut-out PNG) in the smallest size at least
    `width` wide; the site signs every size, so only the sizes it lists can be used."""
    for media in listed.get('portraitList') or []:
        if media.get('type') != 'portrait':
            continue
        r = media.get('renderedMedia') or {}
        sizes = []
        for item in (r.get('srcset') or '').split(','):
            url, _, w = item.strip().rpartition(' ')
            if url and w[:-1].isdigit():
                sizes.append((int(w[:-1]), url))
        big = sorted(s for s in sizes if s[0] >= width)
        return big[0][1] if big else r.get('url') or None
    return None


def parse_player(listed, details, pos):
    """A roster entry plus its detail record -> a player in the data pack's shape (None without a birthdate)."""
    d = (details or {}).get('athleteData') or {}
    born = d.get('dateOfBirth') or ''
    if len(born) < 10 or not listed.get('firstName') or not listed.get('lastName'):
        return None
    y, m, dd = (int(x) for x in born[:10].split('-'))
    number = listed.get('jerseyNumber')
    return {'photo': photo_of(listed),
            'first': listed['firstName'].strip(), 'last': listed['lastName'].strip(), 'birth': [y, m, dd],
            'pos': pos, 'shoots': HAND.get((d.get('shoots') or '').lower()),
            'num': number if isinstance(number, int) and 0 < number < 100 else None,
            'height_cm': d.get('height') or None, 'weight_kg': d.get('weight') or None,
            'country': ISO2.get((d.get('nationality') or listed.get('nationality') or '').upper()),
            'letter': None, 'rookie': False}


def fetch(season_year, sources=(), log=print, league='shl'):
    """{club name: [player, ...]}. Clubs not in `sources` (no slot in the game) are listed with no
    players, so they show up as left out without costing a request per player."""
    site, series = SITES[league]
    clubs = {}
    for name, team in sorted(clubs_of_season(site, series, season_year).items()):
        if sources and name not in sources:
            clubs[name] = []
            continue
        players = []
        for group in api(site, f"athletes/by-team-uuid/{team}"):
            pos = POSITION.get(group.get('positionCode'))
            if pos is None:
                continue
            for listed in group.get('players', []):
                p = parse_player(listed, api(site, f"athlete-details/{listed['uuid']}"), pos)
                if p:
                    players.append(p)
        clubs[name] = players
        log(f"{league}: {name}: {len(players)} players")
    return clubs
