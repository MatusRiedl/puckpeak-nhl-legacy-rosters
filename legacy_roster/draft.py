"""Real draft data for every player: year, round, overall pick and team, from NHL.com's draft lists
(the data pack's 'drafts', every pick since 2005; tools/providers/nhl_facts.py).

The game keeps a player's draft in cPbu: `draftyear` (year - 1900; 255 undrafted), `draftround`,
`draftposition` (the overall pick: Gaudreau round 4, pick 104 on the disc) and `draftteam` (NHL slot
+ 1, five bits like `proteam`, so Vegas in slot 31 cannot be written). A junior who is not drafted yet
has his draft year and round 0, as EA wrote them; Be a GM's draft takes its classes from there.

Before, nothing wrote these fields: a player kept whatever his record had (another person's, when the
record was reused), and new players were all undrafted (testers, 0.7.0: Will Smith, Stenberg).

apply() runs on the whole roster, before the update and again at its end (players it created or
renamed), and gives the same answer on its own output: a second run stays byte-identical.
"""
from . import layout as L
from .donors import UNDRAFTED, real_birth_year
from .matching import norm, same_first_name

FIELDS = ('WzKY', 'Ujcc', 'WfTt', 'uWgv')       # draftyear, draftround, draftposition, draftteam
TEAM_ALIAS = {'ATL': 'WPG', 'PHX': 'UTA', 'ARI': 'UTA'}     # teams that moved: their slot today
DRAFT_AGE = (17, 21)            # draft year - birth year of every pick (18 most, 19-20 for re-entries)


class Drafts:
    def __init__(self, picks, season_year, stale=True):
        self.season_year = season_year
        self.stale = stale              # records in EA's year - 1900 may be there (donors.real_birth_year)
        self.by_last = {}
        for first, last, pos, year, rnd, overall, team in picks or []:
            self.by_last.setdefault(norm(last), []).append((norm(first), pos, year, rnd, overall, team))
        self.first_year = min((p[3] for p in picks), default=None) if picks else None

    def __bool__(self):
        return bool(self.by_last)

    def pick(self, first, last, birth_years, position):
        """The one pick that fits a player (name, goalie or skater, age), or None. `position` is
        the record's (0-2 forwards, 3 defence, 4 goalie)."""
        fn = norm(first)
        goalie = position == 4
        age = lambda c: min(abs(c[2] - y - 18) for y in birth_years)
        found = [c for c in self.by_last.get(norm(last), ())
                 if (c[1] == 'G') == goalie and same_first_name(c[0], fn)
                 and any(DRAFT_AGE[0] <= c[2] - y <= DRAFT_AGE[1] for y in birth_years)]
        # namesakes (two Sebastian Ahos): the same first name, forward or defence, then the usual draft age
        for keep in (lambda c: c[0] == fn, lambda c: (c[1] == 'D') == (position == 3),
                     lambda c: age(c) == min(map(age, found))):
            if len(found) > 1:
                found = [c for c in found if keep(c)] or found
        return found[0] if len(found) == 1 else None

    def wanted(self, P, prow):
        """The draft fields a record should have (a tuple of FIELDS' values), or None to leave it."""
        first, last = P.get(prow, 'PedH'), P.get(prow, 'RMbQ')
        if not last or 'ZZ' in last:
            return None
        shown = P.get(prow, 'dnFq') + 1910
        pos = P.get(prow, 'aljv')
        # his own birth year first; then ten years earlier (a record still in EA's year - 1900)
        found = self.pick(first, last, {shown}, pos) or (self.pick(first, last, {shown - 10}, pos) if self.stale else None)
        if found is not None:
            _, _, year, rnd, overall, team = found
            slot = L.API_TO_SLOT.get(TEAM_ALIAS.get(team, team))
            code = slot + 1 if slot is not None and slot + 1 <= P.field('uWgv').mask else 0
            return (year - 1900, min(rnd, P.field('Ujcc').mask), min(overall, P.field('WfTt').mask), code)
        born = real_birth_year(P, prow, self.stale)
        month, day = P.get(prow, 'pLKJ') + 1, P.get(prow, 'iwsK') + 1
        eligible = born + 18 + (1 if (month, day) > (9, 15) else 0)     # 18 by September 15 of the draft year
        if eligible > self.season_year:     # this season's draft is over: a junior waits for his
            return (eligible - 1900, 0, 0, 0)
        year = P.get(prow, 'WzKY')
        if P.get(prow, 'Ujcc') and year != UNDRAFTED and year + 1900 >= self.first_year:
            return (UNDRAFTED, 0, 0, 0)     # a pick the real drafts do not have (another person's)
        return None


def apply(R, picks, season_year, rows=None):
    """Write the real draft data into the records `rows` (default: all). `picks`: a Drafts, or the
    data pack's list. Returns how many changed."""
    drafts = picks if isinstance(picks, Drafts) else Drafts(picks, season_year)
    if not drafts:
        return 0
    P = R.P
    changed = 0
    for prow in (range(P.cur_rec) if rows is None else sorted(rows)):
        want = drafts.wanted(P, prow)
        if want is None:
            continue
        have = tuple(P.get(prow, f) for f in FIELDS)
        if have != want:
            for f, v in zip(FIELDS, want):
                P.set(prow, f, v)
            changed += 1
    return changed
