"""Contracts as the Front office shows them (no window code). An NHL organisation (`org`): its NHL roster, everyone on
its farm club, its prospects (its rights on any other team or on the free-agent list), each player's deal
(contracts.deal_of) and, for five seasons, what the NHL roster's deals commit against that season's cap. Any other team
(`club`): its own roster with each player's deal and rights, and what the deals pay for five seasons (no cap outside the
NHL). Every club holds contracts (owner, 2026-10-22: contracts.contract_clubs, contract_home).

Amounts are real dollars on either money scale (contracts.real: a roster for the unpatched game holds them times
contracts.GAME). Cap and lowest payroll are each season's real ones (gamepatch.CAP_TABLE): the game patch puts them into
the game; the unpatched game shows its own $71.4M cap with the deals scaled to it. The cap counts the NHL roster, as the
game's payroll does. On a roster for the unpatched game Vegas holds no rights (proteam has five bits, room up to slot
30: gamepatch.RIGHTS), so its prospect group is empty and its farm club's two-way deals count as Vegas's; patch rosters
give proteam six bits (gamepatch.rights_wide) and Vegas holds rights as every team.
"""
from . import contracts, gamepatch
from . import layout as L
from .edits import birth_of, who_of

SEASONS = 5                                             # 2026-27 .. 2030-31
GROUPS = ('nhl', 'farm', 'prospects')


def season_label(k):
    """'2026-27' for season number `k` (0 = 2026-27)."""
    year = gamepatch.FIRST_SEASON + k
    return f"{year}-{(year + 1) % 100:02d}"


class Index:
    """Who is where in a roster, read once: players by team, everyone's teams, the free-agent list, the rights each NHL
    team holds (players on a team or on the free-agent list only: records on neither are spare ones), the farm clubs."""

    def __init__(self, R, base=1910):
        self.R, self.base = R, base
        P, U = R.P, R.U
        self.on_team, self.teams = {}, {}
        for i in range(U.cur_rec):
            prow = R.p_by_id.get(R.link_to_pid.get(U.get(i, 'TWSX')))
            if prow is not None:
                team = U.get(i, 'BSXd')
                self.on_team.setdefault(team, []).append(prow)
                self.teams.setdefault(prow, []).append(team)
        self.free = set()
        for i in range(R.Q.cur_rec):
            prow = R.p_by_id.get(R.link_to_pid.get(R.Q.get(i, 'TWSX')))
            if prow is not None:
                self.free.add(prow)
        self.rights = {}
        for prow in sorted(set(self.teams) | self.free):
            holder = P.get(prow, gamepatch.RIGHTS)
            if holder:
                self.rights.setdefault(holder - 1, []).append(prow)
        T = R.T
        self.farm = {n: T.get(n, gamepatch.AFFILIATE) - 1 for n in sorted(L.NHL_PRIMARY) if T.get(n, gamepatch.AFFILIATE)}
        self.farm.update({parent: farm for farm, parent in L.AHL_PARENT_EXTRA.items()})
        self.parent = {farm: n for n, farm in self.farm.items()}
        self.rights_room = P.field(gamepatch.RIGHTS).mask - 1      # the highest slot whose rights a record can hold
        self.clubs = contracts.contract_clubs(R)
        self._who = None

    def org_of(self, team):
        """The NHL slot of the organisation team `team` belongs to (itself, or its farm club's parent), else None."""
        if team in L.NHL_PRIMARY:
            return team
        return self.parent.get(team) if team in L.AHL else None

    def player(self, prow, where, scale, deal=None):
        P = self.R.P
        return {'prow': prow, 'pid': P.get(prow, 'zIBw'), 'who': who_of(P, prow, self.base), 'name': self.R.name(prow),
                'pos': L.POS_NAME.get(P.get(prow, 'aljv'), '?'), 'birth': birth_of(P, prow, self.base),
                'deal': deal or contracts.deal_of(P, prow, scale), 'where': where}

    def by_who(self, who):
        """The player row of person key `who` (players on a team or on the free-agent list), else None."""
        if self._who is None:
            P = self.R.P
            self._who = {}
            for prow in sorted(set(self.teams) | self.free):
                self._who.setdefault(who_of(P, prow, self.base), prow)
        return self._who.get(who)

    def home(self, prow, teams=None):
        """contracts.contract_home of a player: (NHL slot, True), (his club, False) or None. `teams`: the slots he would
        be on (a free agent signed with a team), else the ones he is on. A two-way deal on the farm club of an NHL team
        whose rights a record cannot hold (Vegas: gamepatch.RIGHTS) is that team's (the Front office's view; verify and
        the edits allow the club's free amounts there, and the NHL amounts the window asks for fit them too)."""
        teams = set(self.teams.get(prow, [])) if teams is None else set(teams)
        home = contracts.contract_home(self.R.P, prow, teams, self.clubs)
        if home is not None and not home[1]:            # Vegas's two-way deals on Henderson: its rights do not fit
            parent = self.parent.get(home[0])
            if parent is not None and parent > self.rights_room and self.R.P.get(prow, 'DVoL'):
                return parent, True
        return home

    def club_of(self, prow):
        """The slot of the club a player is on (not a national team or a copy of an NHL team), None for nobody's."""
        clubs = [t for t in self.teams.get(prow, []) if t not in L.NATIONAL and t not in L.MIRROR_OF]
        return min(clubs) if clubs else None


def org(index, team, scale, override=None):
    """The organisation of NHL slot `team` in `index`: {'org', 'farm' (its farm club's slot or None), 'nhl', 'farm_rows'
    (everyone on the farm club: also players with another team's rights or with none, on a deal with the club),
    'prospects' (lists of players: {'prow', 'pid', 'who', 'name', 'pos', 'birth', 'deal', 'where': slot or None}),
    'seasons', 'no_rights' (the roster cannot hold this team's rights)}. `override` ({person key: deal}) stands in for
    the deals of those players (contracts set but not saved yet)."""
    override = override or {}

    def person(prow, where):
        p = index.player(prow, where, scale)
        if p['who'] in override:
            p['deal'] = dict(override[p['who']])
        return p
    nhl = [person(prow, team) for prow in index.on_team.get(team, [])]
    taken = {p['prow'] for p in nhl}
    farm = index.farm.get(team)
    farm_rows = [person(prow, farm) for prow in index.on_team.get(farm, []) if prow not in taken] if farm is not None else []
    taken |= {p['prow'] for p in farm_rows}
    prospects = [person(prow, index.club_of(prow)) for prow in index.rights.get(team, []) if prow not in taken]
    return {'org': team, 'farm': farm, 'nhl': nhl, 'farm_rows': farm_rows, 'prospects': prospects,
            'seasons': seasons(nhl), 'no_rights': team > index.rights_room}


def club(index, team, scale, override=None):
    """Team `team`'s own roster in `index`: {'team', 'rows' (players as in `org`, each also with 'rights': the NHL slot
    holding his rights or None, 'home': contracts.contract_home), 'seasons' ([{'season', 'label', 'committed',
    'signed'}]: what the club's own deals pay, not an NHL organisation's; no cap outside the NHL)}. `override` as in
    `org`."""
    override = override or {}
    P = index.R.P
    rows = []
    for prow in index.on_team.get(team, []):
        p = index.player(prow, index.club_of(prow), scale)
        if p['who'] in override:
            p['deal'] = dict(override[p['who']])
        rights = P.get(prow, gamepatch.RIGHTS)
        p['rights'], p['home'] = (rights - 1 if rights else None), index.home(prow)
        rows.append(p)
    paid, own = [], [p for p in rows if p['home'] == (team, False)]
    for k in range(SEASONS):
        hits = [contracts.cap_in(p['deal'], k) for p in own]
        paid.append({'season': k, 'label': season_label(k), 'committed': sum(hits), 'signed': sum(1 for h in hits if h)})
    return {'team': team, 'rows': rows, 'seasons': paid}


def seasons(nhl, swap=None):
    """[{'season', 'label', 'committed', 'cap', 'floor', 'space', 'signed'}] for SEASONS seasons: what the deals of the
    NHL roster `nhl` commit against each season's cap (real dollars). `swap` (person key, deal): that player's deal
    replaced (a preview)."""
    out = []
    for k in range(SEASONS):
        hits = [contracts.cap_in(swap[1] if swap and p['who'] == swap[0] else p['deal'], k) for p in nhl]
        committed, cap = sum(hits), gamepatch.cap_of(1, k)
        out.append({'season': k, 'label': season_label(k), 'committed': committed, 'cap': cap,
                    'floor': gamepatch.cap_of(0, k), 'space': cap - committed, 'signed': sum(1 for h in hits if h)})
    return out


def club_payrolls(index, scale, override=None):
    """{club slot: this season's real dollars of the deals players hold with it (not an NHL organisation's deals)}
    (`override` as in `org`)."""
    override = override or {}
    out = {}
    for prow in sorted(index.teams):
        home = index.home(prow)
        if home is None or home[1]:
            continue
        who = who_of(index.R.P, prow, index.base) if override else None
        out[home[0]] = out.get(home[0], 0) + contracts.cap_in(override.get(who) or
                                                              contracts.deal_of(index.R.P, prow, scale), 0)
    return out


def cap_space(index, scale, override=None):
    """{NHL slot: this season's cap space} of all 32 organisations (real dollars, `override` as in `org`)."""
    override = override or {}
    out = {}
    for team in sorted(L.NHL_PRIMARY):
        payroll = 0
        for prow in index.on_team.get(team, []):
            who = who_of(index.R.P, prow, index.base) if override else None
            payroll += contracts.cap_in(override.get(who) or contracts.deal_of(index.R.P, prow, scale), 0)
        out[team] = gamepatch.cap_of(1, 0) - payroll
    return out
