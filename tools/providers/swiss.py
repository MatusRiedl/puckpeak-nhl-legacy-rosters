"""National League (Switzerland) rosters from the league's own app service (nationalleague.ch).

`/api/teams` lists the season's clubs; `/api/player/team/<id>` gives each club's players with
name, number, position, birthdate and captaincy (height, weight, shooting side and nationality are
often empty). Forwards are not split into centre and wings.
"""
import datetime

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


def swiss_date(utc):
    """'2026-10-25T18:45:00+00:00' (UTC) -> the date in Switzerland: UTC+1, UTC+2 in summer time (from the last Sunday
    of March to the last Sunday of October, 01:00 UTC both)."""
    t = datetime.datetime.fromisoformat(utc.replace('Z', '+00:00')).astimezone(datetime.timezone.utc)

    def last_sunday(month):         # March and October have 31 days
        day = datetime.datetime(t.year, month, 31, 1, tzinfo=datetime.timezone.utc)
        return day - datetime.timedelta(days=(day.weekday() + 1) % 7)
    summer = last_sunday(3) <= t < last_sunday(10)
    return (t + datetime.timedelta(hours=2 if summer else 1)).date().isoformat()


def game_ids(node):
    """Every gameId in an answer of rounds, series and games (`/games/playoffs`, `/games/playouts`)."""
    if isinstance(node, dict):
        if 'gameId' in node:
            yield node['gameId']
        for value in node.values():
            yield from game_ids(value)
    elif isinstance(node, list):
        for value in node:
            yield from game_ids(value)


def schedule(season_year, log=print):
    """[[date, home club, away club]] of every regular-season game of the season that starts in `season_year` (clubs by
    their name in `/api/teams`, as `fetch` names them), sorted by date and game id. The feed names a season by its end
    year and lists the pre-season (`isExhibition`), the play-in, the playoffs, the playouts and the league
    qualification with the regular season: the last four are left out by the game ids `/games/playoffs` and
    `/games/playouts` give. Its times are UTC; the date is the Swiss one."""
    season = season_year + 1
    names = {t['teamId']: t['name'] for t in get_json(f"{BASE}/teams")}
    later = set()
    for part in ('playoffs', 'playouts'):
        later |= set(game_ids(get_json(f"{BASE}/games/{part}?season={season}")))
    games = get_json(f"{BASE}/games?season={season}")
    regular = [g for g in games if not g.get('isExhibition') and g['gameId'] not in later]
    unknown = sorted({g[f'{side}TeamName'] for g in regular for side in ('home', 'away')
                      if g[f'{side}TeamId'] not in names})
    if unknown:
        raise ValueError(f"nl: clubs of the {season_year}-{season} schedule that /api/teams does not list: {unknown}")
    if not regular:
        raise ValueError(f"nl: no regular-season games for {season_year}-{season}")
    out = [[swiss_date(g['date']), names[g['homeTeamId']], names[g['awayTeamId']]]
           for g in sorted(regular, key=lambda g: (swiss_date(g['date']), int(g['gameId'])))]
    per_club = {}
    for _date, home, away in out:
        for club in (home, away):
            per_club[club] = per_club.get(club, 0) + 1
    log(f"nl schedule {season_year}: {len(out)} games, {len(per_club)} clubs, "
        f"{min(per_club.values())}-{max(per_club.values())} per club, {out[0][0]} to {out[-1][0]} "
        f"({sum(1 for g in games if g.get('isExhibition'))} pre-season and "
        f"{sum(1 for g in games if not g.get('isExhibition') and g['gameId'] in later)} later games left out)")
    return out


def fetch(season_year, sources=(), log=print):
    """{club name: [player, ...]} for every club of the current season."""
    clubs = {}
    for team in sorted(get_json(f"{BASE}/teams"), key=lambda t: t['name']):
        players = [q for q in (parse_player(p) for p in get_json(f"{BASE}/player/team/{team['teamId']}")) if q]
        clubs[team['name']] = players
        log(f"nl: {team['name']}: {len(players)} players")
    return clubs
