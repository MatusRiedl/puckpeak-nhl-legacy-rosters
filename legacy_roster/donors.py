"""Player records for people who are not in the save yet.

The player table cannot simply grow, so a new player takes over an existing record:
  1. a blanked "ZZ" record (the community roster's deleted players) -- the normal case;
  2. when those run out for a position: a teamless, low-rated record of a former player, the
     oldest first. Never taken: legends and well-rated players, anyone whose NHL rights a team
     holds, anyone younger than MIN_AGE, free agents, and anyone whose name appears in the data
     being applied (he may still be placed later in the same run).

Taking a record over also wipes what belonged to its previous owner: portrait, commentary
name, draft and career data.
"""
import zlib
from collections import Counter

from . import layout as L
from .matching import norm

LEGEND_LEVEL = 84      # teamless records at or above this level are kept (legends, recent stars)
MIN_AGE = 26           # teamless records of younger players are kept (prospects who may sign anywhere)
EA_ART_MAX = 12401     # portrait ids up to here are EA's own (records from EA's 2015 database)
UNDRAFTED = 255
GENERIC_HEAD = 60000   # head ids from here on are the game's generic head models
CAREER_FIELDS = ('nhlgamesplayedcareer', 'progamesplayedcareer', 'nhlgamesplayedlastseason',
                 'nhlgamesplayedtwoseasonsago', 'nhlgamesplayedthreeseasonsago', 'nhlgamesmissedinjurylastseason')
NORTH_AMERICA = (L.NAT_CODE['CAN'], L.NAT_CODE['USA'])


def real_birth_year(P, i):
    """The player's actual birth year, as well as the record tells it.

    This roster family stores birth years as year - 1910, but records nobody updated since EA's
    2015 database still hold year - 1900 and read ten years too young. The draft year (stored as
    year - 1900 in both) gives such records away; an undrafted record with EA's own portrait is
    taken to be one of them too."""
    shown = P.get(i, 'dnFq') + 1910
    drafted = P.get(i, 'WzKY')
    if drafted != UNDRAFTED:
        return drafted + 1900 - 18
    if 0 < P.get(i, 'rnOl') <= EA_ART_MAX and shown >= 1990:
        return shown - 10
    return shown


class Donors:
    def __init__(self, b):
        self.b = b
        R, P = b.R, b.P
        fa = {R.link_to_pid.get(l) for l in b.fa_links}
        self.blank = {pos: [] for pos in range(5)}   # ZZ records by position, in row order
        self.spare = {pos: [] for pos in range(5)}   # other teamless records, oldest first
        self.reserved = set()                        # normalised (first, last) of people in the data
        heads, home = Counter(), {}
        youngest = b.data.season_year - MIN_AGE
        for i in range(P.cur_rec):
            pid = P.get(i, 'zIBw')
            country = P.get(i, 'hleL')
            if R.entries_by_pid.get(pid):
                home.setdefault(country, Counter())[P.get(i, 'IxvQ')] += 1
                if P.get(i, 'DaPp') >= GENERIC_HEAD and not P.get(i, 'LcvS'):
                    heads[(P.get(i, 'DaPp'), P.get(i, 'QDTK'))] += 1
                continue
            if pid in fa or pid not in b.quality:
                continue
            pos = P.get(i, 'aljv')
            if 'ZZ' in P.get(i, 'RMbQ'):
                self.blank[pos].append(i)
            elif (b.quality[pid] < LEGEND_LEVEL and not P.get(i, 'WBbd') and real_birth_year(P, i) <= youngest
                  and len(b.records_of[b.identity(i)]) == 1):      # not a second record of someone else in the game
                self.spare[pos].append(i)
        for pos in self.spare:
            self.spare[pos].sort(key=lambda i: (real_birth_year(P, i), b.quality[P.get(i, 'zIBw')], i))
        # (head id, skin colour) pairs the base uses for players without a real head. Nothing says
        # what a new player looks like, so he gets one of the heads of the most common skin colour.
        skin = Counter()
        for (_head, colour), n in heads.items():
            skin[colour] += n
        usual = skin.most_common(1)[0][0] if skin else 1
        self.generic_heads = sorted(k for k in heads if k[1] == usual) or [(GENERIC_HEAD, 1)]
        # the usual birth-state code per country (Ontario for Canada, ...)
        self.home_state = {c: cnt.most_common(1)[0][0] for c, cnt in home.items()}

    def available(self, pos):
        return len(self.blank[pos]) + len(self.spare[pos])

    def left(self, kind):
        """Records left for goalies ('G') or for skaters of any position ('S': they can switch)."""
        return self.available(4) if kind == 'G' else sum(self.available(p) for p in range(4))

    def take(self, pos, target=None):
        """A record for a new player at position `pos` (None when nothing is left).

        Skaters share one attribute table, so when a skater position has no record left, one of
        another skater position is taken and turned into this position (goalies have a table of
        their own and cannot borrow).

        `target`: prefer the blank record whose rating level is closest to it -- matters for
        players who keep the record's ratings because nobody publishes ratings for them."""
        prow = self._take(pos, target)
        if prow is not None or pos == 4:
            return prow
        same_class = lambda q: (q == 3) == (pos == 3)
        for q in sorted((q for q in range(4) if q != pos), key=lambda q: (not same_class(q), -self.available(q), q)):
            prow = self._take(q, target)
            if prow is not None:
                self.b.set_position(prow, pos)
                return prow
        return None

    def _take(self, pos, target):
        b = self.b
        blank = self.blank[pos]
        if blank:
            if target is None:
                return blank.pop(0)
            k = min(range(len(blank)), key=lambda j: (abs(b.quality[b.P.get(blank[j], 'zIBw')] - target), j))
            return blank.pop(k)
        spare = self.spare[pos]
        while spare:
            i = spare.pop(0)
            pid = b.P.get(i, 'zIBw')
            if pid in b.attached or b.person(i) in self.reserved:
                continue
            return i
        return None

    def reserve(self, people):
        """People named in the data being applied: their existing records are not for reuse."""
        self.reserved.update((norm(p['first']), norm(p['last'])) for p in people)

    def reset_identity(self, prow, name, country_code=None, birth_year=None):
        """Wipe what belonged to the record's previous owner."""
        b, P = self.b, self.b.P
        P.set(prow, 'LcvS', 0)        # hasportrait
        P.set(prow, 'rnOl', 0)        # artid (menu portrait)
        P.set(prow, 'Nzao', 0)        # audioid (commentary name)
        head, skin = self.generic_heads[zlib.crc32(name.encode()) % len(self.generic_heads)]
        P.set(prow, 'DaPp', head)     # headid: a generic head model, never the previous owner's
        P.set(prow, 'QDTK', skin)
        P.set(prow, 'WzKY', UNDRAFTED)
        for f in ('Ujcc', 'WfTt', 'uWgv', 'WBbd', 'yNbZ', 'MHEA'):   # draft round/position/team, proteam, junior team/league
            P.set(prow, f, 0)
        for f in CAREER_FIELDS:
            P.set(prow, f, 0)
        for f in ('ORwy', 'UVQB'):    # rookieahl, rookiechl
            P.set(prow, f, 0)
        if birth_year is not None:
            P.set(prow, 'vnCd', 1 if birth_year >= b.data.season_year - 20 else 0)   # rookie
        if country_code is not None:
            old = P.get(prow, 'hleL')
            P.set(prow, 'hleL', country_code)
            if country_code not in NORTH_AMERICA:
                P.set(prow, 'IxvQ', country_code)            # birth "state" of non-North Americans is the country
            elif old != country_code:
                P.set(prow, 'IxvQ', self.home_state.get(country_code, P.get(prow, 'IxvQ')))
