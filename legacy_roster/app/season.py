"""The player's own Season or Be a GM save, for the Calendar and the Front office (read only, seasonsave.py).

One source for both tabs: the newest save of the picked roster's game version that can be read, read once and kept
while its files stay the same (path and time). It is looked for again when the Calendar's "My season" switch is turned
on and when a tab that shows it comes into view. Nothing is ever written; whatever goes wrong becomes a note in plain
words, never an error.
"""
import threading

from .. import gamepatch, seasonsave

NO_RPCS3 = "Pick RPCS3 and a roster in Setup first."
NO_SAVE = "No Season or Be a GM save found for this version of the game. Play one and save it in the game."
NOT_READ = "Your Season or Be a GM save could not be read."
OFFSET = gamepatch.YEARS_LATER          # the unpatched game counts its seasons from 2015: 2015-16 is this 2026-27


def where(editor):
    """(savedata folder, title ids) of the roster picked in Setup, or None (also the Be a Pro careers', app/career.py)."""
    source, slot = getattr(editor, 'source', None), getattr(editor, 'slot', None)
    folder = source[0] if source else None
    if not folder:
        rpcs3 = getattr(getattr(editor, 'update', None), 'rpcs3', None)
        folder = getattr(rpcs3, 'savedata', None)
    if not folder:
        return None
    title = getattr(slot, 'title_id', None)
    return folder, (title,) if title else None


class SeasonSource:
    def __init__(self, editor):
        self.editor = editor
        self.lock = threading.RLock()
        self.on = False                 # the Calendar's "My season" switch (the Front office shows the record with it)
        self.season = None              # the seasonsave.Season read, or None
        self.save = None                # its seasonsave.Save
        self.note = NO_SAVE             # why there is none (when season is None)
        self._key = None                # (savedata folder, title ids) it was looked for in
        self._looked = False            # looked for at all
        self._read = None               # (path, newest file time) of the save read

    def where(self):
        return where(self.editor)

    def saves(self):
        """The Season and Be a GM saves of the picked roster's game version, newest first (empty when none or unreadable)."""
        where = self.where()
        if where is None:
            return []
        try:
            return seasonsave.find(*where)
        except Exception:
            return []

    def load(self, fresh=False):
        """The Season to show, or None (`note` says why). `fresh`: look at the saves again (a save read before is kept
        while its files are the same)."""
        with self.lock:
            where = self.where()
            if not fresh and self._looked and where == self._key:
                return self.season
            self._key, self._looked = where, True
            if where is None:
                self.season, self.save, self.note = None, None, NO_RPCS3
                return None
            saves = self.saves()
            if not saves:
                self.season, self.save, self.note = None, None, NO_SAVE
                return None
            note = None
            for save in saves:
                if not save.settled():
                    note = note or "The game is still saving. Try again in a moment."
                    continue
                key = (save.path, save.modified)
                if key == self._read and self.season is not None:
                    self.save, self.note = save, None
                    return self.season
                try:
                    season = seasonsave.read(save)
                except seasonsave.SeasonError as e:
                    note = note or f"{save.label()}: {e}"
                    continue
                except Exception:
                    note = note or f"{save.label()}: it could not be read."
                    continue
                self.season, self.save, self.note, self._read = season, save, None, key
                return season
            self.season, self.save, self.note, self._read = None, None, note or NOT_READ, None
            return None

    def switch(self, on):
        """The switch turned on (look at the saves again) or off."""
        with self.lock:
            self.on = bool(on)
            if self.on:
                self.load(fresh=True)

    def shown(self):
        """The Season while the switch is on and one is read, else None."""
        with self.lock:
            return self.season if self.on else None

    def available(self):
        with self.lock:
            return self.season is not None

    def label(self):
        with self.lock:
            return self.save.label() if self.save is not None else None

    def offset(self, season=None):
        """Years to add to the dates of `season` (default the one read) so they fall in this program's seasons: OFFSET
        for a save of the unpatched game (its first season is 2015-16), 0 for the patched game's (2026-27)."""
        season = season or self.season
        if season is None or season.first_year >= gamepatch.FIRST_SEASON:
            return 0
        # the game's own calendar has games on 29 February 2016: such a season keeps its own years
        leap = any(g.date.month == 2 and g.date.day == 29 for g in season.games)
        return 0 if leap else OFFSET

    def today(self):
        """The save's today, in this program's years (None without a save)."""
        with self.lock:
            if self.season is None:
                return None
            return moved(self.season.today, self.offset())


def moved(date, years):
    """`date` `years` later (29 February: the 28th)."""
    if not years:
        return date
    try:
        return date.replace(year=date.year + years)
    except ValueError:                  # 29 February
        return date.replace(year=date.year + years, day=28)


def record_text(row):
    """'8-3-1' of a seasonsave standings row."""
    return f"{row['w']}-{row['l']}-{row['otl']}"


def place_text(n):
    """'1st', '2nd', '3rd', '4th', '11th'."""
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def standing(season, slot, league=seasonsave.NHL):
    """(division group, its row of `slot`) of the save's standings, or (None, None)."""
    for group in season.standings(league):
        for row in group['rows']:
            if row['slot'] == slot:
                return group, row
    return None, None


def conference_rows(season, conference, league=seasonsave.NHL):
    """Every row of a conference's divisions, best first (points, then games played fewer, then wins)."""
    rows = [dict(r, division=g['division']) for g in season.standings(league) if g['conference'] == conference
            for r in g['rows']]
    return sorted(rows, key=lambda r: (-r['pts'], r['gp'], -r['w'], r['abbr']))


DAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November',
          'December')


def date_text(date):
    """'Tue 13 Oct' (English whatever the PC's language)."""
    return f"{DAYS[date.weekday()][:3]} {date.day} {MONTHS[date.month - 1][:3]}"


def long_date(date):
    """'Tuesday 13 October 2026'."""
    return f"{DAYS[date.weekday()]} {date.day} {MONTHS[date.month - 1]} {date.year}"


def season_note(source):
    """What the Calendar says under the switch while it is on."""
    today = source.today()
    if today is None:
        return source.note
    return f"Read from your save, never changed. Played up to {long_date(today)}."
