"""Turn a source roster into an updated one.

`Builder` owns the working copy of the save and the bookkeeping every step shares: roster
entries and links, the free-agent list, line slots, contracts and the change log. It also holds
the NHL and national-team steps; club leagues are in leagues/. pipeline.build() runs the steps.
"""
import heapq
import struct
import zlib
from collections import Counter

from . import layout as L
from . import lines
from . import ratings
from .donors import Donors, real_birth_year
from .matching import match, norm, same_first_name


class ChangeLog(list):
    """The change log: rows [team, change, player, detail, number], each tagged on its way in with
    the part of the update it belongs to (`section`: 'NHL', a league's name, ...) as a sixth
    column, so the list of changes can group them (Chicago and Chicoutimi are both 'CHI')."""
    section = ''

    def append(self, row):
        super().append(list(row) + [self.section])


class Data:
    """Everything the builder needs from outside the save."""

    def __init__(self, nhl_players=None, ea_ratings=None, iihf=None, season_year=2026, leagues=None, nhl_logos=None,
                 nhl_last=None, drafts=None, schedule=None, calendar=None):
        self.nhl_players = nhl_players or []   # flat list, see datasource.flatten_nhl()
        self.ea_ratings = ea_ratings           # [{'name','team','position','birth','ovr','attrs'}] or None
        self.iihf = iihf                       # {'AUT': [player, ...]} or None
        self.season_year = season_year         # the year the season starts in
        self.leagues = leagues or {}           # club leagues: {'liiga': {'teams': [{'slot', 'players', ...}]}}
        self.nhl_logos = nhl_logos or {}       # NHL.com team code -> logo link (photos and logos)
        self.nhl_last = nhl_last or []         # who played in the NHL last season; 'team' None: unsigned now
        self.drafts = drafts or []             # NHL draft picks (draft.py)
        self.schedule = schedule or []         # the season's games [date, home code, away code] (schedule.py)
        self.calendar = calendar               # which way to write them (schedule.VARIANTS), None: the default


LINK_LIMIT = 16000      # player link ids from here up are the game's own
# a free agent or a player leaving his team retires at this age when he did not play in the NHL last
# season and no league lists him (the game's own roster: stock.RETIRE_AGE)
FA_RETIRE_AGE = 35
FREE_AGENTS = "Free agents"     # the part of the list of changes for retired and unsigned free agents


def stock_retire_age():
    from .stock import RETIRE_AGE
    return RETIRE_AGE


def source_rank(team):
    """Which non-NHL entry to promote: AHL first, then prospect pools, draft classes, juniors."""
    if team in L.AHL:
        return 0
    if team in L.SYSTEM_POOL_SLOTS:
        return 1
    if 62 <= team <= 100:
        return 2
    return 3


def marker(table):
    """The row a table header names as the last one removed (the word at 0x18 is 1 and the row), or None."""
    word = struct.unpack_from('>I', table.header, 0x18)[0]
    return word & 0xFFFF if word >> 16 == 1 else None


def drop_removed_player(R):
    """The community's 2026-27 roster was saved by the game right after a player was removed: the
    entry and link tables name his rows in their headers (Jonathan Drouin: entry 225, link row
    2945), and he is on no free-agent list and has no contract team. The game treats those rows as
    removed; our update did not know, put him on the free-agent list when he was not on an NHL
    roster, and Season mode then crashed on his link (every roster this program made, from the
    community roster or the game's own, 2026-10-06). The two rows are removed here, before anything
    else looks at the roster; the markers in every table header are cleared. Returns his name, or
    None when the roster has no such player (the game's own roster and ROSTER2526 have no markers)."""
    U, C, P = R.U, R.C, R.P
    row, link_row = marker(U), marker(C)
    name = None
    if row is not None and link_row is not None and row < U.cur_rec and link_row < C.cur_rec:
        link = U.get(row, 'TWSX')
        prow = R.p_by_id.get(R.link_to_pid.get(link))
        listed = any(R.link_to_pid.get(Q_link) == R.link_to_pid.get(link) for Q_link in (R.Q.get(i, 'TWSX') for i in range(R.Q.cur_rec)))
        if C.get(link_row, 'qEfv') == link and prow is not None and P.get(prow, 'BSXd') == 0 and not listed:
            name = R.name(prow)
            U.delete_record(row)
            C.delete_record(link_row)
            R.kept_links = {link}
    if name is None and (row is not None or link_row is not None):
        # a roster this program made before the fix (0.8.0) from that roster: the markers are still in its
        # headers, but the rows moved; he is a free agent on his old link, which is dropped by
        # relink_free_agents() (pipeline.build) so that a second update does not carry the crash on
        R.stale_markers = True
    for table in R.f.tables:
        R.f[table].header[0x18:0x1C] = b'\x00\x00\xff\xff'
    R.reindex()
    return name


# Utah, Seattle and Vegas as the community roster has them: arena, city, colours. The game's own roster still
# has Arizona's arena and colours in slot 22 and the All-Star slots' (Nashville's arena for both) in 30 and 31.
NHL_LOOK = {22: ("The Delta Center", "Salt Lake, UT", (106, 179, 230), (32, 32, 32)),
            30: ("Climate Pledge Arena", "Seattle, WA", (150, 217, 216), (0, 35, 63)),
            31: ("T-Mobile Arena", "Las Vegas, NV", (238, 192, 84), (60, 59, 65))}


class Builder:
    def __init__(self, R, data, progress=None, layout=L.COMMUNITY):
        self.R = R
        self.data = data
        self.layout = layout
        self.mirrors = L.mirrors(layout)    # custom copies kept in step with their NHL team
        # players who leave a team, or are free agents, at this age retire (their records become
        # spare) unless they played in the NHL last season: in the game's own roster from 30
        # (stock.RETIRE_AGE: its 2014 players), in a community roster from FA_RETIRE_AGE
        self.retire_age = FA_RETIRE_AGE if layout == L.COMMUNITY else stock_retire_age()
        # records still in EA's year - 1900 (donors.real_birth_year): only community rosters have them
        self.stale_years = layout == L.COMMUNITY
        self.progress = progress or (lambda msg: None)
        self.U, self.P, self.C, self.Q = R.U, R.P, R.C, R.Q
        U = self.U
        self.flags = [n for n, f in U.fields.items() if f.bits == 1 and n != 'jZSh']
        self.log = ChangeLog()
        self.deleted = set()
        self.left_keys = set()  # people who left the NHL and are no longer active
        self.created = set()    # repurposed records (their old contract data is junk)
        self.arrivals = {}      # team -> [entry]
        self.departures = {}    # team -> [(pos_class, frozenset(flags), quality)]
        # player links (exhibitionplayers): new ones take the lowest free number; ids from 16000 up
        # are the game's own special links and are never handed out
        # (the link of a leftover entry taken off by drop_removed_player() is not handed out again)
        self.link_ids = {self.C.get(i, 'qEfv') for i in range(self.C.cur_rec)} | getattr(R, 'kept_links', set())
        self.free_links = (k for k in range(LINK_LIMIT) if k not in self.link_ids)
        self.link_row = {self.C.get(i, 'qEfv'): i for i in range(self.C.cur_rec)}
        self.dead_links = []    # (row, link) of retired players' links, handed out again before new ones
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
        self.positions_changed = 0  # NHL players given NHL.com's position
        self.photos = {}        # player row -> photo link, for the players placed in this run
        self.logos = {}         # team slot -> logo link
        self.looks_edits = {}   # team slot -> the player's own jerseys / centre-ice logo (edits.py)
        self.team_names = {}    # team slot -> True: the player renamed it in the Roster editor
        self.nhl_names = {t: R.team_name(t) for t in range(32)}     # as the source has them
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
        # who played in the NHL last season (never retired; the unsigned ones are free agents)
        self.last_season_people = match(R, [dict(p, birth=tuple(p['birth'])) for p in data.nhl_last])
        self.last_season = {self.P.get(p['row'], 'zIBw') for p in self.last_season_people if p['row'] is not None}
        self.listed_rows = set()    # records the club leagues list (reserve_listed): never retired
        self.league_rows = set()    # of them, the ones a club league lists (not an IIHF squad)
        self.api_pids = set()       # pids on the NHL.com rosters (nhl_rosters)
        self.national_gaps = {}     # national team -> position groups of members who retired
        self.rebuild_national = False   # the NHL step first empties the national teams (clear_national)
        self.donors = Donors(self)
        self.donors.reserve(data.nhl_last)      # not for reuse, even when on no team in the save
        self.orig_club = self.club_teams()
        self.orig_home = self.home_teams()
        # each team's original line structure: (class, slot set) of its dressed players, best first.
        # The class is the one the slots are for (a centre on a wing's line slot leaves a wing's set)
        self.orig_slot_sets = {}
        for i in range(U.cur_rec):
            if self.held(i):
                role = lines.slot_role(self.held(i)) or self.cls(i)
                self.orig_slot_sets.setdefault(U.get(i, 'BSXd'), []).append((role, self.held(i), self.q(i)))
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
    def home_teams(self):
        """pid -> the club a player plays for (his lowest team that is no national team, NHL copy or
        event team), for players who have one."""
        U, out = self.U, {}
        for i in range(U.cur_rec):
            t = U.get(i, 'BSXd')
            if i in self.deleted or t in L.NATIONAL or t in L.MIRROR_OF or t in L.EVENTS:
                continue
            pid = self.pid_of_entry(i)
            out[pid] = min(out.get(pid, t), t)
        return out

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
        if self.dead_links:     # a retired player's link: the row is taken over in place
            row, link = heapq.heappop(self.dead_links)
            self.C.set(row, 'BERR', 0)
            self.C.set(row, 'qFky', pid)
            self.R.link_to_pid[link] = pid
            return link
        link = next(self.free_links)
        self.link_ids.add(link)
        self.link_row[link] = self.C.add_record({'BERR': 0, 'qEfv': link, 'qFky': pid})
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

    def would_retire(self, pid):
        """Is this player old enough to retire (retire_age) and nobody's player any more? Not when
        he played in the NHL last season (an unsigned veteran is a free agent: Reimer), is on an
        NHL.com roster, is listed by a club league, or was placed in this run."""
        prow = self.R.p_by_id.get(pid)
        if prow is None or pid in self.last_season or pid in self.api_pids or prow in self.listed_rows:
            return False
        return real_birth_year(self.P, prow, self.stale_years) <= self.data.season_year - self.retire_age and pid not in self.attached

    def retires(self, pid):
        """A player who has left his team (or is a free agent), is on no club team any more and
        would_retire() retires instead of staying a free agent. His record is cleared of its
        contract and NHL rights and becomes a spare record for a new player; his places on national
        teams are freed (national_teams() fills them). False for everyone else. Only
        settle_free_agents(), the NHL step and stock.retire_leftovers() retire players: all run
        before any new player is made, so a second run finds no spare record the first did not."""
        ents = [x for x in self.R.entries_by_pid.get(pid, []) if x not in self.deleted]
        copies = [x for x in ents if self.U.get(x, 'BSXd') in L.MIRROR_OF]
        ents = [x for x in ents if x not in copies]
        if any(self.U.get(x, 'BSXd') not in L.NATIONAL for x in ents) or not self.would_retire(pid):
            return False
        prow = self.R.p_by_id[pid]
        for e in copies:        # places on the custom copies of his NHL team go with it (sync_mirrors)
            self.deleted.add(e)
        for e in ents:          # national teams: a 2014 squad of the game's own roster (Datsyuk, Price)
            team = self.U.get(e, 'BSXd')
            self.depart(e)
            self.deleted.add(e)
            self.national_gaps.setdefault(team, []).append({3: 'D', 4: 'G'}.get(self.P.get(prow, 'aljv'), 'F'))
            self.log.append([self.R.T.get(team, 'RPbr'), 'national team: removed', self.R.name(prow), 'retired',
                             self.U.get(e, 'tRVs')])
        for f in ('BSXd', 'GDhI', 'dhKk', 'IrlK', 'IzRv', 'WBbd'):
            self.P.set(prow, f, 0)
        self.fa_links = [l for l in self.fa_links if self.R.link_to_pid.get(l) != pid]
        self.donors.add_spare(prow)
        if getattr(self, '_pick_links', None) is None:
            picks = self.R.f['vaHq']
            self._pick_links = {picks.get(i, 'TWSX') for i in range(picks.cur_rec)}
        for link in self.R.pid_to_links.get(pid, []):      # his links are free for new players now
            if link not in self._pick_links and link in self.link_row:
                heapq.heappush(self.dead_links, (self.link_row[link], link))
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

    def create_player(self, p, required=True):
        P = self.P
        pos = L.POS_CODE[p['pos']]
        name = f"{p['first']} {p['last']}"
        prow = self.take_record(pos, name, target=self.depth[pos == 4], required=required)
        if prow is None:
            return None
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
        self.nhl_bio(prow, p)
        if p.get('num'):
            P.set(prow, 'tRVs', p['num'])
        self.log.append([p['team'], 'created', name, f"reused record of {old}", p.get('num') or ''])
        return prow

    def nhl_bio(self, prow, p):
        """NHL.com's height, weight, hand and birthplace, for every NHL player (not only new ones:
        the game's own roster has 2014's)."""
        P = self.P
        if p.get('height_in'):
            P.set(prow, 'QBpy', max(0, min(31, p['height_in'] - 54)))
        if p.get('weight_lb'):
            P.set(prow, 'WZNs', max(0, min(255, p['weight_lb'] - 120)))
        if p.get('shoots') in ('L', 'R'):
            P.set(prow, 'pkRG', 0 if p['shoots'] == 'L' else 1)
        if p.get('city'):
            self.set_text(prow, 'JzFM', p['city'])

    def former_photos(self):
        """Players on a team or the free-agent list whom no list gave a photo get last season's, from
        the leagues' `former` lists (name and birthdate): a junior the list leaves out stays with his
        club and keeps a picture (Landon DuPont, testers 0.8.0)."""
        index = {}
        for league in self.data.leagues.values():
            for p in league.get('former') or []:
                index.setdefault((norm(p['first']), norm(p['last']), tuple(p['birth'])), p['photo'])
        if not index:
            return 0
        P, R = self.P, self.R
        fa = {R.link_to_pid.get(l) for l in self.fa_links}
        live = self.live_entries()
        added = 0
        for prow in range(P.cur_rec):
            pid = P.get(prow, 'zIBw')
            if prow in self.photos or not (live.get(pid) or pid in fa):
                continue
            key = (norm(P.get(prow, 'PedH')), norm(P.get(prow, 'RMbQ')),
                   (P.get(prow, 'dnFq') + 1910, P.get(prow, 'pLKJ') + 1, P.get(prow, 'iwsK') + 1))
            if key in index:
                self.photos[prow] = index[key]
                added += 1
        return added

    # --- free agents --------------------------------------------------------------
    def reserve_listed(self, leagues):
        """The players the club leagues list (`leagues`: {step: league} as they will be built) and the
        IIHF's national squads: their records are never reused or retired, even before their league
        or national team places them."""
        from .leagues import clubs
        from .matching import match_club
        people = [p for league in leagues.values() for p in clubs.listed(league['teams'])]
        self.donors.reserve(people)
        match_club(self.R, people)
        squads = [dict(p, birth=tuple(p['birth'])) for players in (self.data.iihf or {}).values() for p in players]
        self.donors.reserve(squads)
        match(self.R, squads)
        self.listed_rows = {p['row'] for p in people + squads if p['row'] is not None}
        self.league_rows = {p['row'] for p in people if p['row'] is not None}      # a league places these

    def settle_free_agents(self):
        """Free agents who would_retire() retire: off the list, their records spare (Rask, Getzlaf,
        Price, who last played in 2022). Runs before any player is made (see retires())."""
        R = self.R
        section, self.log.section = self.log.section, FREE_AGENTS
        for link in list(self.fa_links):
            pid = R.link_to_pid.get(link)
            prow = R.p_by_id.get(pid)
            if prow is None or link not in self.fa_links:
                continue
            age = self.data.season_year - real_birth_year(self.P, prow, self.stale_years)
            if self.retires(pid):
                self.log.append(['FA', 'free agent retired', R.name(prow), f"{age}, not in the NHL last season", ''])
        self.log.section = section

    def add_unsigned(self):
        """Everyone who played in the NHL last season and is unsigned now is a free agent: the ones
        the save has get onto the list, the others are created (owner, 2026-10-04: all of them)."""
        R, P = self.R, self.P
        section, self.log.section = self.log.section, FREE_AGENTS
        on_rosters = {p.get('nhl_id') for p in self.api if p.get('nhl_id')}
        live = self.live_entries()
        fa = {R.link_to_pid.get(l) for l in self.fa_links}
        added = created = 0
        for p in sorted(self.last_season_people, key=lambda p: p['nhl_id'] or 0):
            if p.get('team') or p.get('nhl_id') in on_rosters:
                continue
            name = f"{p['first']} {p['last']}"
            row = p['row']
            if row is not None:
                pid = P.get(row, 'zIBw')
                if pid in fa or pid in self.api_pids or any(e not in self.deleted for e in live.get(pid, [])):
                    continue                    # a free agent already, or with a club in the save
                detail = 'unsigned, in the NHL last season'
                added += 1
            else:
                row = self.create_player(dict(p, team='FA', num=None, birth=tuple(p['birth'])), required=False)
                if row is None:
                    self.log.append(['FA', 'skipped', name, 'no free player record left', ''])
                    continue
                pid = P.get(row, 'zIBw')
                detail = 'unsigned, in the NHL last season: new to the game'
                created += 1
            self.fa_links.append(self.new_link(pid))
            fa.add(pid)
            if p.get('photo'):
                self.photos[row] = p['photo']
            self.log.append(['FA', 'free agent added', name, detail, ''])
        if added or created:
            self.log.append(['ALL', 'summary', 'unsigned NHL players made free agents', f"{added + created} "
                             f"({created} new to the game)", ''])
        self.log.section = section

    # --- NHL ------------------------------------------------------------------
    def nhl_rosters(self):
        """Put every player of the official rosters on his team (steps 1-3 of the original)."""
        R, U = self.R, self.U
        api = match(R, [dict(p) for p in self.data.nhl_players])
        self.api = api
        self.api_rows = {p['row'] for p in api if p['row'] is not None}
        self.api_country = {p['row']: p.get('country') for p in api if p['row'] is not None}
        api_pids = {self.P.get(p['row'], 'zIBw') for p in api if p['row'] is not None}
        self.api_pids = api_pids
        target_entry = {}
        if self.rebuild_national:      # the game's own roster, first update (clear_national)
            self.clear_national()
        # 0. free agents who retired since: before anything else, so their records are spare now
        self.settle_free_agents()

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
                elif self.retires(pid):
                    status = 'retired'
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
            self.nhl_position(p)
            self.nhl_birthdate(p)
            self.nhl_bio(p['row'], p)
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
        # 2b. last season's NHL players who are unsigned now: free agents
        self.add_unsigned()

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
                # the official number wins; between two official claims the one who already wears it
                # keeps it (so a second run, with ratings since written, changes nothing), else the
                # better player
                clash = sorted((e for e in ents if U.get(e, 'tRVs') == n),
                               key=lambda e: (bool(target_entry.get(e) and target_entry[e]['num'] == n),
                                              before[e] == n, self.q(e)),
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

    def nhl_position(self, p):
        """A player already in the save gets the position NHL.com lists him at (C, LW, RW, D): the
        community roster has some at another one (Cole Smith a left wing, Chicago one right wing
        short). Goalies and skaters never swap."""
        want = L.POS_CODE.get(p.get('pos'))
        cur = self.P.get(p['row'], 'aljv')
        if want is None or want == cur or 4 in (want, cur):
            return
        self.set_position(p['row'], want)
        self.positions_changed += 1
        self.log.append([p['team'], 'position changed', f"{p['first']} {p['last']}",
                         f"{L.POS_NAME[cur]} to {L.POS_NAME[want]}", p['num']])

    def nhl_birthdate(self, p):
        """A player found by his name (not his birthdate) gets the birthdate NHL.com lists: the game's
        own roster has Kyle Burroughs a month off, and a league step would then not know him and
        make him a second record. National-team goalies' second records are left alone (their
        records must keep one birthdate)."""
        if p.get('how') == 'birth' or not p.get('birth'):
            return
        prow = p['row']
        if len(self.records_of.get(self.identity(prow), ())) > 1:
            return
        y, m, d = p['birth']
        if y - 1910 < 0:
            return
        before = self.identity(prow)
        self.P.set(prow, 'dnFq', y - 1910)
        self.P.set(prow, 'pLKJ', m - 1)
        self.P.set(prow, 'iwsK', d - 1)
        self.records_of.pop(before, None)
        self.records_of.setdefault(self.identity(prow), []).append(prow)

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
            if team not in self.orig_slot_sets:
                self.lines_from_scratch(team)
            elif team in changed or not self.maintain:
                self.lines_by_template(team, self.orig_slot_sets[team])

    def sync_mirrors(self):
        """Keep the mirror copies (classic/alternate team slots) identical to the primary team. A
        player who was only on the copy (a community roster whose copies are out of step) becomes
        a free agent rather than a player on no team."""
        U = self.U
        live = None
        for prim, mirrors in self.mirrors.items():
            pe = {self.pid_of_entry(e): e for e in self.entries_on(prim)}
            for m in mirrors:
                me = {self.pid_of_entry(e): e for e in self.entries_on(m)}
                for pid, e in me.items():
                    if pid not in pe:
                        live = live if live is not None else self.live_entries()
                        self.release(e, live)
                for pid, src in pe.items():
                    e = me.get(pid)
                    if e is None:
                        e = U.add_record()
                        U.records[e * U.rec_len:(e + 1) * U.rec_len] = U.records[src * U.rec_len:(src + 1) * U.rec_len]
                        U.set(e, 'BSXd', m)
                        U.set(e, 'XWot', L.XWOT_UNSET)
                    for f in self.flags + ['jZSh', 'lcCm', 'tRVs', 'sFgQ']:
                        U.set(e, f, U.get(src, f))

    def nhl_identity(self):
        """The arena, city and colours of slots 22 (Utah), 30 (Seattle) and 31 (Vegas), for the game's own roster
        (NHL_LOOK). A slot whose arena another team shares gets an arena row of its own while the table has room.
        Returns how many slots were set."""
        T, A = self.R.T, self.R.f['OEtS']
        done = 0
        for slot, (arena, city, primary, secondary) in NHL_LOOK.items():
            row = T.get(slot, 'arenaid')
            if A.get(row, 'arenaname') != arena:
                if any(t != slot and T.get(t, 'arenaid') == row for t in range(T.cur_rec)):
                    if A.cur_rec >= A.max_rec:
                        continue
                    row = A.add_record(template=row)
                    A.set(row, 'index', row)
                    T.set(slot, 'arenaid', row)
                A.set(row, 'arenaname', arena)
                A.set(row, 'cityname', city)
            for kind, rgb in (('primary', primary), ('secondary', secondary)):
                for channel, value in zip('rgb', rgb):
                    T.set(slot, f"{kind}color_{channel}", value)
            done += 1
        return done

    def relink_free_agents(self):
        """Every free agent gets a new link number; his old link row goes in finish() when nothing else
        uses it. Returns how many."""
        old = list(self.fa_links)
        self.fa_links = [self.new_link(self.R.link_to_pid[link]) for link in old]
        self.old_fa_links = set(old)
        return len(old)

    def finish(self):
        """Remove deleted entries, give every entry its team slot id, write the free-agent list, and
        give back the links of removed roster places that nothing uses any more (the link table
        has room for 9,955: without this every update would use up more, until it is full)."""
        U, Q, C = self.U, self.Q, self.C
        gone = {U.get(e, 'TWSX') for e in self.deleted} | getattr(self, 'old_fa_links', set())
        for e in sorted(self.deleted, reverse=True):
            U.delete_record(e)
        used = {U.get(i, 'TWSX') for i in range(U.cur_rec)} | set(self.fa_links)
        picks = self.R.f['vaHq']
        used |= {picks.get(i, 'TWSX') for i in range(picks.cur_rec)}      # draft picks point at links too
        unused = gone - used
        for i in reversed(range(C.cur_rec)):
            if C.get(i, 'qEfv') in unused:
                C.delete_record(i)
        self.deleted = set()
        for name in self.R.f.tables:        # no "last removed row" is left to name (see drop_removed_player)
            self.R.f[name].header[0x18:0x1C] = b'\x00\x00\xff\xff'
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
    STAND_INS = {'G': 'G', 'D': 'DWC', 'C': 'CWD', 'W': 'WCD'}   # who fills a slot set of each class

    def lines_by_template(self, team, template):
        """Re-deal a team's line slots by rating: the i-th best player of a class (G, D, C, W) gets
        the slot set held by the i-th most-used player of that class in `template`. A wing's slot
        set goes to a winger of its side first (a left wing on the left), then to the other side."""
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
                # short of forwards: the other forward position, then a spare defenceman (and the
                # other way round for defence)
                pool = next((pools[k] for k in self.STAND_INS[c] if pools[k]), [])
                if pool:
                    e = pool[0]
                    side = lines.wing_side(slots) if pool is pools['W'] else None
                    natural = next((x for x in pool if self.P.get(self.prow_of_entry(x), 'aljv') == side), None)
                    if natural is not None and self.q(natural) >= self.q(e) - lines.SIDE_MARGIN:
                        e = natural         # his own side, unless that means dressing a much weaker player
                    pool.remove(e)
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
        name_only = set()           # records rated by name alone: only while on an NHL or AHL team
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
                name_only.add(cands[0][0])
            elif not cands and len(elsewhere.get(key, ())) == 1:
                matched.append((p, next(iter(elsewhere[key]))))
                name_only.add(next(iter(elsewhere[key])))
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
        self.ea_name_only = {P.get(r, 'zIBw') for r in name_only} & rated
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

    def unrate_name_only(self, pid):
        """A player EA's rating reached by name alone (no birthdate: only on NHL and AHL teams) who now
        joins a club elsewhere: from now on he counts as the next run will see him, by his attributes
        (they stay as EA's rating wrote them). Otherwise lines dealt on EA's overall in this run
        differ from the next run's (Joona Koppanen, 75 by EA, 74.5 by his attributes, at Luleå)."""
        if pid not in getattr(self, 'ea_name_only', ()):
            return
        self.ea_name_only.discard(pid)
        self.ea_rated.discard(pid)
        self.ovr.pop(pid, None)
        for tname in ('yvSd', 'yuHm'):
            row = self.ai_row[tname].get(pid)
            if row is not None:
                self.quality[pid] = ratings.level(self.R.f[tname], row) + self.ovr_offset[tname == 'yuHm']

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

    # the smallest squad a filled national team gets (2 goalies and 18 skaters dress, plus spares)
    NATIONAL_MINIMUM = {'G': 3, 'D': 7, 'F': 13}

    def fill_empty_national(self):
        """Fill every national team the source leaves empty: the eight the base roster never had,
        and any squad a community roster emptied. Members: the latest IIHF roster (players not in
        the save get a spare record), NHL players of that nationality, then -- where positions are
        still short -- other players of that nationality in the save (AHL, European clubs, juniors,
        prospect pools, free agents), best first; at most 26. A country without enough players to
        dress 2 goalies and 18 skaters keeps its empty squad."""
        R, U, P = self.R, self.U, self.P
        rosters = self.data.iihf or {}
        prof = self.estimated_profile()
        group = lambda prow: {3: 'D', 4: 'G'}.get(P.get(prow, 'aljv'), 'F')
        quality = lambda prow: self.quality.get(P.get(prow, 'zIBw'), 0)
        nhl_now, elsewhere = {}, {}
        for t in L.NHL_PRIMARY:
            for e in self.entries_on(t):
                nhl_now[self.person(self.prow_of_entry(e))] = self.prow_of_entry(e)
        for e in range(U.cur_rec):
            t = U.get(e, 'BSXd')
            if e not in self.deleted and t not in L.NHL_ALL and t not in L.NATIONAL and t not in L.EVENTS:
                elsewhere.setdefault(self.person(self.prow_of_entry(e)), self.prow_of_entry(e))
        for link in self.fa_links:
            prow = R.p_by_id.get(R.link_to_pid.get(link))
            if prow is not None:
                elsewhere.setdefault(self.person(prow), prow)
        for team in sorted(L.NATIONAL):
            code = L.NATIONAL_ISO.get(R.T.get(team, 'RPbr'))
            if self.entries_on(team) or code not in L.NAT_CODE:
                continue
            iihf = [dict(p) for p in rosters.get(code) or []]
            if code == 'BLR':  # 2021 roster: drop players who would be 38+ this season
                iihf = [p for p in iihf if p['birth'][0] >= self.data.season_year - 37]
            for p in iihf:
                p.update(team=code, birth=tuple(p['birth']))
            match(R, iihf)
            members = []  # (prow or IIHF player still to be created, number, source)
            for p in iihf:
                members.append((p['row'] if p['row'] is not None else p, p['num'], 'IIHF'))
            grp = lambda m: group(m[0]) if isinstance(m[0], int) else {'G': 'G', 'D': 'D'}.get(m[0]['pos'], 'F')
            qual = lambda m: (quality(m[0]) if isinstance(m[0], int) else
                              (self._national_estimate(m[0], code, prof) or (0, 0, 0, 0))[3])
            have = {self.person(m[0]) for m in members if isinstance(m[0], int)}

            def room_for(g):
                """A free place for one more player of group g that still leaves enough places for
                every other group's minimum (Russia has no IIHF roster: its best NHL players alone
                would be 26 forwards and goalies, and the game needs 6 defencemen)."""
                count = Counter(grp(m) for m in members)
                short = sum(max(0, need - count[h]) for h, need in self.NATIONAL_MINIMUM.items() if h != g)
                return len(members) < 26 and (count[g] < self.NATIONAL_MINIMUM[g] or 26 - len(members) > short)
            # NHL players of that nationality (save nationality and NHL birth country agree)
            nhl_cands = sorted((prow for k, prow in nhl_now.items()
                                if k not in have and P.get(prow, 'hleL') == L.NAT_CODE[code]
                                and self.api_country.get(prow) == code),
                               key=quality, reverse=True)
            for prow in nhl_cands:
                same = [m for m in members if grp(m) == group(prow)]
                if room_for(group(prow)):
                    members.append((prow, None, 'NHL'))
                elif len(members) >= 26 and same:
                    weakest = min(same, key=qual)
                    if quality(prow) > qual(weakest):
                        members.remove(weakest)
                        members.append((prow, None, 'NHL'))
            # positions still short: the country's players elsewhere in the save
            have = {self.person(m[0]) for m in members if isinstance(m[0], int)}
            others = sorted((prow for k, prow in elsewhere.items()
                             if k not in have and k not in nhl_now and P.get(prow, 'hleL') == L.NAT_CODE[code]
                             and P.get(prow, 'dnFq') + 1910 >= self.data.season_year - 38
                             and not self.would_retire(P.get(prow, 'zIBw'))),
                            key=lambda r: (-quality(r), r))
            for prow in others:
                g = group(prow)
                if len(members) >= 26:
                    break
                if sum(grp(m) == g for m in members) < self.NATIONAL_MINIMUM[g]:
                    members.append((prow, None, 'club'))
            # places kept for a position nobody else could fill: the best NHL players left
            have = {self.person(m[0]) for m in members if isinstance(m[0], int)}
            for prow in nhl_cands:
                if len(members) >= 26:
                    break
                if self.person(prow) not in have:
                    members.append((prow, None, 'NHL'))
            count = Counter(grp(m) for m in members)
            # the game dresses 2 goalies, 6 defencemen and 12 forwards (verify.structure)
            if count['G'] < 2 or count['D'] < 6 or count['D'] + count['F'] < 18:
                self.log.append([code, 'national team: left empty', R.team_name(team),
                                 f"{count['G']} goalies, {count['D']} defencemen and "
                                 f"{count['D'] + count['F']} skaters found", ''])
                continue
            self.filled_now.add(team)
            numbers = Counter()
            for who, num, src in members:
                prow = who if isinstance(who, int) else self.create_national(who, code, prof, team)
                e = self.new_entry(team, self.new_link(P.get(prow, 'zIBw')), prow)
                n = num if num and not numbers[num] else next(x for x in range(2, 99) if not numbers[x])
                U.set(e, 'tRVs', n)
                numbers[n] += 1
                self.log.append([code, 'national team: added', R.name(prow), src, n])
            lines.build_lines(self, team)
            self.set_letters(team)

    def clear_national(self):
        """The game's own roster, first update: its national teams are 2014's, so they are emptied and
        filled again like the ones the community left empty (fill_empty_national). Their members who
        are on no other team retire (would_retire) or become free agents: never a teamless record,
        which the next update would reuse and so differ from this one."""
        self.rebuild_national = False
        R, U = self.R, self.U
        gone = set()
        for e in range(U.cur_rec):
            if e not in self.deleted and U.get(e, 'BSXd') in L.NATIONAL:
                self.deleted.add(e)
                gone.add(self.pid_of_entry(e))
        live = self.live_entries()
        fa = {R.link_to_pid.get(l) for l in self.fa_links}
        retired = freed = 0
        for pid in sorted(p for p in gone if p in R.p_by_id):
            if any(e not in self.deleted for e in live.get(pid, [])) or pid in fa:
                continue
            if self.retires(pid):
                retired += 1
            else:
                link = next((l for l in R.pid_to_links.get(pid, []) if l in self.link_row), None)
                self.fa_links.append(link if link is not None else self.new_link(pid))
                fa.add(pid)
                freed += 1
        self.log.append(['ALL', 'summary', "2014's national teams emptied, to be filled again",
                         f"{len(gone)} players: {retired} retired, {freed} free agents", ''])

    def _national_estimate(self, p, code, prof):
        """(rating table, attribute profile, adjustment, quality) for an IIHF player EA does not
        rate: the mod's European national median, adjusted for tournament level and age. None
        when the save has no such profile."""
        goalie = p['pos'] == 'G'
        tname, grp = ('yuHm', 'G') if goalie else ('yvSd', 'D' if p['pos'] == 'D' else 'F')
        base = prof.get((tname, grp))
        if not base:
            return None
        name = f"{p['first']} {p['last']}"
        age = self.data.season_year - p['birth'][0]
        adj = L.NATIONAL_TIER.get(code, 0) + (-2 if age < 21 else -1 if age < 24 else -1 if age > 32 else 0)
        adj += (zlib.crc32(name.encode()) % 3) - 1
        return tname, base, adj, sum(base.values()) / len(base) + adj + 36 + self.ovr_offset[goalie]

    def create_national(self, p, code, prof, team):
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
        P.set(prow, 'BSXd', team + 1)  # national-only player: contract team = national team
        estimate = self._national_estimate(p, code, prof)
        pid = P.get(prow, 'zIBw')
        if estimate and self.ai_row[estimate[0]].get(pid) is not None:
            tname, base, adj, quality = estimate
            t, row = R.f[tname], self.ai_row[tname][pid]
            for n, v in base.items():
                t.set(row, n, max(0, min(63, v + adj)))
            self.quality[pid] = quality
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
            # places of members who retired in this run (retires())
            for g in self.national_gaps.pop(t, []):
                repl = next((v for v in pool if group(v[0]) == g), None)
                if repl:
                    add(*repl, reason="replaces a retired player")
            # up to `max_swaps` rising stars who rate above the weakest member at their position (never
            # one who would retire as a free agent: the next update would retire him, and differ)
            swaps = 0
            for prow, ce in list(pool):
                if swaps >= max_swaps:
                    break
                if P.get(prow, 'dnFq') + 1910 < rising_star_born:
                    continue
                same = [e for e in members if e not in added and group(self.prow_of_entry(e)) == group(prow)
                        and not self.would_retire(self.pid_of_entry(e))]
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
            ents = self.entries_on(team)
            if not ents:
                continue
            if team not in self.orig_slot_sets and team not in self.filled_now:
                # players but no line structure (a squad a community roster left unfinished): deal
                # lines from scratch, or the game would see a team that dresses nobody
                self.lines_from_scratch(team)
            elif team in self.orig_slot_sets and (team in changed or not self.maintain):
                self.lines_by_template(team, self.orig_slot_sets[team])

    def lines_from_scratch(self, team):
        """Deal every line slot of a team that has no structure of its own to copy (lines.py) and
        give it letters; a team too short to dress 20 keeps no lines."""
        try:
            lines.build_lines(self, team)
        except lines.NotEnoughPlayers:
            for e in self.entries_on(team):
                for f in self.flags + ['jZSh']:
                    self.U.set(e, f, 0)
            return
        self.set_letters(team)

    # --- goalie equipment ------------------------------------------------------------
    GEAR_PARTS = ('pads', 'blocker', 'trapper')

    def goalie_gear(self):
        """A goalie who changed club (or is new: a record taken over) wears his old club's colours:
        EA painted each goalie's pads, blocker and glove (exhibitiongoalieequipment) in his 2014
        team's colours on white. The coloured parts are painted in the new club's colours: the first
        colour becomes its primary, the second its secondary; white, grey and black stay. A goalie
        whose club did not change is left alone, so a second run changes nothing."""
        R, P, T = self.R, self.P, self.R.T
        G = R.f['lVMf']
        rows = {G.get(i, 'zIBw'): i for i in range(G.cur_rec)}
        now = self.home_teams()
        painted = 0
        for pid, team in sorted(now.items()):
            prow = R.p_by_id.get(pid)
            if prow is None or P.get(prow, 'aljv') != 4 or pid not in rows:
                continue
            if self.orig_home.get(pid) == team and prow not in self.created:
                continue
            club = [tuple(T.get(team, f"{k}color_{c}") for c in 'rgb') for k in ('primary', 'secondary')]
            g = rows[pid]
            order = []          # the gear's own colours, in the order they first appear
            for part in self.GEAR_PARTS:
                for z in range(1, 10):
                    colour = tuple(G.get(g, f"{part}zone{z}color_{c}") for c in 'rgb')
                    if max(colour) - min(colour) >= 40 and colour not in order:
                        order.append(colour)
            if not order:
                continue
            for part in self.GEAR_PARTS:
                for z in range(1, 10):
                    colour = tuple(G.get(g, f"{part}zone{z}color_{c}") for c in 'rgb')
                    if colour in order:
                        for c, v in zip('rgb', club[order.index(colour) % 2]):
                            G.set(g, f"{part}zone{z}color_{c}", v)
            painted += 1
        self.gear_painted = painted
        if painted:
            self.log.append(['ALL', 'summary', "goalie equipment painted in the new club's colours",
                             f"{painted} goalies", ''])

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
