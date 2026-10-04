"""One entry point for building an updated roster: used by the GUI, the CLI and the tests."""
import csv
import datetime
from collections import Counter

from . import datasource, savedata
from . import layout as L
from .builder import Builder
from .leagues import clubs, pools
from .roster import Roster
from .verify import verify

# what the user can tick; steps run in this order whatever order they are given in
NHL, RATINGS, NATIONAL = 'nhl', 'ratings', 'national'
CORE_STEPS = (NHL, RATINGS, NATIONAL)
# club leagues, available when the data pack has rosters for them
LEAGUE_ORDER = ('liiga', 'extraliga', 'shl', 'del', 'nl', 'norway', 'ahl', 'chl')
STEP_LABELS = {NHL: "NHL rosters, numbers, lines and captains",
               RATINGS: "Player ratings",
               NATIONAL: "National teams",
               'liiga': "Liiga: real clubs", 'extraliga': "Extraliga: real clubs", 'shl': "SHL: real clubs",
               'del': "DEL: real clubs", 'nl': "National League: real clubs", 'norway': "Norway: real clubs",
               'ahl': "AHL rosters", 'chl': "CHL (OHL / QMJHL / WHL)"}
LEAGUE_NAMES = {'liiga': "Liiga", 'extraliga': "Extraliga", 'shl': "SHL", 'del': "DEL", 'nl': "National League",
                'norway': "Norway", 'ahl': "AHL", 'chl': "CHL (OHL / QMJHL / WHL)"}
# steps that pass every check here but have not been confirmed in the game yet: off unless ticked
# (Liiga and Extraliga were confirmed in the game on 2026-10-03)
EXPERIMENTAL = {'shl', 'del', 'nl', 'norway', 'ahl', 'chl'}
ALL_STEPS = CORE_STEPS      # the default selection


def steps_for(pack):
    """The steps this data pack can serve, in running order."""
    return list(CORE_STEPS) + [k for k in LEAGUE_ORDER if k in pack.get('leagues', {})]


def default_steps(pack):
    """What is switched on unless the user chooses: everything the pack serves that is not new."""
    return [s for s in steps_for(pack) if s not in EXPERIMENTAL]


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
        return Counter(r[1] for r in self.log if r[0] in L.API_TO_SLOT or str(r[1]).startswith('national'))

    def headline(self):
        """The size of each step's work on one line (the sentences are in summary())."""
        c = self._counts()
        parts = []
        if c['moved'] or c['added'] or c['left NHL roster'] or c['created']:
            parts.append(f"NHL: {c['moved']} moved, {c['added'] + c['created']} joined, {c['left NHL roster']} left")
        stats = getattr(self.builder, 'rating_stats', None)
        if stats:
            parts.append(f"Ratings: {stats.get('players rated', 0)} players")
        for key, s in self.builder.league_stats.items():
            placed = s.get('moved', 0) + s.get('added', 0) + s.get('created', 0)
            parts.append(f"{LEAGUE_NAMES[key]}: {placed} players placed" if placed or s.get('left')
                         else f"{LEAGUE_NAMES[key]}: up to date")
        if c['national team: added'] or c['national team: removed']:
            parts.append(f"National teams: {c['national team: added']} added")
        return "   |   ".join(parts) or "Nothing needed changing."

    def summary(self):
        """A few plain sentences about what changed."""
        c = self._counts()
        lines = []
        if c['moved'] or c['added'] or c['left NHL roster'] or c['created']:
            lines.append(f"NHL: {c['moved']} players changed teams, {c['added']} joined an NHL roster, "
                         f"{c['left NHL roster']} left, {c['created']} new players created.")
        stats = getattr(self.builder, 'rating_stats', None)
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
        if not lines:
            lines.append("Nothing needed changing.")
        return lines


def build(source, data, steps=ALL_STEPS, progress=None, check=True, art_registry=None, my_edits=None):
    """Build an updated roster from `source` (path or bytes of a SYS-DATA).

    `data` is a builder.Data; `steps` the steps to run (see steps_for()). `my_edits` are the
    player's own edits (edits.py), applied last. With `art_registry` (an art.portraits.Registry:
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
    L.check_base(R)
    if my_edits:
        from . import edits
        edits.restore(R, my_edits)      # renamed players carry their real names through the update
        R.reindex()
    b = Builder(R, data, progress=say)
    rebuilt = set()
    if NHL in steps:
        say("NHL: moving players to their teams")
        b.nhl_rosters()
    if RATINGS in steps:
        say("Ratings: writing player attributes")
        b.apply_ea_ratings()
    if NHL in steps:
        say("NHL: lines and mirror teams")
        b.nhl_lines()
        b.sync_mirrors()
    if NATIONAL in steps:
        # before the club leagues: new national players need spare records, and the junior
        # leagues, last in line, are the ones cut short if records run out
        say("Filling the empty national teams")
        b.fill_empty_national()
    leagues = [key for key in LEAGUE_ORDER if key in steps and key in data.leagues]
    # player records are scarce: every league's clubs get a dressable 20 before any league's depth
    needs = {key: clubs.core_needs(b, data.leagues[key]) for key in leagues}
    for k, key in enumerate(leagues):
        b.core_reserve = sum((needs[x] for x in leagues[k + 1:]), Counter())
        say(f"{LEAGUE_NAMES[key]}: building the clubs")
        rebuilt |= clubs.update_league(b, key, data.leagues[key], say)
    if leagues:
        b.pool_released = pools.settle(b, say)
    if NATIONAL in steps:
        say("National teams")
        b.national_teams()
        b.national_lines()
    if my_edits:
        from . import edits
        say("My edits: applying your own changes")
        edits.apply(b, my_edits, say)
    b.contracts()
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
                                edited=getattr(b, 'edited', None))
    result = BuildResult(out, sorted(b.log, key=lambda r: (str(r[0]), str(r[1]), str(r[2]))), problems, info, b)
    result.art = art            # ({portrait id: photo link}, {team art id: (logo link, colours)}) or None
    return result


class UpdateResult:
    def __init__(self, build_result, slot, report_path, name, art=None):
        self.build = build_result
        self.slot = slot                # the new savedata.Slot, None on a dry run or a failed check
        self.report_path = report_path
        self.name = name
        self.art = art                  # (pictures installed, already there, failed), a message, or None

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


def write_report(result, title):
    path = datasource.app_dir('reports', f"{title}.csv")
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['team', 'change', 'player', 'detail', 'number'])
        w.writerows(result.log)
    return path


def update(save_folder, source_folder=None, steps=ALL_STEPS, name=None, progress=None,
           offline=False, dry_run=False, data=None, art_rpcs3=None, art_registry=None, my_edits=None):
    """The whole job: read the chosen roster save, gather data, build, check, write a new save.

    `save_folder`: anything savedata.find_savedata() accepts. `source_folder`: the roster save to
    start from (folder name); default is the one pointed at, else the newest.
    `art_rpcs3` (a savedata.Rpcs3) switches photos and logos on: they are installed into that
    RPCS3's game folder after the new roster is saved (RPCS3 must be closed).
    Nothing is written when the integrity check finds a problem or `dry_run` is set."""
    say = progress or (lambda msg: None)
    folder, preselected = savedata.find_savedata(save_folder)
    slots = savedata.list_rosters(folder)
    wanted = source_folder or preselected
    source = next((s for s in slots if s.folder == wanted), None) if wanted else slots[0]
    if source is None:
        raise FileNotFoundError(f"roster save {wanted} was not found in {folder}")
    if dry_run:
        art_rpcs3 = None
    if art_rpcs3 is not None:           # say what stands in the way before anything is built
        from .art import install, portraits
        install.check(art_rpcs3, source.title_id)
        art_registry = art_registry or portraits.Registry()
    say(f"Starting from \"{source.name}\" ({source.folder})")
    with open(source.sys_data, 'rb') as f:
        src_bytes = f.read()
    if data is None:
        pack = datasource.load_pack(say, offline)
        R = Roster(src_bytes)
        L.check_base(R)
        data = datasource.gather(R, set(steps), pack, say, offline)
    result = build(src_bytes, data, steps, say, art_registry=art_registry if art_rpcs3 is not None else None,
                   my_edits=my_edits)
    name = savedata.clean_name(name or savedata.default_name())
    stamp = f"{datetime.datetime.now():%Y%m%d-%H%M%S}"
    if not result.ok:
        report = write_report(result, f"failed_{stamp}")
        say(f"The new roster did not pass {len(result.problems)} integrity checks, so nothing was saved.")
        return UpdateResult(result, None, report, name)
    if dry_run:
        return UpdateResult(result, None, write_report(result, f"dryrun_{stamp}"), name)
    slot = savedata.install(folder, source, result.data, name)
    report = write_report(result, f"{slot.folder}_{stamp}")
    say(f"Saved as \"{slot.name}\" in {slot.folder}")
    art = None
    if result.art is not None and art_rpcs3 is not None:
        art_registry.save()             # the new roster uses these ids now
        portraits_, logos = result.art
        try:
            art = install.install(art_rpcs3, source.title_id, portraits_, logos, say)
        except install.ArtError as err:  # the roster is saved; only the pictures are missing
            say(str(err))
            art = str(err)
    return UpdateResult(result, slot, report, name, art)
