"""Czech Extraliga rosters from the federation's site (hokej.cz).

Every club has a roster page with three tables -- goalies, defencemen, forwards -- giving
number, name, birthdate, stick hand, height, weight and country. Forwards are not split into
centre and wings; captains are not marked. Each player's own page (linked from the roster) shows his
photo (`/static/images/hrac/...`); its address is remembered in tools/cache/extraliga_photos.json, so
a refresh only visits players it has not seen.
"""
import html
import json
import os
import re
import time
import urllib.request

BASE = "https://www.hokej.cz"
POSITIONS = ('G', 'D', 'F')     # the order of the three tables on a roster page
HAND = {'levá': 'L', 'pravá': 'R'}
PHOTO_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cache', 'extraliga_photos.json')
PHOTO = re.compile(r"""(/static/images/hrac/[^"'\s>]+\.(?:png|jpe?g|webp))""", re.I)


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
            page = re.search(r'href="(/hrac/[^"?]+)', row)
            players.append({'page': page.group(1) if page else None,
                'first': first, 'last': last, 'birth': [int(m.group(3)), int(m.group(2)), int(m.group(1))],
                'pos': pos, 'shoots': HAND.get(hand), 'num': int(number) if number.isdigit() else None,
                'height_cm': int(height.split()[0]) if height[:1].isdigit() else None,
                'weight_kg': int(weight.split()[0]) if weight[:1].isdigit() else None,
                'country': country.group(1).upper() if country else None, 'letter': None, 'rookie': False})
    return players


def _get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', 'replace')


def photos(players, log=print):
    """Each player's photo link from his page (or None), remembered between runs."""
    known = {}
    if os.path.exists(PHOTO_CACHE):
        with open(PHOTO_CACHE, encoding='utf-8') as f:
            known = json.load(f)
    fetched = 0
    for p in players:
        page = p.pop('page', None)
        if page and page not in known:
            try:
                found = PHOTO.search(_get(BASE + page))
                known[page] = BASE + found.group(1) if found else None
            except OSError as err:          # this one stays without a photo; the next refresh tries again
                log(f"extraliga: no page for {p['first']} {p['last']}: {err}")
                continue
            fetched += 1
            time.sleep(0.3)
        p['photo'] = known.get(page) if page else None
    os.makedirs(os.path.dirname(PHOTO_CACHE), exist_ok=True)
    with open(PHOTO_CACHE, 'w', encoding='utf-8') as f:
        json.dump(known, f, ensure_ascii=False, indent=0, sort_keys=True)
    log(f"extraliga: photos for {sum(1 for p in players if p.get('photo'))} of {len(players)} players "
        f"({fetched} player pages read)")


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
    photos([p for players in clubs.values() for p in players], log)
    return clubs
