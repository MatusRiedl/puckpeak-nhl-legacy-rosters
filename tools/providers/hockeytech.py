"""AHL, OHL, QMJHL and WHL rosters from HockeyTech, the stats service the leagues' own websites use.

The keys below are the public ones those websites send with every page view (checked
2026-10-03); if a league changes its key, copy the new one from the `key=` parameter of the
lscluster.hockeytech.com requests its website makes. One request per club; a roster row gives
name, birthdate, position (C/LW/RW or F, D or LD/RD, G), shoots, height, weight, number,
birthplace, a photo and, in the AHL, whether the player is on an NHL or an AHL contract. The
club list gives each club's logo (PNG). The captain and alternates come from the club's last GAMES game summaries (their
line-ups mark them: `status` 'C' / 'A'), counted over the games (providers/letters.py).
"""
import re
import urllib.parse

from .letters import count_letters
from .web import country_of_place, get_json, inches_to_cm, pounds_to_kg

FEED = "https://lscluster.hockeytech.com/feed/index.php"
KEYS = {'ahl': '50c2cd9b5e18e390', 'ohl': '2976319eb44abe94', 'whl': '41b145a848f4bd67', 'lhjmq': 'f322673b6bcae299'}
POSITION = {'C': 'C', 'LW': 'L', 'RW': 'R', 'F': 'F', 'W': 'F', 'D': 'D', 'LD': 'D', 'RD': 'D', 'G': 'G'}
GAMES = 5                       # a club's last games read for its captains


def call(client, view, **params):
    query = dict(feed='modulekit', view=view, key=KEYS[client], client_code=client, fmt='json', lang='en', **params)
    return get_json(f"{FEED}?{urllib.parse.urlencode(query)}")['SiteKit']


def game_summary(client, game_id):
    query = dict(feed='gc', tab='gamesummary', game_id=game_id, key=KEYS[client], client_code=client, fmt='json',
                 lang='en')
    return get_json(f"{FEED}?{urllib.parse.urlencode(query)}")['GC']['Gamesummary']


def lineup_letters(summary, team_id):
    """{(first, last) lower case: 'C' | 'A'} of the club `team_id`'s line-up in one game summary."""
    side = 'home_team_lineup' if str(summary['meta']['home_team']) == str(team_id) else 'visitor_team_lineup'
    return {((p.get('first_name') or '').strip().lower(), (p.get('last_name') or '').strip().lower()): p['status']
            for p in (summary.get(side) or {}).get('players', []) if p.get('status') in ('C', 'A')}


def club_letters(client, season, team_id, cache, log=print):
    """{(first, last) lower case: 'C' | 'A'}: the club's captain and alternates over its last GAMES finished games ({}
    when the feed has none or cannot be read)."""
    try:
        games = [g for g in call(client, 'schedule', season_id=season, team_id=team_id)['Schedule'] if g.get('final') == '1']
        games.sort(key=lambda g: (g['date_played'], int(g['game_id'])))
        seen = []
        for g in games[-GAMES:]:
            if g['game_id'] not in cache:
                cache[g['game_id']] = game_summary(client, g['game_id'])
            seen.append(lineup_letters(cache[g['game_id']], team_id))
        return count_letters(seen)
    except (OSError, ValueError, KeyError, TypeError) as err:     # the captains are a bonus: the roster still counts
        log(f"{client}: team {team_id}: captains not read: {err}")
        return {}


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


def schedule(season_year, client='ahl', log=print):
    """[[date, home club, away club]] of every regular-season game of the season that starts in `season_year` (clubs by
    their name in the feed, as `fetch` names them), sorted by date and game id."""
    season = regular_season(client, season_year)
    games = sorted(call(client, 'schedule', season_id=season)['Schedule'],
                   key=lambda g: (g['date_played'], int(g['game_id'])))
    out = [[g['date_played'], g['home_team_name'], g['visiting_team_name']] for g in games]
    per_club = {}
    for _date, home, away in out:
        for club in (home, away):
            per_club[club] = per_club.get(club, 0) + 1
    log(f"{client} schedule {season_year}: {len(out)} games, {len(per_club)} clubs, "
        f"{min(per_club.values())}-{max(per_club.values())} per club, {out[0][0]} to {out[-1][0]}")
    return out


def fetch(season_year, sources=(), log=print, client='ahl'):
    """{club name in the feed: [player, ...]} for every club of the league's regular season,
    '_logos': {club name: logo link}, and '_former': last season's players who are on no club's
    list now, with their photo (a junior the list leaves out stays with his club and keeps a picture:
    Landon DuPont, testers 0.8.0)."""
    season = regular_season(client, season_year)
    clubs, logos, summaries = {}, {}, {}
    for team in call(client, 'teamsbyseason', season_id=season)['Teamsbyseason']:
        rows = call(client, 'roster', season_id=season, team_id=team['id'])['Roster']
        players = [p for p in (parse_player(r) for r in rows) if p]
        letters = club_letters(client, season, team['id'], summaries, log)
        for p in players:
            if p['pos'] != 'G':
                p['letter'] = letters.get((p['first'].lower(), p['last'].lower()))
        clubs[team['name']] = players
        if (team.get('team_logo_url') or '').startswith('http'):
            logos[team['name']] = team['team_logo_url']
        log(f"{client}: {team['name']}: {len(players)} players, "
            f"{sum(1 for p in players if p['letter'])} letters")
    clubs['_logos'] = logos
    now = {(p['first'].lower(), p['last'].lower(), tuple(p['birth'])) for players in clubs.values()
           if isinstance(players, list) for p in players}
    former = {}
    try:
        last = regular_season(client, season_year - 1)
        for team in call(client, 'teamsbyseason', season_id=last)['Teamsbyseason']:
            for p in (parse_player(r) for r in call(client, 'roster', season_id=last, team_id=team['id'])['Roster']):
                key = (p['first'].lower(), p['last'].lower(), tuple(p['birth'])) if p else None
                if p and p.get('photo') and key not in now:
                    former[key] = {'first': p['first'], 'last': p['last'], 'birth': p['birth'], 'photo': p['photo']}
    except (OSError, ValueError, KeyError) as err:        # last season's lists are a bonus
        log(f"{client}: last season's rosters not read: {err}")
    clubs['_former'] = [former[k] for k in sorted(former)]
    log(f"{client}: {len(former)} players of last season who are on no list now (photos kept)")
    return clubs
