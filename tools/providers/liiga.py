"""Liiga (Finland) rosters from the league's own public feed.

One request returns every registered player of the season with club, birthdate, position,
handedness, number, size, nationality and a photo (a cut-out PNG). Forwards are not split into
centre and wings. The league's team list links logos on a retired server (old.liiga.fi), so the
logos come from Wikipedia (wiki_logo.py). A second request gives the season's calendar (`schedule`).
"""
import json
import urllib.request

URL = "https://liiga.fi/api/v2/players/info?tournament=runkosarja&fromSeason={end}&toSeason={end}"
GAMES = "https://liiga.fi/api/v2/games?tournament=runkosarja&season={end}"
ROLE = {'GOALIE': 'G', 'DEFENSEMAN': 'D', 'STRIKER': 'F'}
HAND = {'LEFT': 'L', 'RIGHT': 'R'}


def get(url):
    """The feed's JSON; some of its calls answer 403 without a browser's User-Agent."""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def schedule(season_year, log=print):
    """[[date, home club, away club]] of every regular-season game of the season that starts in `season_year` (the
    local date of the game; clubs by their name in the feed, as `fetch` names them), sorted by date and game id. The
    feed's `season` is the year the season ends; play-off rows (`serie` PLAYOFFS) and places still to be decided
    (`teamPlaceholder`) are left out."""
    games = {}
    for g in get(GAMES.format(end=season_year + 1)):
        home, away = g.get('homeTeam') or {}, g.get('awayTeam') or {}
        start = home.get('gameStartDateTime') or ''      # local time with its offset; `start` is UTC
        if ((g.get('serie') or 'RUNKOSARJA') != 'RUNKOSARJA' or not (home.get('teamName') and away.get('teamName'))
                or home.get('teamPlaceholder') or away.get('teamPlaceholder') or len(start) < 10):
            continue
        games[g['id']] = [start[:10], home['teamName'], away['teamName']]
    if not games:
        raise ValueError(f"liiga: no regular-season games {season_year} in the feed")
    out = [games[i] for i in sorted(games, key=lambda i: (games[i][0], i))]
    per_club = {}
    for _date, home, away in out:
        for club in (home, away):
            per_club[club] = per_club.get(club, 0) + 1
    log(f"liiga schedule {season_year}: {len(out)} games, {len(per_club)} clubs, "
        f"{min(per_club.values())}-{max(per_club.values())} per club, {out[0][0]} to {out[-1][0]}")
    return out


def fetch(season_year, sources=(), log=print):
    """{club name in the feed: [player, ...]} for the season starting in `season_year`."""
    data = get(URL.format(end=season_year + 1))
    clubs = {}
    for p in data:
        if p.get('removed') or p.get('role') not in ROLE or not p.get('dateOfBirth'):
            continue
        y, m, d = (int(x) for x in p['dateOfBirth'][:10].split('-'))
        clubs.setdefault(p['teamName'], []).append({
            'photo': p.get('pictureUrl') or None,
            'first': (p.get('firstName') or '').strip(), 'last': (p.get('lastName') or '').strip(),
            'birth': [y, m, d], 'pos': ROLE[p['role']], 'shoots': HAND.get(p.get('handedness')),
            'num': p.get('jersey') or None, 'height_cm': p.get('height') or None, 'weight_kg': p.get('weight') or None,
            'country': p.get('nationality') or None,
            'letter': 'C' if p.get('captain') else 'A' if p.get('alternateCaptain') else None,
            'rookie': bool(p.get('rookie'))})
    log(f"liiga: {sum(len(v) for v in clubs.values())} players in {len(clubs)} clubs")
    return clubs
