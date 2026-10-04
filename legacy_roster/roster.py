"""Named access to the tables of a roster save that the updater works on."""
from .tdb import RosterFile

TEAMS = 'ttOk'        # exhibitionteams
PLAYERS = 'cPbu'      # exhibitionplayerbiotable
ROSTER = 'ulGe'       # exhibitionrostertable: one entry per player per team
LINK = 'caBZ'         # exhibitionplayers: link id (index) -> player id
FREE_AGENTS = 'QEoV'  # exhibitionfreeagents: link ids of unattached players
SKATERS = 'yvSd'      # exhibitionskaterai
GOALIES = 'yuHm'      # exhibitiongoalieai


class Roster:
    def __init__(self, source):
        """`source` is a path to SYS-DATA, its bytes, or an already parsed RosterFile."""
        if isinstance(source, RosterFile):
            self.f = source
        elif isinstance(source, (bytes, bytearray)):
            self.f = RosterFile(data=source)
        else:
            self.f = RosterFile(source)
        self.T, self.P, self.U, self.C = (self.f[n] for n in (TEAMS, PLAYERS, ROSTER, LINK))
        self.Q = self.f[FREE_AGENTS]
        self.reindex()

    def reindex(self):
        P, C, U = self.P, self.C, self.U
        self.p_by_id = {P.get(i, 'zIBw'): i for i in range(P.cur_rec)}
        self.link_to_pid = {C.get(i, 'qEfv'): C.get(i, 'qFky') for i in range(C.cur_rec)}
        self.pid_to_links = {}
        for k, v in self.link_to_pid.items():
            self.pid_to_links.setdefault(v, []).append(k)
        self.entries_by_pid = {}
        for i in range(U.cur_rec):
            pid = self.link_to_pid.get(U.get(i, 'TWSX'))
            self.entries_by_pid.setdefault(pid, []).append(i)

    def team_name(self, t):
        return self.T.get(t, 'JkmY').replace('®', '').replace('™', '') if t < self.T.cur_rec else f'#{t}'

    def name(self, prow):
        return f"{self.P.get(prow, 'PedH')} {self.P.get(prow, 'RMbQ')}"

    def team_roster(self, team):
        """[(entry index, player row, name, jersey, playerstyle)] of a team."""
        out = []
        for i in range(self.U.cur_rec):
            if self.U.get(i, 'BSXd') == team:
                pid = self.link_to_pid.get(self.U.get(i, 'TWSX'))
                prow = self.p_by_id.get(pid)
                out.append((i, prow, self.name(prow) if prow is not None else '?', self.U.get(i, 'tRVs'), self.U.get(i, 'sFgQ')))
        return out

    def find_player(self, first, last):
        P = self.P
        return [i for i in range(P.cur_rec) if P.get(i, 'RMbQ').lower() == last.lower() and P.get(i, 'PedH').lower() == first.lower()]

    def teams_of(self, prow):
        """[(entry index, team id)] for a player row."""
        pid = self.P.get(prow, 'zIBw')
        return [(e, self.U.get(e, 'BSXd')) for e in self.entries_by_pid.get(pid, [])]
