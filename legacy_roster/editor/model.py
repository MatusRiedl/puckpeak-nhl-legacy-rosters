"""What a roster holds, in the shape the roster editor shows it (no window code here).

`Snapshot` reads a roster save into teams and players; `compare()` tells what an update (or the
player's edits) changed between two of them ("as is" and "to be"). Players are matched across
rosters by person (edits.who_of: plain name + birthdate), because an update may give a player
another record.
"""
import datetime

from .. import edits, ratings
from .. import layout as L
from ..roster import Roster
from ..schema import EA_GOALIE, EA_SKATER, RATING_BASE

POSITION = {0: 'C', 1: 'LW', 2: 'RW', 3: 'D', 4: 'G'}
POS_KEY = {'C': 'C', 'LW': 'L', 'RW': 'R', 'D': 'D', 'G': 'G'}
COUNTRY = {code: iso for iso, code in L.NAT_CODE.items()}
FREE_AGENTS = 'FA'


def _labels(amap):
    """Attribute names in the game's order, one per field."""
    seen, out = set(), []
    for label, field in amap.items():
        if field not in seen:
            seen.add(field)
            out.append(label)
    return out


SKATER_ATTRIBUTES = _labels(EA_SKATER)
GOALIE_ATTRIBUTES = _labels(EA_GOALIE)


class Player:
    __slots__ = ('who', 'prow', 'pid', 'first', 'last', 'pos', 'num', 'birth', 'country', 'shoots', 'height_in',
                 'weight_lb', 'teams', 'ovr', 'ratings', 'artid', 'hasportrait')

    @property
    def name(self):
        return f"{self.first} {self.last}"

    def age(self, season_year):
        y, m, d = self.birth
        return season_year - y - (1 if (m, d) > (9, 15) else 0)     # age at the start of the season

    def values(self):
        """What can be edited, for comparing two rosters."""
        return {'first': self.first, 'last': self.last, 'num': self.num, 'pos': self.pos, 'shoots': self.shoots,
                'birth': self.birth, 'country': self.country, 'height_in': self.height_in,
                'weight_lb': self.weight_lb, 'ovr': self.ovr}


class Snapshot:
    """Teams and players of one roster save (bytes or Roster)."""

    def __init__(self, source, ovr_offset=None, season_year=None):
        self.R = R = source if isinstance(source, Roster) else Roster(source)
        self.season_year = season_year or datetime.date.today().year - (datetime.date.today().month < 9)
        self.offset = ovr_offset or {False: 0.0, True: 0.0}
        P, U, T = R.P, R.U, R.T
        self.team_names = {t: R.team_name(t) for t in range(T.cur_rec)}
        self.team_league = {t: L.LEAGUE_NAMES.get(T.get(t, 'jjMx'), 'Other') for t in range(T.cur_rec)}
        self.rosters = {}                 # team -> [pid]
        teams_of = {}
        for i in range(U.cur_rec):
            pid = R.link_to_pid.get(U.get(i, 'TWSX'))
            t = U.get(i, 'BSXd')
            self.rosters.setdefault(t, []).append(pid)
            teams_of.setdefault(pid, []).append(t)
        self.free_agents = [R.link_to_pid.get(R.Q.get(i, 'TWSX')) for i in range(R.Q.cur_rec)]
        self.rosters[FREE_AGENTS] = self.free_agents
        ai = {}
        for tname in (ratings.SKATER_TABLE, ratings.GOALIE_TABLE):
            t = R.f[tname]
            for i in range(t.cur_rec):
                ai[t.get(i, 'zIBw')] = (tname, i)
        self.players = {}
        for pid in set(teams_of) | set(self.free_agents):
            prow = R.p_by_id.get(pid)
            if prow is None:
                continue
            p = Player()
            p.prow, p.pid = prow, pid
            p.first, p.last = P.get(prow, 'PedH'), P.get(prow, 'RMbQ')
            p.pos = POSITION.get(P.get(prow, 'aljv'), '?')
            p.num = P.get(prow, 'tRVs')
            p.birth = edits.birth_of(P, prow)
            p.who = edits.who_of(P, prow)
            p.country = COUNTRY.get(P.get(prow, 'hleL'), str(P.get(prow, 'hleL')))
            p.shoots = 'R' if P.get(prow, 'pkRG') else 'L'
            p.height_in = P.get(prow, 'QBpy') + 54
            p.weight_lb = P.get(prow, 'WZNs') + 120
            p.teams = sorted(teams_of.get(pid, []))
            p.artid, p.hasportrait = P.get(prow, 'artid'), P.get(prow, 'hasportrait')     # his menu photo
            p.ratings, p.ovr = {}, None
            where = ai.get(pid)
            if where:
                table = R.f[where[0]]
                goalie = where[0] == ratings.GOALIE_TABLE
                amap = EA_GOALIE if goalie else EA_SKATER
                labels = GOALIE_ATTRIBUTES if goalie else SKATER_ATTRIBUTES
                p.ratings = {a: table.get(where[1], amap[a]) + RATING_BASE for a in labels}
                p.ovr = round(ratings.level(table, where[1]) + self.offset[goalie])
            self.players[pid] = p
        self.by_who = {}
        for p in sorted(self.players.values(), key=lambda p: (not [t for t in p.teams if t not in L.NATIONAL], p.prow)):
            self.by_who.setdefault(p.who, p)

    def leagues(self):
        """League names that have players, in the game's order, then free agents."""
        seen = []
        for t in sorted(t for t in self.rosters if t != FREE_AGENTS):
            name = self.team_league[t]
            if self.rosters[t] and name not in seen:
                seen.append(name)
        return seen + ['Free agents']

    def teams_in(self, league):
        if league == 'Free agents':
            return [FREE_AGENTS]
        return [t for t in sorted(t for t in self.rosters if t != FREE_AGENTS)
                if self.team_league[t] == league and self.rosters[t]]

    def team_name(self, team):
        return 'Free agents' if team == FREE_AGENTS else self.team_names.get(team, f"#{team}")

    def roster(self, team):
        return [self.players[pid] for pid in self.rosters.get(team, []) if pid in self.players]

    def search(self, text, limit=200):
        t = text.lower().strip()
        return [p for p in self.by_who.values() if t in p.name.lower()][:limit] if t else []


def club(teams):
    return [t for t in teams if t not in L.NATIONAL and t not in L.MIRROR_OF]


def compare(before, after, team, renamed=None):
    """How `team` changed from `before` to `after` (two Snapshots):
    {'joined': {who: where from}, 'left': [Player of before], 'changed': {who: [field, ...]}}.
    `renamed` maps a renamed player's new key to his old one (edits keep the old one)."""
    renamed = dict(renamed or {})
    # the same record under the same name whose birthdate the update corrected (NHL.com's) is the
    # same person, not one leaving and another joining
    by_pid = {q.pid: q for q in before.roster(team)}
    for p in after.roster(team):
        q = by_pid.get(p.pid)
        if q is not None and q.who != p.who and (q.first, q.last) == (p.first, p.last):
            renamed.setdefault(p.who, q.who)
    old_key = lambda who: renamed.get(who, who)
    now = {old_key(p.who) for p in after.roster(team)}
    was = {p.who for p in before.roster(team)}
    out = {'joined': {}, 'left': [], 'changed': {}}
    for p in after.roster(team):
        old = before.by_who.get(old_key(p.who))
        if old_key(p.who) not in was:
            out['joined'][p.who] = ('new to the game' if old is None else
                                    ', '.join(before.team_name(t) for t in club(old.teams)) or 'free agent')
        elif old is not None:
            a, b = old.values(), p.values()
            diff = [k for k in b if a[k] != b[k]]
            if old.ratings != p.ratings and 'ovr' not in diff:
                diff.append('ratings')
            if diff:
                out['changed'][p.who] = diff
    for p in before.roster(team):
        if p.who not in now:
            out['left'].append(p)
    return out
