"""One entry point for building an updated roster: used by the GUI, the CLI and the tests."""
import collections
import csv
import datetime
import os
import sys
from collections import Counter

from . import datasource, draft, savedata, schedule, stock
from . import layout as L
from .builder import FREE_AGENTS, Builder, drop_removed_player
from .leagues import clubs, pools
from .roster import Roster
from .verify import verify

# what the user can tick; steps run in this order whatever order they are given in
NHL, RATINGS, NATIONAL = 'nhl', 'ratings', 'national'
CORE_STEPS = (NHL, RATINGS, NATIONAL)
# the game's calendar (schedule.py): the real schedule of the season, 30 teams; played by the owner on 2026-10-06 and on
# by default since (the year label stays 2015, Seattle and Vegas play Play Now only)
SCHEDULE = 'schedule'
# club leagues, available when the data pack has rosters for them
LEAGUE_ORDER = ('liiga', 'extraliga', 'shl', 'del', 'nl', 'norway', 'ahl', 'chl')
STEP_LABELS = {NHL: "NHL rosters, numbers, lines and captains",
               RATINGS: "Player ratings",
               NATIONAL: "National teams",
               'liiga': "Liiga: real clubs", 'extraliga': "Extraliga: real clubs", 'shl': "SHL: real clubs",
               'del': "DEL: real clubs", 'nl': "National League: real clubs", 'norway': "Norway: real clubs",
               'ahl': "AHL rosters", 'chl': "CHL (OHL / QMJHL / WHL)",
               SCHEDULE: "Calendar 2026-27"}
LEAGUE_NAMES = {'liiga': "Liiga", 'extraliga': "Extraliga", 'shl': "SHL", 'del': "DEL", 'nl': "National League",
                'norway': "Norway", 'ahl': "AHL", 'chl': "CHL (OHL / QMJHL / WHL)"}
# the parts of the update, as the change log tags its rows (builder.ChangeLog) and the list of changes groups them
SECTION_NHL, SECTION_RATINGS, SECTION_NATIONAL = "NHL", "Player ratings", "National teams"
SECTION_POOLS, SECTION_EDITS, SECTION_CONTRACTS = "Prospect pools", "My edits", "Contracts"
SECTION_STOCK = "The game's own roster"
SECTION_FREE_AGENTS, SECTION_PLAYER_DATA = FREE_AGENTS, "Player data"
SECTION_PICTURES = "Pictures not installed"


def usable_clubs(R, league):
    """A league's clubs without those whose slot is a custom team that is switched off (the game's
    own roster has Coachella Valley's and Henderson's slots, 234 and 235, off): those clubs are left
    out, like clubs the game has no slot for."""
    off = [t for t in league['teams'] if R.T.get(t['slot'], 'league') == L.CUSTOM_LEAGUE and not R.T.get(t['slot'], 'NYKk')]
    if not off:
        return league
    out = dict(league)
    out['teams'] = [t for t in league['teams'] if t not in off]
    out['left_out'] = list(league.get('left_out') or []) + [t['full'] for t in off]
    out['extra'] = list(league.get('extra') or []) + off       # for a player's own team of that name
    return out


def with_own_teams(R, league, taken, mirrors):
    """The league with the player's own custom teams named after its left-out clubs added
    (clubs.own_teams). `taken`: slots already used, grown by the ones given out here."""
    own = clubs.own_teams(R, league, taken, mirrors)
    taken.update(t['slot'] for t in league['teams'])
    if not own:
        return league
    taken.update(t['slot'] for t in own)
    return dict(league, teams=list(league['teams']) + own)


def section_of(row):
    """The part of the update a change-log row belongs to ('' for rows made outside build())."""
    return row[5] if len(row) > 5 else ''
# steps that pass every check here but still wait for the owner's check in the game (docs/ROADMAP.md);
# the window no longer marks them and they are on by default like the rest (owner, 2026-10-04).
# Liiga and Extraliga were confirmed in the game on 2026-10-03.
# 'stock' is starting from the game's own roster (stock.py), 'positions' NHL.com's positions and wing
# sides on the lines, 'favourite logos' the reflection logos (art/install.REFLECTION), all new in 0.6.0.
# New in 0.8.0: 'free agents' (retired ones go, unsigned NHL players come), 'goalie gear' (painted in
# the new club's colours), 'draft' (real draft data), 'own teams' (a player's own team named after a
# club the game has no slot for gets its players). The calendar left this list on 2026-10-06: the owner played it.
EXPERIMENTAL = {'shl', 'del', 'nl', 'norway', 'ahl', 'chl', 'stock', 'positions', 'favourite logos',
                'free agents', 'goalie gear', 'draft', 'own teams'}
ALL_STEPS = CORE_STEPS      # what build() and update() run when no steps are given


def steps_for(pack):
    """The steps this data pack can serve, in running order."""
    return list(CORE_STEPS) + [k for k in LEAGUE_ORDER if k in pack.get('leagues', {})] + (
        [SCHEDULE] if pack.get('schedule') else [])


def default_steps(pack):
    """What is switched on unless the user chooses: everything the pack serves."""
    return steps_for(pack)


def planned(pack):
    """Names of the leagues the game has that cannot be updated with this data pack."""
    return [LEAGUE_NAMES[k] for k in LEAGUE_ORDER if k not in pack.get('leagues', {})]


def left_out_note(pack, step):
    """A short line naming a league's clubs the game has no team slot for (None when all fit)."""
    clubs = (pack.get('leagues', {}).get(step) or {}).get('left_out') or []
    if not clubs:
        return None
    if len(clubs) <= 3:
        return "No slot in the game for " + ", ".join(clubs)
    return f"The game has slots for only some clubs: {len(clubs)} are left out"


class BuildResult:
    def __init__(self, data, log, problems, info, builder):
        self.data = data            # bytes of the new SYS-DATA
        self.log = log              # [[team, change, player, detail, number]]
        self.problems = problems    # integrity problems; the save must not be installed if any
        self.info = info
        self.builder = builder

    @property
    def ok(self):
        return not self.problems

    def _counts(self):
        return Counter(r[1] for r in self.log if section_of(r) in (SECTION_NHL, SECTION_NATIONAL))

    def lines(self):
        """What each part of the update did, one (title, text) per part, for the window and the
        list of changes: ('NHL', '124 changed teams, 201 joined, 127 left')."""
        c = self._counts()
        out = []
        if c['moved'] or c['added'] or c['left NHL roster'] or c['created']:
            joined = f"{c['added'] + c['created']} joined" + (f" ({c['created']} new)" if c['created'] else "")
            out.append((SECTION_NHL, f"{c['moved']} traded, {joined}, {c['left NHL roster']} left"))
        if getattr(self.builder, 'positions_changed', 0):
            out.append(("Positions", f"{self.builder.positions_changed} NHL players moved to NHL.com's position"))
        retired, signable, new = self.free_agent_counts()
        if retired or signable:
            out.append((SECTION_FREE_AGENTS, f"{retired} retired, {signable} unsigned NHL "
                        f"player{'s' if signable != 1 else ''} added" + (f" ({new} new)" if new else "")))
        stats = getattr(self.builder, 'rating_stats', None)
        if stats:
            out.append((SECTION_RATINGS, f"{stats.get('players rated', 0)} players rated"))
        if c['national team: added'] or c['national team: removed']:
            text = f"{c['national team: added']} players added"
            if c['national team: removed']:
                text += f", {c['national team: removed']} removed"
            out.append((SECTION_NATIONAL, text))
        empty = [r[2] for r in self.log if r[1] == 'national team: left empty']
        if empty:
            out.append(("Left empty", f"{', '.join(empty)} (not enough players of that country)"))
        for key, s in self.builder.league_stats.items():
            placed = s.get('moved', 0) + s.get('added', 0) + s.get('created', 0)
            if not placed and not s.get('left'):
                out.append((LEAGUE_NAMES[key], "already up to date"))
                continue
            text = f"{placed} placed" + (f" ({s['created']} new)" if s.get('created') else "")
            if s.get('left'):
                text += f", {s['left']} left"
            if s.get('skipped: no free record'):
                text += f", {s['skipped: no free record']} skipped (no room)"
            out.append((LEAGUE_NAMES[key], text))
        if getattr(self.builder, 'pool_released', 0):
            out.append((SECTION_POOLS, f"{self.builder.pool_released} without room, now free agents"))
        for club, team in getattr(self.builder, 'own_teams', ()):
            out.append(("Your own team", f"{team} got {club}'s players"))
        edited = sum(1 for r in self.log if r[1] in ('edited', 'team edited', 'created') and section_of(r) == SECTION_EDITS)
        if edited:
            out.append((SECTION_EDITS, f"{edited} of your changes applied"))
        data = [f"{n} {what}" for n, what in ((getattr(self.builder, 'drafted', 0), "real drafts"),
                                               (getattr(self.builder, 'gear_painted', 0), "goalies' gear repainted"))
                if n]
        if data:
            out.append((SECTION_PLAYER_DATA, ", ".join(data)))
        cal = getattr(self.builder, 'calendar', None)
        if cal:
            out.append(("Calendar", f"{cal['games']} games, {cal['first']} to {cal['last']} ({cal['variant']})"))
        return out

    def free_agent_counts(self):
        """(players who retired, unsigned NHL players made free agents, of them new to the game)."""
        retired = sum(1 for r in self.log if r[1] == 'free agent retired'
                      or (r[1] in ('left NHL roster', 'left the club') and r[3] == 'retired'))
        added = [r for r in self.log if r[1] == 'free agent added']
        return retired, len(added), sum(1 for r in added if 'new to the game' in str(r[3]))

    def headline(self):
        """The size of each step's work on one line (the sentences are in summary())."""
        return "   |   ".join(f"{title}: {text}" for title, text in self.lines()) or "Nothing needed changing."

    def summary(self):
        """A few plain sentences about what changed."""
        c = self._counts()
        lines = []
        if c['moved'] or c['added'] or c['left NHL roster'] or c['created']:
            lines.append(f"NHL: {c['moved']} players changed teams, {c['added']} joined an NHL roster, "
                         f"{c['left NHL roster']} left, {c['created']} new players created.")
        stats = getattr(self.builder, 'rating_stats', None)
        if getattr(self.builder, 'positions_changed', 0):
            lines.append(f"Positions: {self.builder.positions_changed} NHL players now play the position NHL.com lists.")
        if stats:
            lines.append(f"Ratings: {stats.get('players rated', 0)} players updated.")
        for key, s in self.builder.league_stats.items():
            moved = s.get('moved', 0) + s.get('added', 0)
            if not moved and not s.get('created') and not s.get('left'):
                lines.append(f"{LEAGUE_NAMES[key]}: the clubs were already up to date.")
                continue
            text = (f"{LEAGUE_NAMES[key]}: {moved + s.get('created', 0)} players placed on their clubs "
                    f"({s.get('created', 0)} of them new to the game)")
            if s.get('left'):
                text += f", {s['left']} left"
            if s.get('pool players moved'):
                text += f"; {s['pool players moved']} prospect-pool players moved to custom teams"
            if s.get('skipped: no free record'):
                text += f"; {s['skipped: no free record']} skipped, no free player record left"
            lines.append(text + ".")
        if getattr(self.builder, 'pool_released', 0):
            lines.append(f"Prospect pools: no room left for {self.builder.pool_released} players; "
                         "they are free agents now and can be signed.")
        if c['national team: added'] or c['national team: removed']:
            lines.append(f"National teams: {c['national team: added']} players added, {c['national team: removed']} removed.")
        empty = [r[2] for r in self.log if r[1] == 'national team: left empty']
        if empty:
            lines.append(f"National teams left empty, not enough players of that country found: {', '.join(empty)}.")
        retired, signable, new = self.free_agent_counts()
        if retired or signable:
            lines.append(f"Free agents: {retired} players retired; {signable} NHL players without a contract can be "
                         f"signed ({new} of them new to the game).")
        if not lines:
            lines.append("Nothing needed changing.")
        return lines


def build(source, data, steps=ALL_STEPS, progress=None, check=True, art_registry=None, my_edits=None,
          team_edits=None):
    """Build an updated roster from `source` (path or bytes of a SYS-DATA).

    `data` is a builder.Data; `steps` the steps to run (see steps_for()). `my_edits` and
    `team_edits` are the player's own edits of players and teams (edits.py), applied last. With `art_registry` (an art.portraits.Registry:
    photos and logos are on) the placed players get portrait ids and the result's `art` lists the
    pictures to install."""
    say = progress or (lambda msg: None)
    steps = set(steps)
    if isinstance(source, (bytes, bytearray)):
        src_bytes = bytes(source)
    else:
        with open(source, 'rb') as f:
            src_bytes = f.read()
    R = Roster(src_bytes)
    kind = L.check_base(R)
    prepared = []
    if kind == L.STOCK:                 # the game's own roster: made updatable first (stock.py)
        prepared = stock.prepare(R, data.season_year)
        if prepared:
            say("The game's own roster: making room for today's players")
    if my_edits:
        from . import edits
        edits.restore(R, my_edits)      # renamed players carry their real names through the update
        R.reindex()
    gone = drop_removed_player(R)       # a player the game's own save left behind (Season mode crashed on him)
    if gone:
        say(f"Taking off {gone}, whom the game had already removed")
    drafts = draft.Drafts(data.drafts, data.season_year, stale=kind == L.COMMUNITY)
    drafted = draft.apply(R, drafts, data.season_year)     # before the builder looks at anyone's age
    b = Builder(R, data, progress=say, layout=kind)
    if getattr(R, 'stale_markers', False):      # a roster made by 0.8.0 from the community roster (see builder)
        say(f"Giving the {b.relink_free_agents()} free agents new links")
    if prepared:
        b.maintain = False              # its national teams are 2014's: brought up to date like a first run
    log = b.log                         # each change is tagged with the part of the update it belongs to
    log.section = SECTION_STOCK
    for what, detail in prepared:
        log.append(['ALL', 'summary', what, detail, ''])
    if kind == L.STOCK and b.nhl_identity():
        log.append(['ALL', 'summary', "arenas and colours of Utah, Seattle and Vegas", 3, ''])
    # the club leagues as they will be built (with the player's own teams named after left-out clubs):
    # their players' records are reserved from the start
    leagues = [key for key in LEAGUE_ORDER if key in steps and key in data.leagues]
    taken = set(L.MIRROR_OF) if b.mirrors else set()
    league_data = {key: with_own_teams(R, usable_clubs(R, data.leagues[key]), taken, set(L.MIRROR_OF) if b.mirrors else ())
                   for key in leagues}
    own = [(t['full'], R.team_name(t['slot'])) for key in leagues for t in league_data[key]['teams'] if t.get('own')]
    for club, team in own:
        log.append(['ALL', 'summary', f"your own team {team}", f"gets {club}'s players", ''])
    b.reserve_listed(league_data)
    b.league_keys = set(leagues)        # where undrafted prospects can go (clubs._place_prospects)
    # the game's own roster, first update: its 2014 national teams are filled again from scratch (the NHL
    # step empties them once it knows NHL.com's players)
    b.rebuild_national = bool(prepared) and NATIONAL in steps
    if b.rebuild_national and NHL not in steps:
        b.clear_national()
    rebuilt = set()
    if NHL in steps:
        log.section = SECTION_NHL
        say("NHL: moving players to their teams")
        b.nhl_rosters()
    if RATINGS in steps:
        log.section = SECTION_RATINGS
        say("Ratings: writing player attributes")
        b.apply_ea_ratings()
        b.donors.refresh()              # ratings move players across the legend line of spare records
    if NHL in steps:
        log.section = SECTION_NHL
        say("NHL: lines and mirror teams")
        b.nhl_lines()
        b.sync_mirrors()
    if NATIONAL in steps:
        # before the club leagues: new national players need spare records, and the junior
        # leagues, last in line, are the ones cut short if records run out
        log.section = SECTION_NATIONAL
        say("Filling the empty national teams")
        b.fill_empty_national()
    if leagues:                         # old players the leagues no longer list retire first
        log.section = SECTION_FREE_AGENTS
        say("Retiring the old players the leagues no longer list")
        stock.retire_leftovers(b, league_data)
    # player records are scarce: every league's clubs get a dressable 20 before any league's depth
    needs = {key: clubs.core_needs(b, league_data[key]) for key in leagues}
    for k, key in enumerate(leagues):
        b.core_reserve = sum((needs[x] for x in leagues[k + 1:]), Counter())
        log.section = LEAGUE_NAMES[key]
        say(f"{LEAGUE_NAMES[key]}: building the clubs")
        rebuilt |= clubs.update_league(b, key, league_data[key], say)
    if leagues:
        log.section = SECTION_POOLS
        b.pool_released = pools.settle(b, say)
        b.former_photos()               # last season's photos for players no list gave one
    if NATIONAL in steps:
        log.section = SECTION_NATIONAL
        say("National teams")
        b.national_teams()
        b.national_lines()
    log.section = SECTION_EDITS
    if my_edits:
        from . import edits
        say("My edits: applying your own changes")
        edits.apply(b, my_edits, say)
    if team_edits:
        from . import edits
        edits.apply_teams(b, team_edits, say)
    log.section = SECTION_PLAYER_DATA
    b.goalie_gear()
    log.section = SECTION_CONTRACTS
    b.contracts()
    log.section = SECTION_PLAYER_DATA
    # the real draft for everyone (again: players made or renamed in this run)
    drafted += draft.apply(R, drafts, data.season_year)
    if drafted:
        log.append(['ALL', 'summary', 'players given their real draft (year, round, pick, team)', drafted, ''])
    b.drafted = drafted
    b.own_teams = own
    b.calendar = None
    if SCHEDULE in steps and data.schedule:
        say("Calendar: writing the season's games")
        b.calendar = schedule.apply(R, data.schedule, data.calendar or schedule.THIRTY)
    b.finish()
    art = None
    if art_registry is not None:
        from .art import portraits
        say("Photos and logos: choosing the pictures")
        art = portraits.plan(b, art_registry)
    say("Packing the save")
    out = R.f.build()
    problems, info = [], {}
    if check:
        say("Checking the new roster")
        problems, info = verify(out, Roster(src_bytes), data.nhl_players if NHL in steps else None, rebuilt,
                                edited=getattr(b, 'edited', None), calendar=b.calendar)
    result = BuildResult(out, sorted(b.log, key=lambda r: (str(r[0]), str(r[1]), str(r[2]))), problems, info, b)
    result.art = art            # ({portrait id: photo link}, {team art id: (logo link, colours)}, team names) or None
    return result


class UpdateResult:
    def __init__(self, build_result, slot, report_path, name, art=None, slots=None, in_place=False, backup=None,
                 unchanged=False, exported=None):
        self.exported = exported        # the SYS-DATA file written by export_sysdata (no save, no RPCS3)
        self.in_place = in_place        # the roster save was updated, not a new one made
        self.backup = backup            # the folder with the old roster's files (in place)
        self.unchanged = unchanged      # in place, and the roster already was this
        self.build = build_result
        self.slot = slot                # the new savedata.Slot, None on a dry run or a failed check
        self.slots = slots if slots is not None else ([slot] if slot else [])   # one per version saved for
        self.report_path = report_path
        self.name = name
        self.art = art                  # (pictures installed, already there, failed), a message, or None

    def saved_where(self):
        """'BLES021530210 (EU) and BLUS315400200 (NA)': the new folders, for the player."""
        if self.exported:
            return self.exported
        if self.in_place:
            return f"{self.slot.folder} ({self.slot.region}), updated in place"
        return " and ".join(f"{s.folder} ({s.region})" for s in self.slots)

    def art_line(self):
        """One sentence about photos and logos (None when they were off)."""
        if self.art is None:
            return None
        if isinstance(self.art, str):
            return "Photos and logos were not installed: " + self.art
        written, already, failed = self.art
        text = f"Photos and logos: {written} pictures installed"
        if already:
            text += f", {already} were installed already"
        if failed:
            text += f", {failed} could not be downloaded (those players keep their old picture or none)"
        return text + "."


def write_report(result, title, heading=None, leagues=None):
    """The list of changes: a page to read (HTML, grouped by part and team; its path is returned)
    and the same rows as a table next to it (CSV, for a spreadsheet)."""
    from . import report
    path = datasource.app_dir('reports', f"{title}.csv")
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['team', 'change', 'player', 'detail', 'number', 'part'])
        w.writerows(result.log)
    page = path[:-4] + '.html'
    with open(page, 'w', encoding='utf-8') as f:
        f.write(report.html(result, heading or title, leagues or {}, csv_name=title + '.csv'))
    return page


def update(save_folder, source_folder=None, steps=ALL_STEPS, name=None, progress=None,
           offline=False, dry_run=False, data=None, art_rpcs3=None, art_registry=None, my_edits=None,
           team_edits=None, targets=None, disc=None, in_place=False, backup_root=None):
    """The whole job: read the chosen roster save, gather data, build, check, write a new save.

    `save_folder`: anything savedata.find_savedata() accepts. `source_folder`: the roster save to
    start from (folder name); default is the one pointed at, else the newest.
    `targets`: the versions of the game to save the new roster for (title ids, see
    savedata.GAMES); default the source's own. One new save folder each.
    `art_rpcs3` (a savedata.Rpcs3) switches photos and logos on: they are installed into that
    RPCS3's game folders (one per target) after the new roster is saved (RPCS3 must be closed).
    `disc` (a savedata.DiscSlot) starts from the game's own roster on the player's disc instead of a
    roster save; `save_folder` is then the save folder itself (it may not exist yet).
    `in_place` updates the chosen roster save itself instead of making a new one (savedata.update_in_place:
    after a backup copy in `backup_root`, default the program's backups folder; only the source's own
    version, never the game's own roster; RPCS3 must be closed); `name` then renames it, no name keeps it.
    Nothing is written when the integrity check finds a problem or `dry_run` is set."""
    say = progress or (lambda msg: None)
    if in_place and disc is not None:
        raise savedata.InPlaceError("The game's own roster cannot be updated in place: save it as a new roster.")
    if disc is not None:
        folder, source = os.path.abspath(save_folder), disc
    else:
        folder, preselected = savedata.find_savedata(save_folder)
        slots = savedata.list_rosters(folder)
        wanted = source_folder or preselected
        source = next((s for s in slots if s.folder == wanted), None) if wanted else slots[0]
        if source is None:
            raise FileNotFoundError(f"roster save {wanted} was not found in {folder}")
    targets = sorted(set(targets or [source.title_id]), key=lambda t: (t != source.title_id, t))
    if in_place and targets != [source.title_id]:
        raise savedata.InPlaceError("A roster is updated in place in its own version of the game only: "
                                    "save a new roster for the other version.")
    if in_place and not dry_run and savedata.running_rpcs3():
        raise savedata.InPlaceError("Close RPCS3 first: a roster can only be updated while the game is closed.")
    if dry_run:
        art_rpcs3 = None
    art_title = None
    if art_rpcs3 is not None:           # say what stands in the way before anything is built
        from .art import install, portraits
        # the pictures are made from the disc of a version RPCS3 knows; the other version gets copies
        art_title = next((t for t in targets if art_rpcs3.game_disc(t)), targets[0])
        install.check(art_rpcs3, art_title)
        art_registry = art_registry or portraits.Registry()
    say(f"Starting from \"{source.name}\" ({source.folder})")
    src_bytes = savedata.read_roster(source)
    if data is None:
        pack = datasource.load_pack(say, offline)
        R = Roster(src_bytes)
        L.check_base(R)
        data = datasource.gather(R, set(steps), pack, say, offline)
    result = build(src_bytes, data, steps, say, art_registry=art_registry if art_rpcs3 is not None else None,
                   my_edits=my_edits, team_edits=team_edits)
    asked_name = name
    name = savedata.clean_name(name or (source.name if in_place else savedata.default_name()))
    stamp = f"{datetime.datetime.now():%Y%m%d-%H%M%S}"
    heading = f"\"{name}\", made from \"{source.name}\""
    def report_as(title):
        return write_report(result, title, heading, data.leagues)
    if not result.ok:
        report = report_as(f"failed_{stamp}")
        say(f"The new roster did not pass {len(result.problems)} integrity checks, so nothing was saved.")
        return UpdateResult(result, None, report, name)
    if dry_run:
        return UpdateResult(result, None, report_as(f"dryrun_{stamp}"), name)
    saved, backup, unchanged = [], None, False
    if in_place:
        slot, backup, changed = savedata.update_in_place(
            folder, source, result.data, asked_name, expected=src_bytes,
            backup_root=backup_root or datasource.app_dir('backups'))
        saved, unchanged = [slot], not changed
        say("Already up to date: the roster is the same as the new one" if unchanged else
            f"Updated \"{slot.name}\" in place ({slot.folder}, {slot.region})")
    else:
        for title_id in targets:
            slot = savedata.install(folder, source, result.data, name, title_id=title_id)
            saved.append(slot)
            say(f"Saved as \"{slot.name}\" in {slot.folder} ({slot.region})")
    title = f"{saved[0].folder}_{stamp}"
    report = report_as(title)
    art = None
    if result.art is not None and art_rpcs3 is not None:
        art_registry.save()             # the new roster uses these ids now
        portraits_, logos, names = result.art
        skipped = []
        try:
            install_looks(result, art_rpcs3, art_title, targets, say)
            art = install.install(art_rpcs3, art_title, portraits_, logos, say, names=names,
                                  also=[t for t in targets if t != art_title], skipped=skipped)
        except install.ArtError as err:  # the roster is saved; only the pictures are missing
            say(str(err))
            art = str(err)
        if skipped:                     # in the list of changes, by name: a player can tell us who
            note_skipped(result, skipped)
            report = report_as(title)
    return UpdateResult(result, saved[0], report, name, art, slots=saved, in_place=in_place, backup=backup,
                        unchanged=unchanged)


def install_looks(result, rpcs3, title, targets, say):
    """The new jerseys, pants, socks, menu pictures and centre-ice logos of Utah, Seattle and Vegas (art/looks.py), made from
    the player's own disc, with the photos and logos. A logo that cannot be had leaves the jerseys out, the rest goes on."""
    from .art import looks
    from .art.photopack import PhotoPack, PictureCache
    b = result.builder
    nhl_logos = getattr(b.data, 'nhl_logos', None)
    try:
        nhl_logos = nhl_logos or datasource.load_pack(offline=True).get('nhl_logos') or {}
        made = looks.looks_from(Roster(result.data), dict(getattr(b, 'looks_edits', {})), dict(b.logos), nhl_logos,
                                PhotoPack.open(), PictureCache())
    except Exception as err:
        say(f"Jerseys and ice: left out ({err})")
        return
    if made:
        looks.install_looks(rpcs3, title, made, say, also=[t for t in targets if t != title])


ExportSlot = collections.namedtuple('ExportSlot', 'name folder region')


def export_root():
    """The folder an exported SYS-DATA goes to: next to the program (the exe; run from source, the current folder).
    When that folder cannot be written to (a program folder), the player's Documents folder."""
    base = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, 'frozen', False) else os.getcwd()
    try:
        probe = os.path.join(base, '.write-test')
        with open(probe, 'w'):
            pass
        os.remove(probe)
        return base
    except OSError:
        docs = os.path.join(os.path.expanduser('~'), 'Documents')
        return docs if os.path.isdir(docs) else os.path.expanduser('~')


def export_sysdata(source_file, steps=ALL_STEPS, name=None, progress=None, offline=False, my_edits=None, team_edits=None,
                   data=None, out_root=None):
    """Update a roster file (a community roster's SYS-DATA) and write the new SYS-DATA into a new folder next to the program,
    without RPCS3 and without any save folder: for a PC that cannot run RPCS3 (a Mac, a Linux box). The new file is checked
    like every roster; nothing is written when a check fails. No photos, logos or jerseys (they are RPCS3's files), no
    start from the game's own roster (that needs the disc). Returns an UpdateResult whose `exported` is the new file."""
    say = progress or (lambda msg: None)
    if not os.path.isfile(source_file):
        raise FileNotFoundError("The roster file was not found.")
    with open(source_file, 'rb') as f:
        src_bytes = f.read()
    R = Roster(src_bytes)
    L.check_base(R)
    from . import stock
    if stock.is_stock(R):
        raise L.LayoutError("This is the game's own roster, which is started from your game disc. Pick the community "
                            "roster's SYS-DATA instead.")
    say(f"Starting from \"{os.path.basename(os.path.dirname(os.path.abspath(source_file))) or 'SYS-DATA'}\" (SYS-DATA file)")
    if data is None:
        pack = datasource.load_pack(say, offline)
        data = datasource.gather(R, set(steps), pack, say, offline)
    result = build(src_bytes, data, steps, say, my_edits=my_edits, team_edits=team_edits)
    name = savedata.clean_name(name or savedata.default_name())
    stamp = f"{datetime.datetime.now():%Y%m%d-%H%M%S}"
    heading = f"\"{name}\", made from the roster file {os.path.basename(source_file)}"
    if not result.ok:
        say(f"The new roster did not pass {len(result.problems)} integrity checks, so nothing was saved.")
        return UpdateResult(result, None, write_report(result, f"failed_{stamp}", heading, data.leagues), name)
    root = out_root or export_root()
    folder = os.path.join(root, f"NHL Legacy roster {datetime.datetime.now():%Y-%m-%d %H%M}")
    n = 1
    while os.path.exists(folder):
        n += 1
        folder = os.path.join(root, f"NHL Legacy roster {datetime.datetime.now():%Y-%m-%d %H%M} ({n})")
    os.makedirs(folder)
    target = os.path.join(folder, 'SYS-DATA')
    with open(target + '.tmp', 'wb') as f:
        f.write(result.data)
    os.replace(target + '.tmp', target)
    say(f"Exported SYS-DATA to {target}")
    report = write_report(result, f"export_{stamp}", heading, data.leagues)
    return UpdateResult(result, ExportSlot(name, folder, ''), report, name, exported=target)


def note_skipped(result, skipped):
    """Rows in the list of changes for the pictures that could not be made, with the players' or
    clubs' names."""
    b = result.builder
    R = Roster(result.data)
    who = {}
    for prow, url in b.photos.items():
        who.setdefault(url, []).append(R.name(prow))
    for slot, url in b.logos.items():
        who.setdefault(url, []).append(R.team_name(slot))
    for what, url, why in sorted(skipped):
        for name in sorted(who.get(url, [url])):
            result.log.append(['', f"{what} not installed", name, why, '', SECTION_PICTURES])
