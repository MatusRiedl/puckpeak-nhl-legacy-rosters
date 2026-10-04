"""Where things live in a roster of the community family: "ROSTER2526", its descendants such as the
community's 2026-27 roster, and the rosters this program makes from them.

The game has 252 fixed team slots in 16 fixed leagues. The updater never adds a team and never
changes a team's league (hard limits of the game); it only refills existing slots.
"""
import re
import unicodedata
from collections import Counter

# ttOk.league
LEAGUE_NAMES = {0: 'NHL', 1: 'AHL', 2: 'SHL', 3: 'Liiga', 4: 'DEL', 5: 'Extraliga', 6: 'National League',
                7: 'Norway', 8: 'National', 9: 'OHL', 10: 'QMJHL', 11: 'WHL', 12: 'Top Prospects',
                13: 'Custom', 14: 'Winter Classic', 15: 'EASHL'}
CUSTOM_LEAGUE = 13
TEAM_COUNT = 252
MAX_PER_TEAM = 40                 # roster entry ids (ulGe.key) are team * 40 + slot
XWOT_UNSET = (1 << 14) - 1

# NHL.com team code -> team slot. Slot 22 is the old Arizona slot (holds Utah); Seattle and Vegas
# live in the two All-Star slots.
API_TO_SLOT = {'ANA': 0, 'WPG': 1, 'BOS': 2, 'BUF': 3, 'CGY': 4, 'CAR': 5, 'CHI': 6, 'COL': 7, 'CBJ': 8,
               'DAL': 9, 'DET': 10, 'EDM': 11, 'FLA': 12, 'LAK': 13, 'MIN': 14, 'MTL': 15, 'NSH': 16,
               'NJD': 17, 'NYI': 18, 'NYR': 19, 'OTT': 20, 'PHI': 21, 'UTA': 22, 'PIT': 23, 'STL': 24,
               'SJS': 25, 'TBL': 26, 'TOR': 27, 'VAN': 28, 'WSH': 29, 'SEA': 30, 'VGK': 31}
SLOT_TO_API = {v: k for k, v in API_TO_SLOT.items()}
# custom-team copies of NHL teams with current branding; they must mirror their primary team
MIRRORS = {0: [225], 2: [223], 5: [232], 12: [230], 13: [227], 14: [233], 20: [231], 22: [229],
           24: [222], 28: [224], 30: [228], 31: [226]}
MIRROR_OF = {m: p for p, ms in MIRRORS.items() for m in ms}
# what the community calls those copies; a roster whose copies are out of step with their NHL team
# (the 2026-27 community roster) is still recognised by these names
MIRROR_NAMES = {222: 'Blues', 223: 'Bruins', 224: 'Canucks', 225: 'Ducks', 226: 'Golden Knights', 227: 'Kings',
                228: 'Kraken', 229: 'Mammoth', 230: 'Panthers', 231: 'Senators', 232: 'Whalers', 233: 'Wild'}

NHL_PRIMARY = set(range(32))
NHL_ALL = NHL_PRIMARY | set(MIRROR_OF)
AHL = set(range(32, 62)) | {234, 235}   # Coachella Valley and Henderson sit in custom slots
NATIONAL = set(range(133, 154))   # 133 Austria, 134 Belarus, 135 Canada ... 153 USA (132 is a club)
# teams that hold player contracts (cPbu.team = team + 1): NHL and AHL clubs
CLUB = set(range(62)) | {234, 235}
# the club leagues' slots (ttOk.league 2-7 and 9-11)
SHL = set(range(62, 76))
LIIGA = set(range(76, 91))
DEL = set(range(91, 105))
EXTRALIGA = set(range(105, 119))
NL = set(range(119, 131))
NORWAY = {131, 132}
EUROPE = SHL | LIIGA | DEL | EXTRALIGA | NL | NORWAY
OHL = set(range(154, 174))
QMJHL = set(range(174, 192))
WHL = set(range(192, 214))
CHL = OHL | QMJHL | WHL
EVENTS = set(range(214, 222))     # Top Prospects, Winter Classic, EASHL: left alone
SPARE = range(236, 252)           # custom slots switched off in the base: room for displaced prospect pools
# the base roster keeps its NHL "System" prospect pools here (DEL 101-104, Extraliga, National League)
SYSTEM_POOL_SLOTS = set(range(101, 131))
# farm teams the NHL team table cannot name (ttOk.ahlaffiliate has six bits): Coachella Valley -> Seattle,
# Henderson -> Vegas
AHL_PARENT_EXTRA = {234: 30, 235: 31}

POS_CODE = {'C': 0, 'L': 1, 'R': 2, 'D': 3, 'G': 4}
POS_CLASS = {0: 'C', 1: 'W', 2: 'W', 3: 'D', 4: 'G'}
POS_NAME = {0: 'C', 1: 'LW', 2: 'RW', 3: 'D', 4: 'G'}
# cPbu.intlcountry codes (decoded from the players in the file)
NAT_CODE = {'SWE': 69, 'USA': 14, 'FIN': 67, 'CAN': 0, 'RUS': 76, 'NOR': 68, 'CZE': 82, 'CHE': 97, 'DEU': 85,
            'SVK': 95, 'BLR': 70, 'DNK': 66, 'AUT': 78, 'LVA': 74, 'FRA': 84, 'AUS': 98, 'JPN': 109, 'KAZ': 72,
            'UKR': 77, 'GBR': 83, 'POL': 91, 'ITA': 87, 'HUN': 86, 'SVN': 96, 'NLD': 89, 'LTU': 75, 'HRV': 81}
# national teams the original mod left empty, filled from the latest IIHF rosters
EMPTY_NATIONAL = {'AUT': 133, 'BLR': 134, 'GBR': 141, 'JPN': 143, 'KAZ': 144, 'NOR': 146, 'POL': 147, 'UKR': 152}
# how much weaker (rating-field units) than the mod's European national players an unrated player is
NATIONAL_TIER = {'AUT': 0, 'NOR': 0, 'BLR': 0, 'GBR': -2, 'KAZ': -2, 'POL': -3, 'UKR': -3, 'JPN': -3,
                 'DEU': 1, 'CHE': 1, 'SVK': 1, 'LVA': 0, 'DNK': 0, 'FRA': -1, 'ITA': -2}
# national team (ttOk abbreviation) -> birth country code used by the NHL data
NATIONAL_ISO = {'CAN': 'CAN', 'CZE': 'CZE', 'DEN': 'DNK', 'FIN': 'FIN', 'FRA': 'FRA', 'GER': 'DEU', 'ITA': 'ITA',
                'LAT': 'LVA', 'RUS': 'RUS', 'SLV': 'SVK', 'SWE': 'SWE', 'SWI': 'CHE', 'USA': 'USA',
                'AUS': 'AUT', 'BEL': 'BLR', 'GBR': 'GBR', 'JPN': 'JPN', 'KAZ': 'KAZ', 'NOR': 'NOR', 'POL': 'POL',
                'UKR': 'UKR'}

# NHL.com team codes by the full names other sources use
NHL_TEAM_NAMES = {
    'Anaheim Ducks': 'ANA', 'Boston Bruins': 'BOS', 'Buffalo Sabres': 'BUF', 'Calgary Flames': 'CGY',
    'Carolina Hurricanes': 'CAR', 'Chicago Blackhawks': 'CHI', 'Colorado Avalanche': 'COL',
    'Columbus Blue Jackets': 'CBJ', 'Dallas Stars': 'DAL', 'Detroit Red Wings': 'DET', 'Edmonton Oilers': 'EDM',
    'Florida Panthers': 'FLA', 'Los Angeles Kings': 'LAK', 'Minnesota Wild': 'MIN', 'Montreal Canadiens': 'MTL',
    'Nashville Predators': 'NSH', 'New Jersey Devils': 'NJD', 'New York Islanders': 'NYI', 'New York Rangers': 'NYR',
    'Ottawa Senators': 'OTT', 'Philadelphia Flyers': 'PHI', 'Pittsburgh Penguins': 'PIT', 'San Jose Sharks': 'SJS',
    'Seattle Kraken': 'SEA', 'St. Louis Blues': 'STL', 'Tampa Bay Lightning': 'TBL', 'Toronto Maple Leafs': 'TOR',
    'Utah Mammoth': 'UTA', 'Vancouver Canucks': 'VAN', 'Vegas Golden Knights': 'VGK', 'Washington Capitals': 'WSH',
    'Winnipeg Jets': 'WPG'}


def team_code(name):
    """NHL.com code for a team given as a code or a full name (None when unknown)."""
    if name in API_TO_SLOT:
        return name
    return NHL_TEAM_NAMES.get(name)


# country codes as leagues and the IOC write them, where they differ from the ISO codes above
COUNTRY_ALIASES = {'GER': 'DEU', 'SUI': 'CHE', 'DEN': 'DNK', 'LAT': 'LVA', 'SLO': 'SVN', 'NED': 'NLD',
                   'CRO': 'HRV', 'ENG': 'GBR'}


def country_code(code):
    """cPbu.intlcountry value for an ISO or IOC country code (None when the game's code is not known)."""
    if not code:
        return None
    code = code.upper()
    return NAT_CODE.get(COUNTRY_ALIASES.get(code, code))
# born abroad but represent another country -- never picked for their birth country's team
NOT_ELIGIBLE = {('mason', 'mctavish'), ('benoitolivier', 'groulx')}


def city_key(text):
    """A custom team's city as a key in the game's own style: 'Coachella Valley' -> COACHELLA_VALLEY.

    A custom team's name in the menus is the game's text whose key is its `shortname` (art/loc.py).
    The keys that show are written like the game's own (ANAHEIM, LAS_VEGAS); the community's
    "NhlCityName_13" and the texts this program added under "Coachella Valley" or
    "2026 Prospects 2" showed nothing in the game (owner, 2026-10-04)."""
    plain = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Z0-9]+', '_', plain.upper()).strip('_')


def is_city_key(text):
    return bool(re.fullmatch(r'[A-Z0-9_]+', text or ''))


def set_city(T, slot, city):
    """Write a team's city (`shortname`); a custom team's as a key in the game's style."""
    if T.get(slot, 'league') == CUSTOM_LEAGUE and not is_city_key(city):
        city = city_key(city) or city
    T.set(slot, 'shortname', city[:T.field('shortname').bits // 8 - 1])


class LayoutError(ValueError):
    """The roster is not one the updater can work on."""


# the layouts the updater works on (check_base): the community roster family, and the game's own
# roster (stock.py: from the player's disc, or saved in the game without loading a community roster)
COMMUNITY, STOCK = 'community', 'stock'


def mirrors(kind):
    """The custom copies of NHL teams a layout keeps in step: none in the game's own roster."""
    return MIRRORS if kind == COMMUNITY else {}


def team_leagues(R):
    return [R.T.get(t, 'jjMx') for t in range(R.T.cur_rec)]


def check_base(R):
    """The layout of `R` (COMMUNITY or STOCK); LayoutError when the updater cannot work on it.

    Two layouts are known: the community roster family, and the game's own roster (30 NHL teams
    and the All-Star teams, the custom teams switched off; stock.py prepares it). Anything else,
    and a different table set, is rejected with a message a player can act on. The custom copies
    of NHL teams of a community roster may be out of step with their team (the update makes them
    copies again): they are recognised by their name or by sharing most players with it."""
    from . import stock
    T, U = R.T, R.U
    if T.cur_rec != TEAM_COUNT:
        raise LayoutError(f"this roster has {T.cur_rec} teams; the updater needs the 252-team NHL Legacy layout")
    count = Counter(U.get(i, 'BSXd') for i in range(U.cur_rec))
    if any(count[t] > MAX_PER_TEAM for t in count):
        raise LayoutError("a team has more than 40 players")
    if stock.is_stock(R):
        return STOCK
    if not all(count[m] for m in MIRROR_OF) or not T.get(222, 'NYKk'):
        raise LayoutError(
            "some of the custom copies of NHL teams are missing, so this is neither the game's own roster nor a "
            "community roster. Pick another roster, or start from the game's own roster.")
    members = {}
    for i in range(U.cur_rec):
        members.setdefault(U.get(i, 'BSXd'), set()).add(R.link_to_pid.get(U.get(i, 'TWSX')))
    for prim, mirrors in MIRRORS.items():
        for m in mirrors:
            if R.team_name(m).replace('®', '').strip() == MIRROR_NAMES[m]:
                continue
            a, b = members.get(prim, set()), members.get(m, set())
            if len(a & b) < 0.6 * max(len(a), len(b), 1):
                raise LayoutError(
                    f"{R.team_name(m)} (team {m}) is not a copy of {R.team_name(prim)} in this roster; "
                    "the team layout differs from the community roster.")
    return COMMUNITY
