"""National League (Switzerland) rosters from the league's own app service (nationalleague.ch).

`/api/teams` lists the season's clubs; `/api/player/team/<id>` gives each club's players with
name, number, position, birthdate and captaincy (height, weight, shooting side and nationality are
often empty). Forwards are not split into centre and wings.
"""
from .web import ISO2, get_json

BASE = "https://www.nationalleague.ch/api"
POSITION = {'goalkeeper': 'G', 'defender': 'D', 'forwarder': 'F', 'forward': 'F'}
HAND = {'l': 'L', 'left': 'L', 'r': 'R', 'right': 'R'}


def parse_player(p):
    born = p.get('birth') or ''
    pos = POSITION.get((p.get('position') or '').lower())
    if len(born) < 10 or pos is None or not p.get('firstName') or not p.get('lastName'):
        return None
    y, m, d = (int(x) for x in born[:10].split('-'))
    number = str(p.get('number') or '')
    nation = (p.get('nationality') or '').upper()
    return {'first': p['firstName'].strip(), 'last': p['lastName'].strip(), 'birth': [y, m, d], 'pos': pos,
            'shoots': HAND.get((p.get('hand') or '').lower()),
            'num': int(number) if number.isdigit() and 0 < int(number) < 100 else None,
            'height_cm': p.get('height') or None, 'weight_kg': p.get('weight') or None,
            'country': ISO2.get(nation, nation if len(nation) == 3 else None),
            'letter': 'C' if p.get('isCaptain') else None, 'rookie': False}


def fetch(season_year, sources=(), log=print):
    """{club name: [player, ...]} for every club of the current season."""
    clubs = {}
    for team in sorted(get_json(f"{BASE}/teams"), key=lambda t: t['name']):
        players = [q for q in (parse_player(p) for p in get_json(f"{BASE}/player/team/{team['teamId']}")) if q]
        clubs[team['name']] = players
        log(f"nl: {team['name']}: {len(players)} players")
    return clubs
