"""Which picture each player and club shows: the roster side of "Photos and logos".

A player's menu portrait is the art file p<artid>.big (`artid` and `hasportrait` in his record).
When photos are switched on, every player the update placed and who has a photo link gets one:

- an id the game already uses for him keeps it: EA's own ids (1-12,401, the disc's portraits) and
  the community roster's ids (12,402-13,826, its portrait pack). His file is replaced by the
  current photo;
- anyone else gets an id of his own from NEW_IDS. Ids are remembered per person on this PC
  (`Registry`), so the same player keeps his picture in every roster made here, and the next
  update writes the same ids again (a build on its own output stays byte-identical).

Clubs need no change in the roster: a club's logo is the file t<artid>.big of its team record.

`plan()` returns the pictures to make; `install.py` downloads, draws and writes them. Nothing
here needs Pillow.
"""
import json
import os
import unicodedata

from .. import datasource

from .. import layout as L

EA_IDS = range(1, 12402)           # the disc's portraits
COMMUNITY_IDS = range(12402, 13827)  # the community roster's portrait pack
NEW_IDS = range(20000, 65536)       # ours (artid is 16 bits)
SHARED_POOL_ART = 20054             # the custom logo every prospect pool of the base roster uses
POOL_ART = 21000                    # + slot: a pool's own logo (team artid is 15 bits)
CUSTOM_LEAGUE = 13
# NHL slots the community roster gave to newer teams; the game's text still names the old ones
NHL_NAMES = {22: ("Utah Mammoth", "Utah", "UTA"), 30: ("Seattle Kraken", "Seattle", "SEA"),
             31: ("Vegas Golden Knights", "Vegas", "VGK")}


def person_key(first, last, birth):
    """A player's identity across rosters: plain-letter name and birthdate."""
    plain = lambda s: unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower().strip()
    return f"{plain(first)}|{plain(last)}|{birth[0]:04d}-{birth[1]:02d}-{birth[2]:02d}"


class Registry:
    """Portrait ids given out on this PC: {person key: id}, kept in a small JSON file."""

    def __init__(self, path=None):
        self.path = path or datasource.app_dir('art', 'portrait_ids.json')
        self.ids = {}
        try:
            with open(self.path, encoding='utf-8') as f:
                self.ids = {k: int(v) for k, v in json.load(f).items()}
        except (OSError, ValueError):
            pass
        self.dirty = False

    def id_for(self, key, current, taken):
        """The id for a person: his remembered one, else the id he has in the roster if it is
        one of ours and nobody else's, else the next free one."""
        if key in self.ids:
            return self.ids[key]
        owners = {v: k for k, v in self.ids.items()}
        if current in NEW_IDS and current not in owners:
            aid = current
        else:
            used = set(owners) | taken
            aid = next(i for i in NEW_IDS if i not in used)
        self.ids[key] = aid
        self.dirty = True
        return aid

    def save(self):
        if self.dirty:
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.ids, f, indent=0, sort_keys=True)
            os.replace(tmp, self.path)
            self.dirty = False


def birth_of(P, prow):
    return (P.get(prow, 'dnFq') + 1910, P.get(prow, 'pLKJ') + 1, P.get(prow, 'iwsK') + 1)


def plan(b, registry):
    """Give every placed player with a photo his portrait id (written into the roster) and list
    the pictures to make: ({artid: photo link}, {team artid: (logo link, colours)})."""
    P, T = b.P, b.R.T
    taken = {P.get(r, 'artid') for r in range(P.cur_rec)}
    portraits = {}
    for prow in sorted(b.photos):
        aid = P.get(prow, 'artid')
        if aid not in EA_IDS and aid not in COMMUNITY_IDS:
            key = person_key(P.get(prow, 'PedH'), P.get(prow, 'RMbQ'), birth_of(P, prow))
            aid = registry.id_for(key, aid, taken - {aid})
            taken.add(aid)
            P.set(prow, 'artid', aid)
        P.set(prow, 'hasportrait', 1)
        portraits[aid] = b.photos[prow]
    _pool_logos(b)
    logos = {}
    for slot, url in sorted(b.logos.items()):
        colours = tuple(tuple(T.get(slot, f"{c}color_{x}") for x in 'rgb') for c in ('primary', 'secondary'))
        logos[T.get(slot, 'artid')] = (url, colours)
    return portraits, logos, names(b)


def _pool_logos(b):
    """The prospect pools in the spare custom slots all share one custom logo (art id 20054). Each
    gets an art id of its own and a logo: an NHL "System" pool its NHL team's, a draft class a
    badge with its year (drawn by images.badge)."""
    T, R = b.R.T, b.R
    names_ = {t: n.replace('®', '').strip().lower() for t, n in b.nhl_names.items()}    # before any team edit
    # "Red Wings System" -> the NHL team whose name ends in "red wings" (two-word cities too: "los angeles kings")
    parent_of = lambda nick: next((t for t, n in names_.items() if n.endswith(' ' + nick)), None)
    nhl_logo = {L.API_TO_SLOT[a]: url for a, url in b.data.nhl_logos.items() if a in L.API_TO_SLOT}
    for slot in sorted(L.SPARE):
        if slot >= T.cur_rec or not b.entries_on(slot):
            continue
        name = R.team_name(slot).strip()
        if T.get(slot, 'artid') == SHARED_POOL_ART:
            T.set(slot, 'artid', POOL_ART + slot)
        if name.endswith('System'):
            parent = parent_of(name[:-len('System')].strip().lower())
            if parent is not None and parent in nhl_logo:
                b.logos.setdefault(slot, nhl_logo[parent])
        elif name[:4].isdigit():
            b.logos.setdefault(slot, f"badge:{name[:4]}")


def _nick(full, city):
    """'Rytíři Kladno' with city 'Kladno' -> 'Rytíři'; the full name when nothing sensible is left."""
    rest = full.replace(city, '').strip(' -') if city and city in full else ''
    return rest if len(rest) >= 3 else full


def names(b):
    """The names the menus should show (the game takes them from its text file, loc.py):
    {'teams': [(art code, full, city, nickname, abbreviation)], 'cities': {custom team key: name},
     'force': {art codes written even when the game's own text looks the same}}.

    A custom team shows only the text under its `shortname` (a key like COACHELLA_VALLEY, see
    Builder.custom_city_keys); it gets the team's full name there, unless the game already has a
    text under that key (ANAHEIM for the Ducks copy)."""
    T, R = b.R.T, b.R
    teams, cities = [], {}
    for slot, (full, city, abbr) in NHL_NAMES.items():           # the community's Utah, Seattle, Vegas
        T.set(slot, 'fullname', full)
        T.set(slot, 'shortname', city)
        T.set(slot, 'abbrname', abbr)
    clubs = L.SHL | L.LIIGA | L.DEL | L.EXTRALIGA | L.NL | L.NORWAY | L.AHL | L.CHL
    for slot in range(T.cur_rec):
        if slot in L.EVENTS or not b.entries_on(slot):
            continue
        if T.get(slot, 'league') == CUSTOM_LEAGUE and not L.is_city_key(T.get(slot, 'shortname')):
            # a city the game cannot find a text for ("NhlCityName_13" on the Kings copy, a roster made
            # by version 0.4): a key in the game's style; a copy takes its NHL team's city (LOS_ANGELES)
            city = T.get(L.MIRROR_OF[slot], 'shortname') if slot in L.MIRROR_OF else T.get(slot, 'shortname')
            L.set_city(T, slot, city or T.get(slot, 'fullname'))
        art = T.get(slot, 'artabbr')
        full, city, abbr = T.get(slot, 'fullname'), T.get(slot, 'shortname'), T.get(slot, 'abbrname')
        if T.get(slot, 'league') == CUSTOM_LEAGUE:
            if L.is_city_key(city):
                name = full
                if slot in L.MIRROR_OF:         # the game has texts for the copies' cities; a fallback only
                    primary = T.get(L.MIRROR_OF[slot], 'shortname')
                    name = primary if L.city_key(primary) == city else city.replace('_', ' ').title()
                cities[city] = (name or city.replace('_', ' ').title()).replace('®', '').strip()
            if slot in b.team_names and slot not in L.MIRROR_OF:
                teams.append((art, full, city, _nick(full, city), abbr))
        elif slot in NHL_NAMES or slot in clubs or slot in b.team_names:
            teams.append((art, full, city, _nick(full, city), abbr))
    return {'teams': teams, 'cities': cities, 'force': {T.get(s, 'artabbr') for s in set(NHL_NAMES) | set(b.team_names)}}
