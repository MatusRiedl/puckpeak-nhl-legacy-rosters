"""Liiga (Finland) rosters from the league's own public feed.

One request returns every registered player of the season with club, birthdate, position,
handedness, number, size, nationality and a photo (a cut-out PNG). Forwards are not split into
centre and wings. The league's team list links logos on a retired server (old.liiga.fi), so the
logos come from Wikipedia (wiki_logo.py).
"""
import json
import urllib.request

URL = "https://liiga.fi/api/v2/players/info?tournament=runkosarja&fromSeason={end}&toSeason={end}"
ROLE = {'GOALIE': 'G', 'DEFENSEMAN': 'D', 'STRIKER': 'F'}
HAND = {'LEFT': 'L', 'RIGHT': 'R'}


def fetch(season_year, sources=(), log=print):
    """{club name in the feed: [player, ...]} for the season starting in `season_year`."""
    req = urllib.request.Request(URL.format(end=season_year + 1), headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
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
