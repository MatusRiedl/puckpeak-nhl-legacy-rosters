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
GAMES = BASE + "/tipsport-extraliga/zapasy"
NOT_REGULAR = ('play', 'baráž', 'předkolo', 'kvalifikace')    # words in the names of the other competitions
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


def regular_season(season_year):
    """The id of the season's regular-season competition. The schedule page lists the season's competitions
    ('Tipsport extraliga', 'Play off Tipsport extraligy', 'Baráž o extraligu'); exactly one must be none of the
    others."""
    select = re.search(r'<select[^>]*name="competition"[^>]*>(.*?)</select>',
                       _get(f"{GAMES}?matchList-filter-season={season_year}"), re.S)
    options = re.findall(r'<option value="(\d+)"[^>]*>([^<]*)', select.group(1)) if select else []
    regular = [cid for cid, name in options if cid != '0' and not any(w in name.lower() for w in NOT_REGULAR)]
    if len(regular) != 1:
        raise ValueError(f"extraliga: no single regular season among the competitions of {season_year}: {options}")
    return regular[0]


def club_paths(games, log=print):
    """{club code: club path} from the game pages ('/zapas/<id>'), which link both clubs ('/klub/hc-kometa-brno/22')
    next to their codes. `games` is {game id: (home code, away code)}; a page is read only while it names a club not
    yet known."""
    paths = {}
    for gid in sorted(games, key=int):
        if all(code in paths for code in games[gid]):
            continue
        page = _get(f"{BASE}/zapas/{gid}")
        for side, code in zip(('home', 'visiting'), games[gid]):
            m = re.search(rf'<div class="team-{side}">\s*<a href="(/klub/[^"?]+)[^"]*">.*?'
                          r'<h2 class="short">([^<]*)</h2>', page, re.S)
            if not m or m.group(2).strip() != code:
                raise ValueError(f"extraliga: the page of game {gid} does not show {code} as the {side} club")
            paths[code] = m.group(1)
        time.sleep(0.7)
    if len(set(paths.values())) != len(paths):
        raise ValueError(f"extraliga: two codes lead to one club: {paths}")
    log(f"extraliga: {len(paths)} club codes read from the game pages")
    return paths


def schedule(season_year, log=print):
    """[[date, home club, away club]] of every regular-season game of the season that starts in `season_year` (clubs by
    their path, as `fetch` names them), sorted by date and game id. The calendar feed (`do=events`, local dates) names
    clubs by code and also holds the play-off and the relegation games once they are drawn: only the games of the
    regular-season competition's list (all rounds) are kept, and the codes are turned into paths by the game pages.
    The feed has no pre-season games."""
    competition = regular_season(season_year)
    page = _get(f"{GAMES}?matchList-filter-season={season_year}&matchList-filter-competition={competition}"
                f"&do=matchList-view-all")
    regular = {}
    for gid, row in re.findall(r'<tr data-href="/zapas/(\d+)"[^>]*>(.*?)</tr>', page, re.S):
        codes = [_clean(c) for c in re.findall(r'<span class="preview__name--short">(.*?)</span>', row, re.S)]
        if len(codes) != 2:
            raise ValueError(f"extraliga: game {gid} of the regular season does not name two clubs")
        regular[gid] = tuple(codes)
    time.sleep(0.7)
    events = json.loads(_get(f"{GAMES}?do=events&start={season_year}-07-01&end={season_year + 1}-07-01"))
    dates, others = {}, 0
    for e in events:
        gid = (e.get('url') or '').rsplit('/', 1)[-1]
        if gid not in regular:
            others += 1
            continue
        m = re.match(r'(\S+) - (\S+)', e.get('title') or '')
        if not m or (m.group(1), m.group(2)) != regular[gid] or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', e['start']):
            raise ValueError(f"extraliga: the calendar's game {gid} ({e.get('title')}, {e.get('start')}) "
                             f"is not {' - '.join(regular[gid])}")
        dates[gid] = e['start']
    missing = sorted(set(regular) - set(dates), key=int)
    if not regular or missing:
        raise ValueError(f"extraliga: {len(missing)} of {len(regular)} regular-season games have no date "
                         f"in the calendar (it holds only the current season): {missing[:10]}")
    time.sleep(0.7)
    paths = club_paths(regular, log)
    out = [[dates[g], paths[regular[g][0]], paths[regular[g][1]]]
           for g in sorted(regular, key=lambda g: (dates[g], int(g)))]
    per_club = {}
    for _date, home, away in out:
        for club in (home, away):
            per_club[club] = per_club.get(club, 0) + 1
    log(f"extraliga schedule {season_year}: {len(out)} games, {len(per_club)} clubs, "
        f"{min(per_club.values())}-{max(per_club.values())} per club, {out[0][0]} to {out[-1][0]} "
        f"({others} games of other competitions left out)")
    return out


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
