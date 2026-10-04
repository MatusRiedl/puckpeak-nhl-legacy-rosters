"""Ratings for players nobody publishes ratings for (club players outside the NHL).

A player's level is set relative to the NHL players of the roster being built:

    level = NHL median for his position + league gap + age + role + a little spread

The league gaps and the age curve were measured on EA's own final roster for the game, which
rated every league it shipped. The shape of the attributes (a centre takes face-offs, a
defenceman blocks shots) is the median shape of NHL players at the same position.
"""
import zlib

from . import layout as L
from . import ratings
from .schema import RATING_BASE

# median level of a league's dressed players minus the NHL's, for forwards / defencemen / goalies
LEAGUE_GAP = {
    'ahl':       {'F': -6.1, 'D': -5.6, 'G': -6.9},
    'shl':       {'F': -7.4, 'D': -7.1, 'G': -8.0},
    'liiga':     {'F': -8.8, 'D': -7.7, 'G': -9.3},
    'del':       {'F': -7.9, 'D': -9.4, 'G': -8.9},
    'extraliga': {'F': -5.9, 'D': -6.0, 'G': -10.7},
    'nl':        {'F': -4.8, 'D': -5.8, 'G': -6.6},
    'norway':    {'F': -9.8, 'D': -8.4, 'G': -9.2},
    'chl':       {'F': -13.5, 'D': -13.0, 'G': -15.7},
}
# level by age relative to a 24-27 year old in the same league (older players still in a top
# league are the ones who were good enough to stay)
AGE_CURVE = ((19, -4.0), (21, -2.5), (23, -1.4), (27, 0.0), (31, 1.0), (34, 1.6), (99, 2.2))
POTENTIAL_BONUS = ((20, 9), (22, 6), (24, 3), (99, 1))
# junior leagues: the gap was measured on teenagers, so age counts relative to a typical junior
YOUTH_AGE = {'chl': 18}


def _spread(name, salt, low, high):
    """A fixed pseudo-random whole number in [low, high] for this player."""
    return low + zlib.crc32(f"{salt}:{name}".encode()) % (high - low + 1)


def age_adjust(age):
    return next(adj for limit, adj in AGE_CURVE if age <= limit)


class Estimator:
    def __init__(self, b):
        self.b = b
        R, U, P = b.R, b.U, b.P
        # median level and median attribute shape of dressed NHL players, by position group
        samples = {'C': [], 'W': [], 'D': [], 'G': []}
        for e in range(U.cur_rec):
            if e in b.deleted or U.get(e, 'BSXd') not in L.NHL_PRIMARY or not U.get(e, 'jZSh'):
                continue
            pid = b.pid_of_entry(e)
            pos = P.get(R.p_by_id[pid], 'aljv')
            tname = 'yuHm' if pos == 4 else 'yvSd'
            row = b.ai_row[tname].get(pid)
            if row is not None:
                t = R.f[tname]
                samples[L.POS_CLASS[pos]].append([t.get(row, f) for f in ratings.attribute_fields(t)])
        self.shape, self.nhl_level = {}, {}
        for group, rows in samples.items():
            t = R.f['yuHm' if group == 'G' else 'yvSd']
            fields = ratings.attribute_fields(t)
            if not rows:
                rows = [[40] * len(fields)]
            shape = {f: sorted(r[k] for r in rows)[len(rows) // 2] for k, f in enumerate(fields)}
            self.shape[group] = shape
            self.nhl_level[group] = sum(shape.values()) / len(shape) + RATING_BASE

    def target(self, league, pos, age, name, letter=None, rookie=False, import_player=False):
        """The level a player of this league, position and age should have."""
        group = L.POS_CLASS[pos]
        gap = LEAGUE_GAP[league]['G' if group == 'G' else 'D' if group == 'D' else 'F']
        level = self.nhl_level[group] + gap + age_adjust(age)
        if league in YOUTH_AGE:
            level -= age_adjust(YOUTH_AGE[league])
        level += {'C': 2.0, 'A': 1.0}.get(letter, 0.0)
        level += 1.5 if import_player else 0.0     # clubs bring players in from abroad to be better
        level -= 1.0 if rookie else 0.0
        level += (_spread(name, 'a', -2, 2) + _spread(name, 'b', -2, 2)) / 2    # -2..+2, mostly near 0
        return level

    def write(self, prow, level, name, age):
        """Give a player the NHL shape of his position, moved to `level`, with small quirks."""
        b = self.b
        pid = b.P.get(prow, 'zIBw')
        pos = b.P.get(prow, 'aljv')
        tname = 'yuHm' if pos == 4 else 'yvSd'
        row = b.ai_row[tname].get(pid)
        if row is None:
            return
        t = b.R.f[tname]
        group = L.POS_CLASS[pos]
        shape = self.shape[group]
        delta = round(level - self.nhl_level[group])
        for f, v in shape.items():
            t.set(row, f, ratings.clamp(v + delta + _spread(name, f, -2, 2)))
        stored = round(level) - RATING_BASE
        bonus = next(b_ for limit, b_ in POTENTIAL_BONUS if age <= limit)
        t.set(row, 'koEt', ratings.clamp(stored + bonus))          # c_potential
        b.quality[pid] = ratings.level(t, row) + b.ovr_offset[pos == 4]

    def shift(self, prow, level):
        """Move an existing player to `level` keeping the shape of his attributes."""
        b = self.b
        pid = b.P.get(prow, 'zIBw')
        pos = b.P.get(prow, 'aljv')
        tname = 'yuHm' if pos == 4 else 'yvSd'
        row = b.ai_row[tname].get(pid)
        if row is None:
            return
        t = b.R.f[tname]
        fields = ratings.attribute_fields(t)
        for _ in range(6):
            delta = round(level - ratings.level(t, row, fields))
            if not delta:
                break
            for f in fields:
                t.set(row, f, ratings.clamp(t.get(row, f) + delta))
        b.quality[pid] = ratings.level(t, row) + b.ovr_offset[pos == 4]
