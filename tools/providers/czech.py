"""Czech Extraliga rosters from the federation's site (hokej.cz).

Every club has a roster page with three tables -- goalies, defencemen, forwards -- giving
number, name, birthdate, stick hand, height, weight and country. Forwards are not split into
centre and wings; captains are not marked.
"""
import html
import re
import time
import urllib.request

BASE = "https://www.hokej.cz"
POSITIONS = ('G', 'D', 'F')     # the order of the three tables on a roster page
HAND = {'levá': 'L', 'pravá': 'R'}


def _clean(text):
    return html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text)).strip())


def parse_roster(page):
    tables = [t for t in re.findall(r'<table[^>]*>(.*?)</table>', page, re.S) if 'Narozen' in t]
    if len(tables) != 3:
        raise ValueError(f"expected three roster tables, found {len(tables)}")
    players = []
    for pos, table in zip(POSITIONS, tables):
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.S):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
            if len(cells) < 7:
                continue
            number, name, born, _age, hand, height, weight = (_clean(c) for c in cells[:7])
            m = re.fullmatch(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', born)
            if not m or ' ' not in name:
                continue
            first, last = name.split(' ', 1)
            country = re.search(r'class="country-([a-z]{3})"', row)
            players.append({
                'first': first, 'last': last, 'birth': [int(m.group(3)), int(m.group(2)), int(m.group(1))],
                'pos': pos, 'shoots': HAND.get(hand), 'num': int(number) if number.isdigit() else None,
                'height_cm': int(height.split()[0]) if height[:1].isdigit() else None,
                'weight_kg': int(weight.split()[0]) if weight[:1].isdigit() else None,
                'country': country.group(1).upper() if country else None, 'letter': None, 'rookie': False})
    return players


def fetch(season_year, sources=(), log=print):
    """{club path: [player, ...]} for the club paths in `sources` ('/klub/hc-kometa-brno/22')."""
    clubs = {}
    for path in sources:
        req = urllib.request.Request(f"{BASE}{path}/soupiska", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = r.read().decode('utf-8', 'replace')
        if f"{season_year}-{season_year + 1}" not in page:
            raise ValueError(f"{path}: the roster page is not for {season_year}-{season_year + 1}")
        clubs[path] = parse_roster(page)
        log(f"extraliga: {path.split('/')[2]}: {len(clubs[path])} players")
        time.sleep(0.7)
    return clubs
