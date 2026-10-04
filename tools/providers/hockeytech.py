"""AHL, OHL, QMJHL and WHL rosters from HockeyTech, the stats service the leagues' own websites use.

The keys below are the public ones those websites send with every page view (checked
2026-10-03); if a league changes its key, copy the new one from the `key=` parameter of the
lscluster.hockeytech.com requests its website makes. One request per club; a roster row gives
name, birthdate, position (C/LW/RW or F, D or LD/RD, G), shoots, height, weight, number,
birthplace, a photo and, in the AHL, whether the player is on an NHL or an AHL contract. The
club list gives each club's logo (PNG).
"""
import re
import urllib.parse

from .web import country_of_place, get_json, inches_to_cm, pounds_to_kg

FEED = "https://lscluster.hockeytech.com/feed/index.php"
KEYS = {'ahl': '50c2cd9b5e18e390', 'ohl': '2976319eb44abe94', 'whl': '41b145a848f4bd67', 'lhjmq': 'f322673b6bcae299'}
POSITION = {'C': 'C', 'LW': 'L', 'RW': 'R', 'F': 'F', 'W': 'F', 'D': 'D', 'LD': 'D', 'RD': 'D', 'G': 'G'}


def call(client, view, **params):
    query = dict(feed='modulekit', view=view, key=KEYS[client], client_code=client, fmt='json', lang='en', **params)
    return get_json(f"{FEED}?{urllib.parse.urlencode(query)}")['SiteKit']


def regular_season(client, season_year):
    """The id of the regular season that starts in `season_year`."""
    for s in call(client, 'seasons')['Seasons']:
        if (s.get('playoff') == '0' and 'regular' in s.get('season_name', '').lower()
                and (s.get('start_date') or '')[:4] == str(season_year)):
            return s['season_id']
    raise ValueError(f"{client}: no regular season starting in {season_year} in the feed")


def parse_player(row):
    """One roster row -> a player in the data pack's shape, or None (staff, no birthdate)."""
    if not isinstance(row, dict) or POSITION.get((row.get('position') or '').upper()) is None:
        return None
    m = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})', row.get('rawbirthdate') or row.get('birthdate') or '')
    first, last = (row.get('first_name') or '').strip(), (row.get('last_name') or '').strip()
    if not m or m.group(1) == '0000' or not first or not last:
        return None
    pos = POSITION[row['position'].upper()]
    hand = (row.get('catches') if pos == 'G' else None) or row.get('shoots') or ''
    number = (row.get('tp_jersey_number') or '').strip()
    photo = row.get('player_image') or ''
    return {'photo': photo if photo.startswith('http') and 'nophoto' not in photo else None,
        'first': first, 'last': last, 'birth': [int(m.group(1)), int(m.group(2)), int(m.group(3))], 'pos': pos,
        'shoots': hand.upper()[:1] if hand.upper()[:1] in ('L', 'R') else None,
        'num': int(number) if number.isdigit() and 0 < int(number) < 100 else None,
        'height_cm': inches_to_cm(row.get('height')), 'weight_kg': pounds_to_kg(row.get('weight')),
        'country': country_of_place(row.get('birthplace'), row.get('homecntry'), row.get('birthcntry')),
        'letter': None, 'rookie': row.get('rookie') == '1',
        'nhl_contract': (row.get('status') or '').upper() == 'NHL'}


def fetch(season_year, sources=(), log=print, client='ahl'):
    """{club name in the feed: [player, ...]} for every club of the league's regular season, and
    '_logos': {club name: logo link}."""
    season = regular_season(client, season_year)
    clubs, logos = {}, {}
    for team in call(client, 'teamsbyseason', season_id=season)['Teamsbyseason']:
        rows = call(client, 'roster', season_id=season, team_id=team['id'])['Roster']
        players = [p for p in (parse_player(r) for r in rows) if p]
        clubs[team['name']] = players
        if (team.get('team_logo_url') or '').startswith('http'):
            logos[team['name']] = team['team_logo_url']
        log(f"{client}: {team['name']}: {len(players)} players")
    clubs['_logos'] = logos
    return clubs
