"""EA NHL ratings from nhlratings.net.

    crawl(cache)   download every player page into `cache` (about one request per second,
                   roughly 40 minutes the first time; pages already cached are not fetched again)
    parse(cache)   -> list of players for the data pack

Skater attributes come from each player's page; goalie-specific attributes are only published
on the per-attribute list pages (top 100 each, which covers practically every NHL goalie).
"""
import html
import json
import os
import re
import time
import urllib.error
import urllib.request

BASE = "https://www.nhlratings.net/"
GAME = "NHL 27"
TEAM_SLUGS = {"anaheim-ducks": "ANA", "boston-bruins": "BOS", "buffalo-sabres": "BUF", "calgary-flames": "CGY",
              "carolina-hurricanes": "CAR", "chicago-blackhawks": "CHI", "colorado-avalanche": "COL",
              "columbus-blue-jackets": "CBJ", "dallas-stars": "DAL", "detroit-red-wings": "DET",
              "edmonton-oilers": "EDM", "florida-panthers": "FLA", "los-angeles-kings": "LAK",
              "minnesota-wild": "MIN", "montreal-canadiens": "MTL", "nashville-predators": "NSH",
              "new-jersey-devils": "NJD", "new-york-islanders": "NYI", "new-york-rangers": "NYR",
              "ottawa-senators": "OTT", "philadelphia-flyers": "PHI", "pittsburgh-penguins": "PIT",
              "san-jose-sharks": "SJS", "seattle-kraken": "SEA", "st-louis-blues": "STL",
              "tampa-bay-lightning": "TBL", "toronto-maple-leafs": "TOR", "utah-mammoth": "UTA",
              "vancouver-canucks": "VAN", "vegas-golden-knights": "VGK", "washington-capitals": "WSH",
              "winnipeg-jets": "WPG"}
COUNTRY_SLUGS = ["australia", "austria", "belarus", "belgium", "canada", "czechia", "denmark", "england", "finland",
                 "france", "germany", "italy", "latvia", "netherlands", "norway", "russia", "serbia-and-montenegro",
                 "slovakia", "sweden", "switzerland", "usa", "uzbekistan", "wales"]
GOALIE_LISTS = {"angles": "Angles", "breakaway": "Breakaway", "five-hole": "Five Hole",
                "glove-side-high": "Glove Side High", "glove-side-low": "Glove Side Low",
                "stick-side-high": "Stick Side High", "stick-side-low": "Stick Side Low", "poke-check": "Poke Check",
                "rebound-control": "Rebound Control", "shot-recover": "Shot Recover", "vision": "Vision",
                "puck-playing-frequency": "Puck Playing Frequency", "aggression": "Aggression"}
NOT_PLAYERS = ("teams/", "countries/", "lists/", "about", "contact", "privacy-policy", "terms", "nhl-27-release-date",
               "wp-content", "favicon")
MONTHS = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                          "September", "October", "November", "December"])}
POSITION = {'Center': 'C', 'Left Wing': 'L', 'Right Wing': 'R', 'Defense': 'D', 'Goalie': 'G'}


def fetch(cache, path):
    """GET BASE+path with an on-disk cache."""
    fn = os.path.join(cache, path.strip('/').replace('/', '__') + ".html")
    if os.path.exists(fn):
        with open(fn, encoding='utf-8') as f:
            return f.read()
    req = urllib.request.Request(BASE + path, headers={'User-Agent': 'Mozilla/5.0'})
    for attempt in range(4):
        try:
            body = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')
            break
        except urllib.error.HTTPError as err:  # rate limited or transient: back off politely
            if err.code not in (403, 429, 500, 502, 503) or attempt == 3:
                raise
            time.sleep(30 * (attempt + 1))
    os.makedirs(cache, exist_ok=True)
    with open(fn, 'w', encoding='utf-8') as f:
        f.write(body)
    time.sleep(1.0)
    return body


def text_lines(body):
    body = re.sub(r'<script.*?</script>|<style.*?</style>', '', body, flags=re.S)
    t = html.unescape(re.sub(r'<[^>]+>', '\n', body))
    return [l.strip() for l in t.split('\n') if l.strip()]


def player_links(body):
    out = {}
    for slug, name in re.findall(r'href="https://www\.nhlratings\.net/([a-z0-9\-]+)" title="([^"]+)"', body):
        if not slug.startswith(NOT_PLAYERS):
            out[slug] = html.unescape(name)
    return out


def crawl(cache, log=print):
    slugs = {}
    for t in TEAM_SLUGS:
        slugs.update(player_links(fetch(cache, f"teams/{t}")))
    for c in COUNTRY_SLUGS:
        slugs.update(player_links(fetch(cache, f"countries/{c}")))
    for lst in GOALIE_LISTS:
        slugs.update(player_links(fetch(cache, f"lists/{lst}")))
    log(f"players to fetch: {len(slugs)}")
    for i, slug in enumerate(sorted(slugs)):
        try:
            fetch(cache, slug)
        except Exception as err:  # keep going; parse() skips missing pages
            log(f"failed {slug}: {err}")
        if i % 100 == 0:
            log(f"{i} {slug}")
    with open(os.path.join(cache, "_slugs.json"), 'w', encoding='utf-8') as f:
        json.dump(slugs, f, ensure_ascii=False, indent=1)


def parse_player(slug, body):
    lines = text_lines(body)
    p = {'slug': slug}
    for key, lab in (('nationality', 'Nationality:'), ('team', 'Team:'), ('position', 'Position:')):
        if lab in lines:
            p[key] = lines[lines.index(lab) + 1]
    for l in lines:
        m = re.match(r'Birthdate: (\w+) (\d+), (\d{4})', l)
        if m:
            p['birth'] = [int(m.group(3)), MONTHS[m.group(1)], int(m.group(2))]
            break
    joined = " ".join(lines)
    m = (re.search(rf"(\d+) current Overall Rating in {GAME}", joined)
         or re.search(rf"On {GAME}, .*? has an Overall Rating of (\d+)", joined))
    p['ovr'] = int(m.group(1)) if m else None
    title = re.search(rf'<title>(.*?)(?: {GAME}| \|)', body)
    p['name'] = html.unescape(title.group(1)).strip() if title else slug
    attrs = {}
    head = f'{GAME} Attributes'
    if head in lines and 'Total Attributes' in lines:
        seq = lines[lines.index(head) + 1:lines.index('Total Attributes')]
        for val, lab in zip(seq[0::2], seq[1::2]):  # value comes before its label
            if lab.endswith('Ratings'):
                continue
            attrs[lab] = int(val) if val.isdigit() else None
    p['attrs'] = attrs
    return p


def parse_list(body):
    """Top-100 list page: rank. name pos | team value ovr total."""
    lines = text_lines(body)
    out = {}
    for i, l in enumerate(lines):
        if re.fullmatch(r'\d+\.', l) and i + 6 < len(lines) and lines[i + 3] == '|':
            name, val = lines[i + 1], lines[i + 5]
            if val.isdigit():
                out[name] = int(val)
    return out


def parse(cache):
    players = []
    for fn in sorted(os.listdir(cache)):
        if fn.endswith('.html') and '__' not in fn and not fn.startswith('_'):
            with open(os.path.join(cache, fn), encoding='utf-8') as f:
                players.append(parse_player(fn[:-5], f.read()))
    by_name = {p['name']: p for p in players}
    for lst, label in GOALIE_LISTS.items():
        path = os.path.join(cache, f"lists__{lst}.html")
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            vals = parse_list(f.read())
        for name, v in vals.items():
            if name in by_name and by_name[name]['attrs'].get(label) is None:
                by_name[name]['attrs'][label] = v
    return players


def compact(players):
    """The form stored in the data pack: only rated players, only published values."""
    out = []
    for p in players:
        attrs = {a: v for a, v in (p.get('attrs') or {}).items() if v is not None}
        if not p.get('ovr') and not attrs:
            continue
        pos = (p.get('position') or '').split(' (')[0]
        out.append({'name': p['name'], 'team': TEAM_NAMES.get(p.get('team')), 'position': POSITION.get(pos),
                    'birth': p.get('birth'), 'ovr': p.get('ovr'), 'attrs': attrs})
    return out


TEAM_NAMES = {' '.join(w.capitalize() for w in slug.split('-')).replace('St Louis', 'St. Louis'): code
              for slug, code in TEAM_SLUGS.items()}
