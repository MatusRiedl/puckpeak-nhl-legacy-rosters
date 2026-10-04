"""Turn a source roster into an updated one.

`Builder` owns the working copy of the save and the bookkeeping every step shares: roster
entries and links, the free-agent list, line slots, contracts and the change log. It also holds
the NHL and national-team steps; club leagues are in leagues/. pipeline.build() runs the steps.
"""
import zlib
from collections import Counter

from . import layout as L
from . import lines
from . import ratings
from .donors import Donors
from .matching import match, norm, same_first_name


class Data:
    """Everything the builder needs from outside the save."""

    def __init__(self, nhl_players=None, ea_ratings=None, iihf=None, season_year=2026, leagues=None, nhl_logos=None):
        self.nhl_players = nhl_players or []   # flat list, see datasource.flatten_nhl()
        self.ea_ratings = ea_ratings           # [{'name','team','position','birth','ovr','attrs'}] or None
        self.iihf = iihf                       # {'AUT': [player, ...]} or None
        self.season_year = season_year         # the year the season starts in
        self.leagues = leagues or {}           # club leagues: {'liiga': {'teams': [{'slot', 'players', ...}]}}
        self.nhl_logos = nhl_logos or {}       # NHL.com team code -> logo link (photos and logos)


def source_rank(team):
    """Which non-NHL entry to promote: AHL first, then prospect pools, draft classes, juniors."""
    if team in L.AHL:
        return 0
    if team in L.SYSTEM_POOL_SLOTS:
        return 1
    if 62 <= team <= 100:
        return 2
    return 3


class Builder:
    def __init__(self, R, data, progress=None):
        self.R = R
        self.data = data
        self.progress = progress or (lambda msg: None)
        self.U, self.P, self.C, self.Q = R.U, R.P, R.C, R.Q
        U = self.U
        self.flags = [n for n, f in U.fields.items() if f.bits == 1 and n != 'jZSh']
        self.log = []
        self.deleted = set()
        self.left_keys = set()  # people who left the NHL and are no longer active
        self.created = set()    # repurposed records (their old contract data is junk)
        self.arrivals = {}      # team -> [entry]
        self.departures = {}    # team -> [(pos_class, frozenset(flags), quality)]
        used = {self.C.get(i, 'qEfv') for i in range(self.C.cur_rec)}
        self.next_link = max(v for v in used if v < 16000) + 1
        self.fa_links = [self.Q.get(i, 'TWSX') for i in range(self.Q.cur_rec)]
        self.ovr = {}           # pid -> EA overall (filled by apply_ea_ratings)
        self.api = []
        self.api_rows = set()
        self.api_country = {}
        self.attached = set()   # pids given a new roster entry in this run
        self.league_stats = {}  # club league -> what its step did
        self.filled_now = set() # national teams filled from scratch in this run
        self.placed = set()     # pids a club league has placed in this run (the first league to list him keeps him)
        self.core_reserve = Counter()   # records kept back for the line-ups of leagues still to come ('G', 'S')
        self.ea_rated = set()   # pids whose attributes EA's ratings set in this run (never estimated over)
        self.pool_released = 0  # prospect-pool players who found no room and became free agents
        self.photos = {}        # player row -> photo link, for the players placed in this run
        self.logos = {}         # team slot -> logo link
        # rating rows never move: player id -> row in the skater / goalie attribute table
        self.ai_row = {tn: {R.f[tn].get(i, 'zIBw'): i for i in range(R.f[tn].cur_rec)} for tn in ('yvSd', 'yuHm')}
        # EA overalls run slightly above (skaters) or below (goalies) the plain attribute mean
        self.ovr_offset = ratings.overall_offset(data.ea_ratings) if data.ea_ratings else {False: 0.0, True: 0.0}
        self._ratings()
        # the most common playing style of defencemen and of forwards (for a skater who changes between them)
        styles = {'D': Counter(), 'F': Counter()}
        S = R.f['yvSd']
        for i in range(S.cur_rec):
            prow = R.p_by_id.get(S.get(i, 'zIBw'))
            if prow is not None and self.P.get(prow, 'aljv') < 4:
                styles['D' if self.P.get(prow, 'aljv') == 3 else 'F'][S.get(i, 'sFgQ')] += 1
        self.usual_style = {k: (c.most_common(1)[0][0] if c else (4 if k == 'D' else 9)) for k, c in styles.items()}
        # the source already has the national teams the base left empty: it was made by this tool,
        # so a second run only maintains what is there instead of rebuilding it
        self.maintain = all(any(U.get(i, 'BSXd') == t for i in range(U.cur_rec)) for t in L.EMPTY_NATIONAL.values())
        self.depth = {goalie: self._depth_level(goalie) for goalie in (False, True)}
        self.records_of = {}    # identity -> records (one person can have two: national-team goalies)
        for r in range(self.P.cur_rec):
            self.records_of.setdefault(self.identity(r), []).append(r)
        self.donors = Donors(self)
        self.orig_club = self.club_teams()
        # each team's original line structure: (class, slot set) of its dressed players, best first
        self.orig_slot_sets = {}
        for i in range(U.cur_rec):
            if self.held(i):
                self.orig_slot_sets.setdefault(U.get(i, 'BSXd'), []).append((self.cls(i), self.held(i), self.q(i)))
        for sets in self.orig_slot_sets.values():
            sets.sort(key=lambda s: (-len(s[1]), -s[2]))
        # contracts that already point at a team the player is not on (left alone, as in the original)
        on = {}
        for i in range(U.cur_rec):
            on.setdefault(self.pid_of_entry(i), set()).add(U.get(i, 'BSXd'))
        self.orig_contract_bad = {
            pid for pid, prow in R.p_by_id.items()
            if self.P.get(prow, 'BSXd') and not self.same_team(self.P.get(prow, 'BSXd') - 1) & on.get(pid, set())}

    # --- helpers ----------------------------------------------------------
    def club_teams(self):
        """pid -> set of club teams (NHL, AHL) the player has a roster entry on."""
        U, out = self.U, {}
        for i in range(U.cur_rec):
            t = U.get(i, 'BSXd')
            if i not in self.deleted and t in L.CLUB:
                out.setdefault(self.pid_of_entry(i), set()).add(t)
        return out

    def active_fields(self, tname):
        """The attribute fields that make up a player's level."""
        return ratings.attribute_fields(self.R.f[tname])

    def _ratings(self):
        """Quality on the overall-rating scale: EA overall when known, otherwise the mean of the
        player's attributes shifted onto that scale."""
        self.quality = {}
        for tname in ('yvSd', 'yuHm'):
            t = self.R.f[tname]
            act = self.active_fields(tname)
            k = self.ovr_offset[tname == 'yuHm']
            for i in range(t.cur_rec):
                self.quality[t.get(i, 'zIBw')] = sum(t.get(i, n) for n in act) / len(act) + 36 + k
        self.quality.update(self.ovr)

    def player_style(self, pid):
        """A roster entry carries the same playerstyle as the player's attribute record."""
        for tname in ('yvSd', 'yuHm'):
            row = self.ai_row[tname].get(pid)
            if row is not None:
                return self.R.f[tname].get(row, 'sFgQ')
        return 1

    def pid_of_entry(self, e):
        return self.R.link_to_pid.get(self.U.get(e, 'TWSX'))

    def prow_of_entry(self, e):
        return self.R.p_by_id.get(self.pid_of_entry(e))

    def q(self, e):
        return self.quality.get(self.pid_of_entry(e), 0)

    def cls(self, e):
        return L.POS_CLASS[self.P.get(self.prow_of_entry(e), 'aljv')]

    def held(self, e):
        return frozenset(f for f in self.flags if self.U.get(e, f))

    def entries_on(self, team):
        U = self.U
        return [i for i in range(U.cur_rec) if i not in self.deleted and U.get(i, 'BSXd') == team]

    def person(self, prow):
        """Identity across duplicate records (national-team goalies have their own records)."""
        return (norm(self.P.get(prow, 'PedH')), norm(self.P.get(prow, 'RMbQ')))

    def identity(self, prow):
        """Name and birthdate: two records with the same identity are one real person."""
        P = self.P
        return self.person(prow) + (P.get(prow, 'dnFq'), P.get(prow, 'pLKJ'), P.get(prow, 'iwsK'))

    def depart(self, e):
        """Record the line slots entry `e` leaves behind on its current team."""
        team = self.U.get(e, 'BSXd')
        self.departures.setdefault(team, []).append((self.cls(e), self.held(e), self.q(e), self.U.get(e, 'lcCm')))

    def clear_lines(self, e):
        for f in self.flags + ['jZSh']:
            self.U.set(e, f, 0)
        self.U.set(e, 'lcCm', 0)

    def move_entry(self, e, team):
        self.depart(e)
        self.clear_lines(e)
        self.U.set(e, 'BSXd', team)
        self.arrivals.setdefault(team, []).append(e)

    def new_entry(self, team, link, prow):
        U = self.U
        e = U.add_record()
        for f in U.fields:
            U.set(e, f, 0)
        U.set(e, 'BSXd', team)
        U.set(e, 'TWSX', link)
        U.set(e, 'XWot', L.XWOT_UNSET)  # real id assigned by renumber_entries()
        U.set(e, 'tRVs', self.P.get(prow, 'tRVs'))
        pid = self.P.get(prow, 'zIBw')
        U.set(e, 'sFgQ', self.player_style(pid))
        self.attached.add(pid)
        return e

    def new_link(self, pid):
        link = self.next_link
        self.next_link += 1
        self.C.add_record({'BERR': 0, 'qEfv': link, 'qFky': pid})
        self.R.link_to_pid[link] = pid
        return link

    def drop_fa(self, pid):
        self.fa_links = [l for l in self.fa_links if self.R.link_to_pid.get(l) != pid]

    def live_entries(self):
        """pid -> the roster entries he has right now (deleted ones left out)."""
        U, live = self.U, {}
        for e in range(U.cur_rec):
            if e not in self.deleted:
                live.setdefault(self.pid_of_entry(e), []).append(e)
        return live

    def release(self, e, live):
        """Take entry `e` off its team. A player left on no club team (a national team does not
        count) goes onto the free-agent list: he stays in the game and can be signed, and his
        record is never reused for someone else. `live` (see live_entries) is kept up to date.
        Returns True when he became a free agent."""
        pid = self.pid_of_entry(e)
        self.depart(e)
        self.deleted.add(e)
        rest = [x for x in live.get(pid, []) if x != e]
        live[pid] = rest
        if any(self.U.get(x, 'BSXd') not in L.NATIONAL for x in rest):
            return False
        if len(self.records_of.get(self.identity(self.R.p_by_id[pid]), ())) > 1:
            return False        # a second record of someone the game has elsewhere (national-team goalies)
        if not any(self.R.link_to_pid.get(l) == pid for l in self.fa_links):
            self.fa_links.append(self.U.get(e, 'TWSX'))
        return True

    # --- creating players that are not in the file -------------------------
    def _depth_level(self, goalie):
        """Quality of a typical depth NHL player (30th percentile of the source's NHL rosters)."""
        R, U = self.R, self.U
        vals = sorted(self.quality[pid] for pid in
                      {R.link_to_pid[U.get(i, 'TWSX')] for i in range(U.cur_rec) if U.get(i, 'BSXd') in L.NHL_PRIMARY}
                      if pid in self.quality and (self.P.get(R.p_by_id[pid], 'aljv') == 4) == goalie)
        return vals[int(len(vals) * 0.3)] if vals else 70

    def set_text(self, prow, field, text):
        """Write a name, shortened to what the field can hold (the limit is in UTF-8 bytes)."""
        limit = self.P.field(field).bits // 8 - 1
        while len(text.encode('utf-8')) > limit:
            text = text[:-1]
        self.P.set(prow, field, text)

    def take_record(self, pos, who, target=None, required=True):
        """A player record for someone who is not in the save yet (see donors.py). When none is
        left: an error, or None if the caller can do without (`required=False`)."""
        prow = self.donors.take(pos, target)
        if prow is None:
            if not required:
                return None
            raise RuntimeError(f"no spare player record left for {who}")
        self.created.add(prow)
        return prow

    def create_player(self, p):
        P = self.P
        pos = L.POS_CODE[p['pos']]
        name = f"{p['first']} {p['last']}"
        prow = self.take_record(pos, name, target=self.depth[pos == 4])
        old = self.R.name(prow)
        y, m, d = p['birth']
        self.donors.reset_identity(prow, name, L.NAT_CODE.get(p.get('country')), y)
        self.set_text(prow, 'PedH', p['first'])
        self.set_text(prow, 'RMbQ', p['last'])
        if p.get('city'):
            self.set_text(prow, 'JzFM', p['city'])
        P.set(prow, 'iwsK', d - 1)
        P.set(prow, 'pLKJ', m - 1)
        P.set(prow, 'dnFq', y - 1910)
        if p.get('height_in'):
            P.set(prow, 'QBpy', max(0, min(31, p['height_in'] - 54)))
        if p.get('weight_lb'):
            P.set(prow, 'WZNs', max(0, min(255, p['weight_lb'] - 120)))
        if p.get('shoots') in ('L', 'R'):
            P.set(prow, 'pkRG', 0 if p['shoots'] == 'L' else 1)
        if p.get('num'):
            P.set(prow, 'tRVs', p['num'])
        self.log.append([p['team'], 'created', name, f"reused record of {old}", p['num']])
        return prow

    # --- NHL ------------------------------------------------------------------
    def nhl_rosters(self):
        """Put every player of the official rosters on his team (steps 1-3 of the original)."""
        R, U = self.R, self.U
        api = match(R, [dict(p) for p in self.data.nhl_players])
        self.api = api
        self.api_rows = {p['row'] for p in api if p['row'] is not None}
        self.api_country = {p['row']: p.get('country') for p in api if p['row'] is not None}
        api_pids = {self.P.get(p['row'], 'zIBw') for p in api if p['row'] is not None}
        target_entry = {}

        # 1. players leaving the NHL: remove their NHL entries, free agent unless still on another pro team
        for e in range(U.cur_rec):
            t = U.get(e, 'BSXd')
            if t in L.NHL_PRIMARY and self.pid_of_entry(e) not in api_pids:
                pid = self.pid_of_entry(e)
                self.depart(e)
                self.deleted.add(e)
                other = [x for x in R.entries_by_pid.get(pid, []) if x != e
                         and U.get(x, 'BSXd') not in L.NHL_ALL and U.get(x, 'BSXd') not in L.NATIONAL]
                status = 'free agent'
                if other:
                    status = 'stays with ' + R.team_name(U.get(other[0], 'BSXd'))
                elif U.get(e, 'TWSX') not in self.fa_links:
                    self.fa_links.append(U.get(e, 'TWSX'))
                self.log.append([L.SLOT_TO_API[t], 'left NHL roster', R.name(R.p_by_id[pid]), status, U.get(e, 'tRVs')])
                self.left_keys.add(self.person(R.p_by_id[pid]))

        # 2. every player onto his team
        self.logos.update({L.API_TO_SLOT[a]: url for a, url in self.data.nhl_logos.items() if a in L.API_TO_SLOT})
        for p in api:
            target = L.API_TO_SLOT[p['team']]
            if p['row'] is None:
                prow = self.create_player(p)
                p['row'] = prow
                self.api_rows.add(prow)
                self.api_country[prow] = p.get('country')
                pid = self.P.get(prow, 'zIBw')
                e = self.new_entry(target, self.new_link(pid), prow)
                self.arrivals.setdefault(target, []).append(e)
                target_entry[e] = p
                self.set_pro_team(prow, target)
                continue
            self.set_pro_team(p['row'], target)
            pid = self.P.get(p['row'], 'zIBw')
            ents = [x for x in R.entries_by_pid.get(pid, []) if x not in self.deleted]
            here = [x for x in ents if U.get(x, 'BSXd') == target]
            nhl = [x for x in ents if U.get(x, 'BSXd') in L.NHL_PRIMARY]
            if here:
                e = here[0]
            elif nhl:
                e = nhl[0]
                frm = L.SLOT_TO_API[U.get(e, 'BSXd')]
                self.move_entry(e, target)
                self.log.append([p['team'], 'moved', f"{p['first']} {p['last']}", f"from {frm}", p['num']])
            else:
                src = sorted((x for x in ents if U.get(x, 'BSXd') not in L.NHL_ALL | L.NATIONAL),
                             key=lambda x: source_rank(U.get(x, 'BSXd')))
                if src:
                    e = src[0]
                    frm = R.team_name(U.get(e, 'BSXd'))
                    self.move_entry(e, target)
                else:
                    fa = [l for l in self.fa_links if R.link_to_pid.get(l) == pid]
                    link = fa[0] if fa else self.new_link(pid)
                    e = self.new_entry(target, link, p['row'])
                    self.arrivals.setdefault(target, []).append(e)
                    frm = 'free agent' if fa else 'no team'
                self.log.append([p['team'], 'added', f"{p['first']} {p['last']}", f"from {frm}", p['num']])
            self.drop_fa(pid)
            target_entry[e] = p
        for p in api:
            if p.get('photo') and p['row'] is not None:
                self.photos[p['row']] = p['photo']

        # 3. jersey numbers from the official rosters, resolving clashes
        for team in L.NHL_PRIMARY:
            ents = self.entries_on(team)
            taken = Counter()
            before = {e: U.get(e, 'tRVs') for e in ents}
            for e in ents:
                p = target_entry.get(e)
                if p and p['num']:
                    U.set(e, 'tRVs', p['num'])
                taken[U.get(e, 'tRVs')] += 1
            for n in [n for n, c in taken.items() if c > 1]:
                # the official number wins; between two official claims the better player keeps it
                clash = sorted((e for e in ents if U.get(e, 'tRVs') == n),
                               key=lambda e: (bool(target_entry.get(e) and target_entry[e]['num'] == n), self.q(e)),
                               reverse=True)
                for e in clash[1:]:
                    # the number he wore before, if nobody has it: a second run then changes nothing
                    free = before[e] if before[e] and taken[before[e]] == 0 else next(
                        x for x in range(2, 99) if taken[x] == 0)
                    taken[n] -= 1
                    taken[free] += 1
                    U.set(e, 'tRVs', free)
                    if free != before[e]:
                        self.log.append([L.SLOT_TO_API[team], 'number changed', R.name(self.prow_of_entry(e)),
                                         f"#{n} also used by {R.name(self.prow_of_entry(clash[0]))}", free])

    def set_position(self, prow, pos):
        """Give a skater another skater position. Moving between forward and defence also moves his
        playing style into the new range (defence styles 1-4, forward styles 5-10), on his
        attribute record and on his roster entries."""
        P, U = self.P, self.U
        old = P.get(prow, 'aljv')
        if old == pos or 4 in (old, pos):
            return
        P.set(prow, 'aljv', pos)
        if (old == 3) == (pos == 3):
            return
        pid = P.get(prow, 'zIBw')
        row = self.ai_row['yvSd'].get(pid)
        if row is None:
            return
        style = self.usual_style['D' if pos == 3 else 'F']
        self.R.f['yvSd'].set(row, 'sFgQ', style)
        for e in range(U.cur_rec):
            if e not in self.deleted and self.pid_of_entry(e) == pid:
                U.set(e, 'sFgQ', style)

    def set_pro_team(self, prow, team):
        """cPbu.proteam (the NHL organisation that holds a player's rights) is team + 1 in five
        bits, so the team in slot 31 cannot be recorded."""
        if team + 1 <= self.P.field('WBbd').mask:
            self.P.set(prow, 'WBbd', team + 1)

    def nhl_lines(self):
        """Departed players' slots/letters go to newcomers, then NHL lines are re-dealt by rating
        on each team's own template. A roster this tool already built keeps the lines of teams
        whose players did not change (they may have been set by hand in the game)."""
        changed = set(self.departures) | set(self.arrivals)
        for team in changed:
            self.fill_lines(team)
        for team in L.NHL_PRIMARY:
            if team in changed or not self.maintain:
                self.lines_by_template(team, self.orig_slot_sets[team])

    def sync_mirrors(self):
        """Keep the mirror copies (classic/alternate team slots) identical to the primary team."""
        U = self.U
        for prim, mirrors in L.MIRRORS.items():
            pe = {self.pid_of_entry(e): e for e in self.entries_on(prim)}
            for m in mirrors:
                me = {self.pid_of_entry(e): e for e in self.entries_on(m)}
                for pid, e in me.items():
                    if pid not in pe:
                        self.deleted.add(e)
                for pid, src in pe.items():
                    e = me.get(pid)
                    if e is None:
                        e = U.add_record()
                        U.records[e * U.rec_len:(e + 1) * U.rec_len] = U.records[src * U.rec_len:(src + 1) * U.rec_len]
                        U.set(e, 'BSXd', m)
                        U.set(e, 'XWot', L.XWOT_UNSET)
                    for f in self.flags + ['jZSh', 'lcCm', 'tRVs', 'sFgQ']:
                        U.set(e, f, U.get(src, f))

    def finish(self):
        """Remove deleted entries, give every entry its team slot id, write the free-agent list."""
        U, Q = self.U, self.Q
        for e in sorted(self.deleted, reverse=True):
            U.delete_record(e)
        self.deleted = set()
        self.renumber_entries()
        Q.cur_rec = 0
        for link in self.fa_links:
            Q.add_record({'TWSX': link})

    def renumber_entries(self):
        """Roster entry ids are team * 40 + slot, slots 0..n-1 with no gaps (the game finds a team's
        players through them). Entries that already belong to the team keep their order."""
        U = self.U
        by_team = {}
        for i in range(U.cur_rec):
            by_team.setdefault(U.get(i, 'BSXd'), []).append(i)
        for team, ents in by_team.items():
            if len(ents) > L.MAX_PER_TEAM:
                raise RuntimeError(f"{self.R.team_name(team)} has {len(ents)} players (max {L.MAX_PER_TEAM})")
            ents.sort(key=lambda i: (U.get(i, 'XWot') // L.MAX_PER_TEAM != team, U.get(i, 'XWot') % L.MAX_PER_TEAM, i))
            for k, i in enumerate(ents):
                U.set(i, 'XWot', team * L.MAX_PER_TEAM + k)

    # --- lines by rating -----------------------------------------------------
    def lines_by_template(self, team, template):
        """Re-deal a team's line slots by rating: the i-th best player of a class (G, D, C, W) gets
        the slot set held by the i-th most-used player of that class in `template`."""
        U = self.U
        ents = self.entries_on(team)
        for e in ents:
            for f in self.flags + ['jZSh']:
                U.set(e, f, 0)
        pools = {c: sorted((e for e in ents if self.cls(e) == c), key=self.q, reverse=True) for c in 'GDCW'}
        for c in 'GDCW':
            for cc, slots, _ in template:
                if cc != c:
                    continue
                # short of forwards: the other forward position, then a spare defenceman
                pool = pools[c] or (pools['W' if c == 'C' else 'C'] or pools['D'] if c in 'CW' else [])
                if pool:
                    e = pool.pop(0)
                    for f in slots:
                        U.set(e, f, 1)
        for e in ents:
            U.set(e, 'jZSh', 1 if self.held(e) else 0)

    def set_letters(self, team):
        """Captain and two alternates for a team that has none: its three best skaters."""
        U = self.U
        ents = self.entries_on(team)
        if any(U.get(e, 'lcCm') for e in ents):
            return
        best = sorted((e for e in ents if self.cls(e) != 'G'), key=self.q, reverse=True)[:3]
        for k, e in enumerate(best):
            U.set(e, 'lcCm', 1 if k == 0 else 2)

    def fill_lines(self, team):
        U = self.U
        ents = self.entries_on(team)
        holders = {}
        for e in ents:
            for f in self.held(e):
                holders.setdefault(f, []).append(e)
        newcomers = sorted((e for e in self.arrivals.get(team, []) if e not in self.deleted), key=self.q, reverse=True)
        reserves = sorted((e for e in ents if not self.held(e) and e not in newcomers), key=self.q, reverse=True)
        pools = [newcomers, reserves]
        for cls, slots, _, captaincy in sorted(self.departures.get(team, []), key=lambda d: -len(d[1])):
            slots = {f for f in slots if f not in holders}
            if not slots:
                continue
            pick = None
            for want in (lambda c: c == cls, lambda c: c in 'CW' and cls in 'CW'):
                for pool in pools:
                    for e in pool:
                        if want(self.cls(e)):
                            pick = e
                            pool.remove(e)
                            break
                    if pick is not None:
                        break
                if pick is not None:
                    break
            if pick is None:
                continue
            for f in slots:
                U.set(pick, f, 1)
                holders.setdefault(f, []).append(pick)
        for e in ents:
            U.set(e, 'jZSh', 1 if self.held(e) else 0)
        # letters (C/A) of departed players go to the best remaining dressed skater without one
        for _, _, _, captaincy in self.departures.get(team, []):
            if not captaincy:
                continue
            cands = [e for e in ents if e not in self.deleted and U.get(e, 'jZSh') and not U.get(e, 'lcCm')
                     and self.cls(e) != 'G']
            if cands:
                U.set(max(cands, key=self.q), 'lcCm', captaincy)

    # --- EA ratings -------------------------------------------------------------
    def apply_ea_ratings(self):
        """Write the published EA attributes into the rating tables."""
        players = self.data.ea_ratings
        if not players:
            return
        P = self.P
        # fully rated players first, so a duplicate listing never downgrades someone to overall-only
        players = sorted(players, key=lambda p: -sum(v is not None for v in p.get('attrs', {}).values()))
        matched = ratings.match_players(self.R, [p for p in players if p.get('birth')])
        # players published without a birthdate: by full name among the players on NHL teams,
        # then on AHL teams (EA lists a club's farm players too); only an unambiguous match counts.
        # Other leagues are left out: a name alone is not enough among thousands of club players.
        by_name, elsewhere = {}, {}
        U = self.U
        for e in range(U.cur_rec):
            if e in self.deleted:
                continue
            t, prow = U.get(e, 'BSXd'), self.prow_of_entry(e)
            if t in L.NHL_PRIMARY:
                by_name.setdefault(self.person(prow), []).append((prow, L.SLOT_TO_API[t]))
            elif t in L.AHL:
                elsewhere.setdefault(self.person(prow), set()).add(prow)
        for p in players:
            if p.get('birth'):
                continue
            first, _, last = p['name'].partition(' ')
            key = (norm(first), norm(last))
            cands = by_name.get(key, [])
            if len(cands) > 1:
                cands = [c for c in cands if c[1] == L.team_code(p.get('team'))]
            if len(cands) == 1:
                matched.append((p, cands[0][0]))
            elif not cands and len(elsewhere.get(key, ())) == 1:
                matched.append((p, next(iter(elsewhere[key]))))
        # the same person can have several records (national-team goalies): rate all of them
        same_person = {}
        for r in range(P.cur_rec):
            key = (self.person(r), P.get(r, 'dnFq'), P.get(r, 'pLKJ'), P.get(r, 'iwsK'))
            same_person.setdefault(key, []).append(r)
        stats = Counter()
        rated = set()
        for p, prow in matched:
            goalie = ratings.is_goalie(p)
            tname = 'yuHm' if goalie else 'yvSd'
            t = self.R.f[tname]
            key = (self.person(prow), P.get(prow, 'dnFq'), P.get(prow, 'pLKJ'), P.get(prow, 'iwsK'))
            done = False
            for r in same_person.get(key, [prow]):
                pid = P.get(r, 'zIBw')
                row = self.ai_row[tname].get(pid)
                if row is None or pid in rated:
                    continue
                rated.add(pid)
                stats['attributes written'] += ratings.write_attributes(t, row, p, self.ovr_offset[goalie])
                if p.get('ovr'):
                    self.ovr[pid] = p['ovr']
                done = True
            if done:
                stats['players rated'] += 1
        self._ratings()
        self.ea_rated = rated
        for k, v in sorted(stats.items()):
            self.log.append(['ALL', 'EA ratings', k, v, ''])
        self.rating_stats = dict(stats)

    def ea_rating_for(self, first, last, birth, by_name=False):
        """EA's rating of a player the ratings step could not reach (a club league is about to create
        him, or to put him on an AHL team), found the way apply_ea_ratings would find him on a
        second run: last name + birthdate with a fitting first name, else -- for AHL players only,
        `by_name` -- a unique listing without a birthdate under his full name."""
        if not self.data.ea_ratings:
            return None
        if getattr(self, '_ea_index', None) is None:
            by_birth, no_birth = {}, {}
            for p in sorted(self.data.ea_ratings, key=lambda p: -sum(v is not None for v in p.get('attrs', {}).values())):
                fn, _, ln = p['name'].partition(' ')
                if p.get('birth'):
                    by_birth.setdefault((norm(ln), tuple(p['birth'])), []).append((norm(fn), p))
                else:
                    no_birth.setdefault((norm(fn), norm(ln)), []).append(p)
            self._ea_index = by_birth, no_birth
        by_birth, no_birth = self._ea_index
        fn = norm(first)
        found = [p for f, p in by_birth.get((norm(last), tuple(birth)), []) if same_first_name(f, fn)]
        if found:
            return found[0]
        listed = no_birth.get((fn, norm(last)), []) if by_name else []
        return listed[0] if len(listed) == 1 else None

    def write_ea_rating(self, prow, p):
        """Give a player EA's published attributes (see apply_ea_ratings). False if he has no rating row."""
        goalie = ratings.is_goalie(p)
        tname = 'yuHm' if goalie else 'yvSd'
        pid = self.P.get(prow, 'zIBw')
        row = self.ai_row[tname].get(pid)
        if row is None:
            return False
        t = self.R.f[tname]
        ratings.write_attributes(t, row, p, self.ovr_offset[goalie])
        if p.get('ovr'):
            self.ovr[pid] = p['ovr']
        self.quality[pid] = self.ovr.get(pid) or ratings.level(t, row) + self.ovr_offset[goalie]
        self.ea_rated.add(pid)
        return True

    # --- national teams the mod left empty ----------------------------------------
    def estimated_profile(self):
        """Median attribute values of the mod's European-league national players (no club team),
        per rating table and position class -- the base for players EA does not rate."""
        U, R = self.U, self.R
        national_only = {self.pid_of_entry(i) for i in range(U.cur_rec) if U.get(i, 'BSXd') in L.NATIONAL}
        national_only -= {self.pid_of_entry(i) for i in range(U.cur_rec) if U.get(i, 'BSXd') in L.CLUB}
        prof = {}
        for tname in ('yvSd', 'yuHm'):
            t = R.f[tname]
            act = self.active_fields(tname)
            groups = {}
            for i in range(t.cur_rec):
                pid = t.get(i, 'zIBw')
                if pid in national_only and pid in R.p_by_id:
                    c = {'W': 'F', 'C': 'F'}.get(L.POS_CLASS[self.P.get(R.p_by_id[pid], 'aljv')],
                                                 L.POS_CLASS[self.P.get(R.p_by_id[pid], 'aljv')])
                    groups.setdefault(c, []).append([t.get(i, n) for n in act])
            for c, rows in groups.items():
                prof[(tname, c)] = {n: sorted(r[k] for r in rows)[len(rows) // 2] for k, n in enumerate(act)}
        return prof

    def fill_empty_national(self):
        R, U, P = self.R, self.U, self.P
        rosters = self.data.iihf or {}
        prof = self.estimated_profile()
        nhl_now = {}
        for t in L.NHL_PRIMARY:
            for e in self.entries_on(t):
                nhl_now[self.person(self.prow_of_entry(e))] = self.prow_of_entry(e)
        for code, team in L.EMPTY_NATIONAL.items():
            if self.entries_on(team) or not rosters.get(code):
                continue
            self.filled_now.add(team)
            iihf = [dict(p) for p in rosters[code]]
            if code == 'BLR':  # 2021 roster: drop players who would be 38+ this season
                iihf = [p for p in iihf if p['birth'][0] >= self.data.season_year - 37]
            for p in iihf:
                p.update(team=code, birth=tuple(p['birth']))
            match(R, iihf)
            members = []  # (prow, number, source)
            for p in iihf:
                prow = p['row'] if p['row'] is not None else self.create_national(p, code, prof)
                members.append((prow, p['num'], 'IIHF'))
            # NHL players of that nationality (save nationality and NHL birth country agree)
            have = {self.person(m[0]) for m in members}
            nhl_cands = sorted((prow for k, prow in nhl_now.items()
                                if k not in have and P.get(prow, 'hleL') == L.NAT_CODE[code]
                                and self.api_country.get(prow) == code),
                               key=lambda r: self.quality.get(P.get(r, 'zIBw'), 0), reverse=True)
            for prow in nhl_cands:
                grp = {3: 'D', 4: 'G'}.get(P.get(prow, 'aljv'), 'F')
                same = [m for m in members if {3: 'D', 4: 'G'}.get(P.get(m[0], 'aljv'), 'F') == grp]
                if len(members) < 26:
                    members.append((prow, None, 'NHL'))
                elif same:
                    weakest = min(same, key=lambda m: self.quality.get(P.get(m[0], 'zIBw'), 0))
                    if self.quality.get(P.get(prow, 'zIBw'), 0) > self.quality.get(P.get(weakest[0], 'zIBw'), 0):
                        members.remove(weakest)
                        members.append((prow, None, 'NHL'))
            numbers = Counter()
            for prow, num, src in members:
                e = self.new_entry(team, self.new_link(P.get(prow, 'zIBw')), prow)
                n = num if num and not numbers[num] else next(x for x in range(2, 99) if not numbers[x])
                U.set(e, 'tRVs', n)
                numbers[n] += 1
                self.log.append([code, 'national team: added', R.name(prow), src, n])
            lines.build_lines(self, team)
            self.set_letters(team)

    def create_national(self, p, code, prof):
        """A European/Asian league player EA does not rate: repurpose a spare record, fill in the
        IIHF data and an estimated rating profile."""
        R, P = self.R, self.P
        if p['pos'] == 'G':
            pos = 4
        elif p['pos'] == 'D':
            pos = 3
        else:  # IIHF lists forwards only as F: alternate C / LW / RW
            pos = len([1 for x in self.created if P.get(x, 'aljv') in (0, 1, 2)]) % 3
        name = f"{p['first']} {p['last']}"
        prow = self.take_record(pos, name)
        old = R.name(prow)
        y, m, d = p['birth']
        self.donors.reset_identity(prow, name, L.NAT_CODE[code], y)
        self.set_text(prow, 'PedH', p['first'])
        self.set_text(prow, 'RMbQ', p['last'])
        P.set(prow, 'JzFM', '')
        P.set(prow, 'iwsK', d - 1)
        P.set(prow, 'pLKJ', m - 1)
        P.set(prow, 'dnFq', y - 1910)
        if p.get('height_cm'):
            P.set(prow, 'QBpy', max(0, min(31, round(p['height_cm'] / 2.54) - 54)))
        if p.get('weight_kg'):
            P.set(prow, 'WZNs', max(0, min(255, round(p['weight_kg'] * 2.20462) - 120)))
        if p.get('shoots') in ('L', 'R'):
            P.set(prow, 'pkRG', 0 if p['shoots'] == 'L' else 1)
        if p.get('num'):
            P.set(prow, 'tRVs', p['num'])
        for f in ('GDhI', 'dhKk', 'IrlK', 'IzRv'):
            P.set(prow, f, 0)
        P.set(prow, 'BSXd', L.EMPTY_NATIONAL[code] + 1)  # national-only player: contract team = national team
        # estimated ratings: mod's European national median, adjusted for tournament level and age
        tname, grp = ('yuHm', 'G') if pos == 4 else ('yvSd', 'D' if pos == 3 else 'F')
        base = prof.get((tname, grp))
        t = R.f[tname]
        pid = P.get(prow, 'zIBw')
        row = self.ai_row[tname].get(pid)
        if base and row is not None:
            age = self.data.season_year - y
            adj = L.NATIONAL_TIER[code] + (-2 if age < 21 else -1 if age < 24 else -1 if age > 32 else 0)
            adj += (zlib.crc32(name.encode()) % 3) - 1
            for n, v in base.items():
                t.set(row, n, max(0, min(63, v + adj)))
            self.quality[pid] = sum(base.values()) / len(base) + adj + 36 + self.ovr_offset[pos == 4]
        self.log.append([code, 'created', name, f"IIHF {code}, reused record of {old}", p.get('num')])
        return prow

    def national_teams(self, max_swaps=4):
        """Keep the filled national teams current: players who left the NHL make room for the best
        available, and (first build only) up to `max_swaps` rising stars are brought in."""
        R, U, P = self.R, self.U, self.P
        if self.maintain:
            max_swaps = 0
        rising_star_born = self.data.season_year - 24  # upgrade swaps only bring in players this young
        group = lambda prow: {3: 'D', 4: 'G'}.get(P.get(prow, 'aljv'), 'F')
        # unknown quality never counts as "weakest", so no one is swapped out on missing data
        nq = lambda e: self.quality.get(self.pid_of_entry(e), float('inf'))
        pq = lambda prow: self.quality.get(P.get(prow, 'zIBw'), 0)
        nhl_now = {}
        for t in L.NHL_PRIMARY:
            for e in self.entries_on(t):
                prow = self.prow_of_entry(e)
                nhl_now[self.person(prow)] = (prow, e)
        live = self.live_entries()
        for t in sorted(L.NATIONAL):
            members = self.entries_on(t)
            if not members or t in self.filled_now:      # a squad filled from scratch in this run is current
                continue
            abbr = R.T.get(t, 'RPbr')
            code = Counter(P.get(self.prow_of_entry(e), 'hleL') for e in members).most_common(1)[0][0]
            have = {self.person(self.prow_of_entry(e)) for e in members}
            # eligible: the save's nationality and the NHL birth country agree
            pool = sorted((v for k, v in nhl_now.items()
                           if k not in have and k not in L.NOT_ELIGIBLE and P.get(v[0], 'hleL') == code
                           and self.api_country.get(v[0]) == L.NATIONAL_ISO.get(abbr)),
                          key=lambda v: pq(v[0]), reverse=True)
            numbers = Counter(U.get(e, 'tRVs') for e in members)
            added = []

            def add(prow, club_entry, reason):
                pool.remove((prow, club_entry))
                e = self.new_entry(t, self.new_link(P.get(prow, 'zIBw')), prow)
                for n in (U.get(club_entry, 'tRVs'), P.get(prow, 'tRVs')):
                    if n and numbers[n] == 0:
                        break
                else:
                    n = next(x for x in range(2, 99) if numbers[x] == 0)
                U.set(e, 'tRVs', n)
                numbers[n] += 1
                self.arrivals.setdefault(t, []).append(e)
                added.append(e)
                self.log.append([abbr, 'national team: added', R.name(prow), reason, n])

            def remove(e, reason):
                numbers[U.get(e, 'tRVs')] -= 1
                self.release(e, live)            # off his last team: a free agent, never lost
                members.remove(e)
                self.log.append([abbr, 'national team: removed', R.name(self.prow_of_entry(e)), reason,
                                 U.get(e, 'tRVs')])

            # players who left the NHL and are no longer active make room for the best available
            for e in [e for e in members if self.person(self.prow_of_entry(e)) in self.left_keys]:
                g = group(self.prow_of_entry(e))
                remove(e, 'no longer active in the NHL')
                repl = next((v for v in pool if group(v[0]) == g), None)
                if repl:
                    add(*repl, reason=f"replaces {R.name(self.prow_of_entry(e))}")
            # up to `max_swaps` rising stars who rate above the weakest member at their position
            swaps = 0
            for prow, ce in list(pool):
                if swaps >= max_swaps:
                    break
                if P.get(prow, 'dnFq') + 1910 < rising_star_born:
                    continue
                same = [e for e in members if e not in added and group(self.prow_of_entry(e)) == group(prow)]
                if not same:
                    continue
                weakest = min(same, key=nq)
                if pq(prow) > nq(weakest) + 0.5:
                    name = R.name(self.prow_of_entry(weakest))
                    remove(weakest, f"replaced by {R.name(prow)}")
                    add(prow, ce, reason=f"rising star, replaces {name}")
                    swaps += 1
            self.fill_lines(t)

    def national_lines(self):
        changed = set(self.departures) | set(self.arrivals)
        for team in L.NATIONAL:
            if team in self.orig_slot_sets and self.entries_on(team) and (team in changed or not self.maintain):
                self.lines_by_template(team, self.orig_slot_sets[team])

    # --- contracts -----------------------------------------------------------------
    def contracts(self):
        """Keep each player's contract team (cPbu.team = team + 1) on a team he is actually on.

        The game walks a team's contracts on screens like Team Management; a contract that
        points at a player who is not on that roster makes it crash."""
        P, R = self.P, self.R
        final = self.club_teams()
        fa = {R.link_to_pid.get(l) for l in self.fa_links}
        stats = Counter()
        for pid in set(self.orig_club) | set(final):
            if self.orig_club.get(pid, set()) == final.get(pid, set()):
                continue
            prow = R.p_by_id.get(pid)
            if prow is None:
                continue
            teams = final.get(pid, set())
            nhl = sorted(t for t in teams if t in L.NHL_PRIMARY)
            if nhl:
                P.set(prow, 'BSXd', nhl[0] + 1)
                if prow in self.created or not P.get(prow, 'GDhI') or not P.get(prow, 'dhKk'):
                    entry_level = P.get(prow, 'dnFq') + 1910 >= self.data.season_year - 22
                    P.set(prow, 'GDhI', 3 if entry_level else 1)
                    P.set(prow, 'dhKk', 146 if entry_level else 116)  # ~$975k ELC / ~$775k minimum
                    P.set(prow, 'IrlK', 0)
                    P.set(prow, 'IzRv', 0)
                    stats['new contract'] += 1
                stats['contract team -> NHL'] += 1
            elif teams:
                P.set(prow, 'BSXd', min(teams) + 1)
                stats['contract team -> AHL'] += 1
            elif pid in fa:
                for f in ('BSXd', 'GDhI', 'dhKk', 'IrlK', 'IzRv'):
                    P.set(prow, f, 0)
                stats['free agent, contract cleared'] += 1
        # sweep: any contract that now points at a team the player left (e.g. national-team-only
        # European players dropped from their national team) moves to a team he is on, or is cleared
        U = self.U
        on = {}
        for i in range(U.cur_rec):
            if i not in self.deleted:
                on.setdefault(self.pid_of_entry(i), set()).add(U.get(i, 'BSXd'))
        for pid, prow in R.p_by_id.items():
            b = P.get(prow, 'BSXd')
            if not b or pid in self.orig_contract_bad:
                continue
            teams = on.get(pid, set())
            if self.same_team(b - 1) & teams:
                continue
            if teams:
                P.set(prow, 'BSXd', min(teams) + 1)
                stats['contract team -> current team'] += 1
            else:
                for f in ('BSXd', 'GDhI', 'dhKk', 'IrlK', 'IzRv'):
                    P.set(prow, f, 0)
                stats['no team left, contract cleared'] += 1
        # free agents carry no contract (club players released by a league step may still have one;
        # the NHL rights in proteam stay)
        for link in self.fa_links:
            prow = R.p_by_id.get(R.link_to_pid.get(link))
            if prow is not None and any(P.get(prow, f) for f in ('BSXd', 'GDhI', 'dhKk', 'IrlK', 'IzRv')):
                for f in ('BSXd', 'GDhI', 'dhKk', 'IrlK', 'IzRv'):
                    P.set(prow, f, 0)
                stats['free agent, contract cleared'] += 1
        for k, v in sorted(stats.items()):
            self.log.append(['ALL', 'contracts', k, f"{v} players", ''])

    @staticmethod
    def same_team(t):
        """A team and its mirror copies count as one team."""
        prim = L.MIRROR_OF.get(t, t)
        return {prim} | set(L.MIRRORS.get(prim, []))
