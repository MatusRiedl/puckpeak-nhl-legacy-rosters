"""The player's Season and Be a GM saves, read only: the calendar with results, the records, the standings.

The game keeps a Season in folders `<TITLE>10NN` (autosaves `1000A` / `1001A`) and a Be a GM in `<TITLE>01NN`
(`0100A` / `0101A`), as files DATA0000, DATA0001, ... that together are one file in a roster's layout: a name
("PS3SeasonFile", "PS3DynastyFile") at 0, the section size at 0x24, its CRC at 0x28 (the roster's rule), the zlib
length at 0x2C (little-endian) and the stream at 0x30. Inside is one database of the league (41 tables in a Season,
49 in a Be a GM). The tables read here (names from the disc's db/nhlng-meta.xml):

    leaguescheduletable  one row per game: round (0 the season, 1-4 the playoff rounds, 6 the preseason), status
                         (2: a playoff game that was not needed), league (0 NHL, 1 the farm league), month
                         (0 = January) and day (0-based), home and away (league keys), index (the row's number)
    leaguegamestats      one row per game played: index (the schedule row), the score, otgame / shootout
    leagueteams          one row per league key: teamid (the roster slot), league, abbreviation, division, conference
    leaguestates         (tier, type) -> value: (0, 0) today in days since 1 January 1900, (t, 4) the player's
                         team key in league t (0 NHL, 1 the farm league), (0, 3) the same as a mask, (0, 13) the
                         league's year (2015 in the first season, also on the patched game)

This reads a save once into memory and never writes. A save written in the last SETTLE seconds, or one that changes
while it is read, is left alone: the game may still be writing it. Checked on 13 lab saves of both versions
(docs/notes/season-saves.md): the schedule rows are the real 2026-27 calendar game for game, the records made from
the played games are the game's own (leagueteamseasonstats) for every team, and a Season's Stanley Cup final came
out as it was played (lab round 28).
"""
import datetime
import os
import re
import struct
import time
import zlib

from .sfo import Sfo
from .tdb import RosterFile, crc32_bzip2

KINDS = {b'PS3SeasonFile': 'season', b'PS3DynastyFile': 'gm'}
MODES = {'season': 'Season', 'gm': 'Be a GM'}
FOLDER = re.compile(r'^([A-Z]{4}\d{5})(10|01)(\d{2})(A?)$')      # a Season (10NN) or a Be a GM (01NN); A: an autosave
DATA = re.compile(r'^DATA\d{4}$')
SETTLE = 5                             # seconds a save must be left alone before it is read
EPOCH = datetime.date(1900, 1, 1)      # leaguestates' day 0 (a new Be a GM: 46274 = 11 September 2026)
NEW_YEAR = (9, 11)                     # the game's fixed new year: from then on the save holds the next season's games

NHL, FARM = 0, 1                       # the schedule's leagues (also leaguestates' tiers)
SEASON, PRESEASON = 0, 6               # rounds; 1-4 are the playoff rounds
NOT_NEEDED = 2                         # status of a playoff game the series did not need
MIN_GAMES = 10                         # a team in the standings plays more (the All-Star teams play one game)

SCHEDULE, PLAYED, TEAMS, STATES = 'yvnq', 'kPYO', 'sbGR', 'WRGI'
ROW = {'round': 'XpWK', 'status': 'fdgg', 'day': 'iwsK', 'league': 'jjMx', 'month': 'pLKJ', 'index': 'qEfv',
       'home': 'qkhY', 'away': 'rOMv'}
SCORE = {'index': 'qEfv', 'home': 'OTmz', 'away': 'PFHk', 'ot': 'UcZh', 'so': 'EgBC'}
TEAM = {'slot': 'gXCm', 'league': 'jjMx', 'abbr': 'nnsx', 'name': 'JkmY', 'division': 'KMGC', 'conference': 'uTwO'}
STATE = {'tier': 'IjBZ', 'type': 'zXpZ', 'value': 'XfbS'}
TODAY, HUMAN_MASK, HUMAN, YEAR = 0, 3, 4, 13       # leaguestates types
FIRST_YEAR = 2015                                  # the league's year in a first season

DIVISIONS = {3: 'Pacific', 4: 'Central', 5: 'Atlantic', 6: 'Metropolitan',
             10: 'Atlantic', 11: 'North', 12: 'Central', 13: 'Pacific'}       # the 2026-27 names
CONFERENCES = {1: 'Western', 2: 'Eastern', 8: 'Western', 9: 'Eastern'}


class SeasonError(ValueError):
    """The save cannot be read (the message says why, in words for players)."""


class Save:
    """A Season or Be a GM save in a savedata folder (only its name and times are read)."""

    def __init__(self, path, kind):
        self.path = path
        self.folder = os.path.basename(path)
        m = FOLDER.match(self.folder)
        self.title_id, self.autosave = m.group(1), bool(m.group(4))
        self.kind = kind
        self.files = data_files(path)
        self.modified = max(os.path.getmtime(p) for p in self.files)
        try:
            self.name = Sfo.load(os.path.join(path, 'PARAM.SFO')).get('SUB_TITLE', '') or self.folder
        except (OSError, ValueError):
            self.name = self.folder

    @property
    def mode(self):
        return MODES[self.kind]

    def settled(self, now=None):
        return (now if now is not None else time.time()) - self.modified >= SETTLE

    def label(self):
        return f"{self.mode}: {self.name}   (saved {datetime.datetime.fromtimestamp(self.modified):%Y-%m-%d %H:%M})"


def data_files(path):
    return [os.path.join(path, n) for n in sorted(os.listdir(path)) if DATA.match(n)]


def kind_of(path):
    """'season' / 'gm' when `path` is a folder with a Season / Be a GM save, else None (reads 16 bytes)."""
    if not FOLDER.match(os.path.basename(path)) or not os.path.isdir(path):
        return None
    first = os.path.join(path, 'DATA0000')
    try:
        with open(first, 'rb') as f:
            head = f.read(16)
    except OSError:
        return None
    return KINDS.get(head.rstrip(b'\0'))


def find(savedata, title_ids=None):
    """The Season and Be a GM saves in a savedata folder (of the games `title_ids`, default every one), newest first."""
    if not savedata or not os.path.isdir(savedata):
        return []
    saves = []
    for name in os.listdir(savedata):
        m = FOLDER.match(name)
        if not m or (title_ids and m.group(1) not in title_ids):
            continue
        path = os.path.join(savedata, name)
        kind = kind_of(path)
        if kind:
            try:
                saves.append(Save(path, kind))
            except (OSError, ValueError):
                pass
    return sorted(saves, key=lambda s: s.modified, reverse=True)


def _raw(save, now=None):
    if not save.settled(now):
        raise SeasonError("The game is still saving. Try again in a moment.")
    before = [os.path.getmtime(p) for p in save.files]
    parts = []
    for p in save.files:
        with open(p, 'rb') as f:
            parts.append(f.read())
    if [os.path.getmtime(p) for p in save.files] != before:
        raise SeasonError("The game is still saving. Try again in a moment.")
    return b''.join(parts)


def database(raw):
    """The league's database (a RosterFile without a roster's checks) of a Season / Be a GM save's bytes."""
    if len(raw) < 0x30 or raw[:16].rstrip(b'\0') not in KINDS:
        raise SeasonError("This is not a Season or Be a GM save.")
    size, stored = struct.unpack_from('>II', raw, 0x24)
    if 0x2C + size > len(raw) or crc32_bzip2(raw[0x2C:0x2C + size]) != stored:
        raise SeasonError("This save is damaged or not complete.")
    zlen = struct.unpack_from('<I', raw, 0x2C)[0]
    try:
        db = zlib.decompress(raw[0x30:0x30 + zlen])
        f = RosterFile.__new__(RosterFile)
        f._parse_db(db)
    except (zlib.error, ValueError, struct.error) as e:
        raise SeasonError("This save could not be read.") from e
    for tag in (SCHEDULE, TEAMS, STATES):
        if tag not in f.tables:
            raise SeasonError("This save could not be read.")
    return f


def read(save, now=None):
    """The Season of a `Save` (or a folder path)."""
    if not isinstance(save, Save):
        kind = kind_of(save)
        if not kind:
            raise SeasonError("This is not a Season or Be a GM save.")
        save = Save(save, kind)
    return Season(database(_raw(save, now)), save)


def _rows(table, names):
    return [{k: table.get(i, tag) for k, tag in names.items()} for i in range(table.cur_rec)]


class Team:
    def __init__(self, key, slot, league, abbr, name, division, conference):
        self.key, self.slot, self.league, self.abbr, self.name = key, slot, league, abbr, name
        self.division, self.conference = division, conference


class Game:
    """One row of the calendar. `home` / `away` are roster slots; `score` (home, away) and `extra` ('OT', 'SO' or
    None) are there once it is played. A shootout's score counts the deciding goal, as the game shows it."""

    def __init__(self, index, date, league, round_, status, home, away, score=None, extra=None):
        self.index, self.date, self.league, self.round, self.status = index, date, league, round_, status
        self.home, self.away, self.score, self.extra = home, away, score, extra

    @property
    def played(self):
        return self.score is not None

    @property
    def playoffs(self):
        return self.round not in (SEASON, PRESEASON)


class Season:
    def __init__(self, f, save=None):
        self.save = save
        self.kind = save.kind if save else None
        states = {(r['tier'], r['type']): r['value'] for r in _rows(f[STATES], STATE)}
        self.today = EPOCH + datetime.timedelta(states.get((NHL, TODAY), 0))
        self.year = states.get((NHL, YEAR), FIRST_YEAR)
        self.number = self.year - FIRST_YEAR + 1          # 1 = the first season
        self.first_year = self.today.year if (self.today.month, self.today.day) >= NEW_YEAR else self.today.year - 1
        self.teams = {}
        for key, r in enumerate(_rows(f[TEAMS], TEAM)):
            self.teams[key] = Team(key, r['slot'], r['league'], r['abbr'], r['name'], r['division'], r['conference'])
        self.human = self._human(states, NHL)
        self.farm = self._human(states, FARM)
        scores = {}
        if PLAYED in f.tables:
            for r in _rows(f[PLAYED], SCORE):
                scores[r['index']] = r
        self.games = []
        for r in _rows(f[SCHEDULE], ROW):
            home, away = self.teams.get(r['home']), self.teams.get(r['away'])
            if home is None or away is None:
                continue
            date = datetime.date(self.first_year + (r['month'] < 6), r['month'] + 1, r['day'] + 1)
            s = scores.get(r['index'])
            score = (s['home'], s['away']) if s else None
            extra = ('SO' if s['so'] else 'OT' if s['ot'] else None) if s else None
            self.games.append(Game(r['index'], date, r['league'], r['round'], r['status'], home.slot, away.slot,
                                   score, extra))

    def _human(self, states, tier):
        key = states.get((tier, HUMAN))
        if key in self.teams:
            return self.teams[key].slot
        mask = states.get((tier, HUMAN_MASK)) or 0
        if tier == NHL and mask:
            low = (mask & -mask).bit_length() - 1
            if low in self.teams:
                return self.teams[low].slot
        return None

    @property
    def mode(self):
        return MODES.get(self.kind, '')

    def team(self, slot):
        return next((t for t in self.teams.values() if t.slot == slot), None)

    def results(self, league=None, first_year=None):
        """{(ISO date, home slot, away slot): (home goals, away goals, 'OT' / 'SO' / None)} of the played games.
        `first_year` dates them in another season (same month and day): the unpatched game counts its seasons from
        2015, while the roster's calendar it plays is this season's."""
        out = {}
        for g in self.games:
            if g.played and (league is None or g.league == league):
                date = g.date
                if first_year is not None:
                    try:
                        date = date.replace(year=first_year + (date.year > self.first_year))
                    except ValueError:                     # 29 February
                        continue
                out[date.isoformat(), g.home, g.away] = (g.score[0], g.score[1], g.extra)
        return out

    def records(self, league=NHL):
        """{slot: record} of the season's teams in `league` (regular season only), as the game counts them: wins and
        losses in overtime and in the shootout apart, goals without the shootout's deciding goal."""
        counts = {}
        for g in self.games:
            if g.league == league and g.round == SEASON:
                for slot in (g.home, g.away):
                    counts[slot] = counts.get(slot, 0) + 1
        out = {slot: _Record() for slot, n in counts.items() if n >= MIN_GAMES}
        for g in sorted(self.games, key=lambda g: (g.date, g.index)):
            if g.league != league or g.round != SEASON or not g.played or g.home not in out or g.away not in out:
                continue
            (h, a), so = g.score, g.extra == 'SO'
            for slot, mine, theirs, home in ((g.home, h, a, True), (g.away, a, h, False)):
                out[slot].add(mine, theirs, g.extra, home, so)
        return out

    def record(self, slot, league=NHL):
        return self.records(league).get(slot)

    def standings(self, league=NHL):
        """[{'division', 'conference', 'rows': [record dicts, best first]}] in the game's division numbers' order."""
        records = self.records(league)
        groups = {}
        for slot, rec in records.items():
            t = self.team(slot)
            groups.setdefault((t.conference, t.division), []).append((slot, rec))
        out = []
        for (conference, division), members in sorted(groups.items()):
            rows = sorted(members, key=lambda m: m[1].order(self.team(m[0]).abbr))
            out.append({'division': DIVISIONS.get(division, f"Division {division}"),
                        'conference': CONFERENCES.get(conference, ''),
                        'rows': [dict(rec.as_dict(), slot=slot, abbr=self.team(slot).abbr, place=n + 1)
                                 for n, (slot, rec) in enumerate(rows)]})
        return out

    def place(self, slot, league=NHL):
        """(place, division name) of a team in its division, or None."""
        for group in self.standings(league):
            for row in group['rows']:
                if row['slot'] == slot:
                    return row['place'], group['division']
        return None


class _Record:
    def __init__(self):
        self.w = self.l = self.otw = self.sow = self.otl = self.sol = self.gf = self.ga = 0
        self.home = [0, 0, 0]
        self.away = [0, 0, 0]
        self.results = []                                  # 'W' / 'L' / 'O' in date order

    def add(self, mine, theirs, extra, home, so):
        won = mine > theirs
        self.gf += mine - (1 if won and so else 0)
        self.ga += theirs - (1 if not won and so else 0)
        if won:
            if extra == 'SO':
                self.sow += 1
            elif extra == 'OT':
                self.otw += 1
            else:
                self.w += 1
        elif extra == 'SO':
            self.sol += 1
        elif extra == 'OT':
            self.otl += 1
        else:
            self.l += 1
        side = self.home if home else self.away
        side[0 if won else 2 if extra else 1] += 1
        self.results.append('W' if won else 'O' if extra else 'L')

    @property
    def wins(self):
        return self.w + self.otw + self.sow

    @property
    def ot_losses(self):
        return self.otl + self.sol

    @property
    def gp(self):
        return self.wins + self.l + self.ot_losses

    @property
    def points(self):
        return 2 * self.wins + self.ot_losses

    def text(self):
        return f"{self.wins}-{self.l}-{self.ot_losses}"

    def streak(self):
        if not self.results:
            return ''
        last, n = self.results[-1], 0
        for r in reversed(self.results):
            if r != last:
                break
            n += 1
        return f"{last}{n}"

    def order(self, abbr):
        # points, fewer games, wins in regulation and overtime, wins, goal difference (the game's own order is not
        # known; docs/notes/season-saves.md)
        return (-self.points, self.gp, -(self.w + self.otw), -self.wins, -(self.gf - self.ga), abbr)

    def as_dict(self):
        last10 = self.results[-10:]
        return {'gp': self.gp, 'w': self.wins, 'l': self.l, 'otl': self.ot_losses, 'pts': self.points,
                'row': self.w + self.otw, 'gf': self.gf, 'ga': self.ga, 'text': self.text(),
                'home': '-'.join(map(str, self.home)), 'away': '-'.join(map(str, self.away)),
                'last10': f"{last10.count('W')}-{last10.count('L')}-{last10.count('O')}", 'streak': self.streak()}
