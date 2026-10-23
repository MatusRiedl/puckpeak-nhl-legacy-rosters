"""DEL (Germany) rosters from the league's site (penny-del.org).

Every club has a roster page ("Kader") with three tables -- forwards, defencemen, goalies --
giving number, photo, name, nationality, shooting side, age, height and weight. The league publishes
the age, not the birthdate: a player gets a birth year that fits his age and the date 1 July,
marked 'birth_approx'. The updater then matches him by full name and that year, and takes the
exact birthdate from the save when it knows him; only players new to the game keep the
approximate date. A name marked '*' is no longer available or not yet licensed and is skipped.
"""
import datetime
import html
import re

from .web import get_text

BASE = "https://www.penny-del.org"
SECTION = {'Stürmer': 'F', 'Verteidiger': 'D', 'Torhüter': 'G'}
HAND = {'L': 'L', 'R': 'R'}
NATION = {'GER': 'DEU', 'SUI': 'CHE', 'DEN': 'DNK', 'LAT': 'LVA', 'SLO': 'SVN', 'NED': 'NLD', 'CRO': 'HRV'}
DAY = re.compile(r'(\d{2})\.(\d{2})\.(\d{4})')


def _clean(text):
    return html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text)).strip())


def birth_from_age(age, today):
    """A birthdate that gives `age` on `today`: 1 July of the fitting year."""
    year = today.year - age - (1 if (today.month, today.day) < (7, 1) else 0)
    return [year, 7, 1]


def photo_of(row):
    """The player's photo in a roster row; players without one show the club's logo instead
    (an SVG, or a picture named after the team), which is not a photo."""
    m = re.search(r'<img[^>]+src="([^"]+)"', row)
    src = html.unescape(m.group(1)) if m else ''
    if not src or src.endswith('.svg') or 'csm_team_' in src or 'csm_empty' in src or '/teams/' in src:
        return None
    return src if src.startswith('http') else BASE + src


def parse_roster(page, today):
    players = []
    for m in re.finditer(r'<table[^>]*>(.*?)</table>', page, re.S):
        before = _clean(page[max(0, m.start() - 400):m.start()])
        pos = next((p for word, p in SECTION.items() if before.endswith(word)), None)
        if pos is None or 'Alter' not in m.group(1):
            continue
        for row in re.findall(r'<tr[^>]*>(.*?)</tr>', m.group(1), re.S):
            cells = [_clean(c) for c in re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)]
            if len(cells) < 8:
                continue
            number, _photo, name, nation, hand, age, height, weight = cells[:8]
            if '*' in name or ' ' not in name or not age.isdigit():
                continue
            first, last = name.split(' ', 1)
            players.append({
                'photo': photo_of(row),
                'first': first, 'last': last, 'birth': birth_from_age(int(age), today), 'birth_approx': True,
                'pos': pos, 'shoots': HAND.get(hand), 'num': int(number) if number.isdigit() and int(number) < 100 else None,
                'height_cm': int(height) if height.isdigit() else None,
                'weight_kg': int(weight) if weight.isdigit() else None,
                'country': NATION.get(nation, nation) or None, 'letter': None, 'rookie': False})
    return players


def parse_schedule(page):
    """[(date, start time, home club, away club)] of a schedule page's rows ("Sonntag, 20.09.2026", home first), clubs
    by the name of their page ('/teams/adler-mannheim/uebersicht'). A club without a link stops with an error: its
    name alone is not the key `fetch` uses."""
    games = []
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', page, re.S):
        day = re.search(r'<td class="team-schedule__date">([^<]*)</td>', row)
        m = DAY.search(day.group(1)) if day else None
        if not m:
            continue
        clock = re.search(r'<td class="team-schedule__time">([^<]*)</td>', row)
        clubs = re.findall(r'<h6 class="team-meta__name[^"]*">(.*?)</h6>', row, re.S)
        slugs = [re.search(r'href="/teams/([a-z0-9\-]+)/', c) for c in clubs]
        if len(clubs) != 2 or not all(slugs):
            raise ValueError(f"del: a game on {day.group(1).strip()} has no club page for "
                             f"{' / '.join(_clean(c) for c in clubs) or 'its clubs'}")
        start = _clean(clock.group(1)).strip('﻿') if clock else ''
        games.append((f"{m.group(3)}-{m.group(2)}-{m.group(1)}", start, slugs[0].group(1), slugs[1].group(1)))
    return games


def schedule(season_year, log=print):
    """[[date, home club, away club]] of every regular-season game of the season that starts in `season_year` (clubs by
    the name of their page, as `fetch` names them), sorted by date, start time and home club (games still to play have
    no id). The statistics section has a schedule per phase: its Hauptrunde pages, one per month, leave out the
    playoffs (and pre-playoffs), which have pages of their own; the league lists no pre-season games."""
    phase = f"{BASE}/statistik/saison-{season_year}-{str(season_year + 1)[2:]}/hauptrunde/spielplan"
    months = list(dict.fromkeys(re.findall(r'value="(/statistik/saison-[0-9\-]+/hauptrunde/spielplan/monat/[a-z]+)"',
                                           get_text(phase, pause=0.7))))
    if not months:
        raise ValueError(f"del: the regular season {season_year}-{season_year + 1} lists no months")
    games = {}
    for path in months:
        for date, start, home, away in parse_schedule(get_text(BASE + path, pause=0.7)):
            games[(date, home, away)] = start
    out = [[date, home, away] for (date, home, away), _start in
           sorted(games.items(), key=lambda kv: (kv[0][0], kv[1], kv[0][1]))]
    if not out:
        raise ValueError(f"del: no regular-season games for {season_year}-{season_year + 1}")
    per_club = {}
    for _date, home, away in out:
        for club in (home, away):
            per_club[club] = per_club.get(club, 0) + 1
    log(f"del schedule {season_year}: {len(out)} games, {len(per_club)} clubs, "
        f"{min(per_club.values())}-{max(per_club.values())} per club, {out[0][0]} to {out[-1][0]} "
        f"({len(months)} months)")
    return out


def fetch(season_year, sources=(), log=print, today=None):
    """{club page name: [player, ...]} for every club on the league's teams page."""
    today = today or datetime.date.today()
    slugs = sorted(set(re.findall(r'href="/teams/([a-z0-9\-]+)/kader"', get_text(f"{BASE}/teams"))))
    clubs = {}
    for slug in slugs:
        page = get_text(f"{BASE}/teams/{slug}/kader", pause=0.7)
        if f"hauptrunde-{str(season_year)[2:]}{str(season_year + 1)[2:]}" not in page:
            raise ValueError(f"{slug}: the roster page is not for {season_year}-{season_year + 1}")
        clubs[slug] = parse_roster(page, today)
        log(f"del: {slug}: {len(clubs[slug])} players")
    return clubs
