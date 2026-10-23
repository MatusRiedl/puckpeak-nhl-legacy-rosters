"""The calendar test (cli `calendar-test`): LAB rosters with the real 2026-27 schedule, for the owner to look at in
the game's Season mode calendar (schedule.py, docs/ROADMAP.md "Calendar").

What it answers, in the game:
  * does Season mode read the schedule from the roster (the calendar shows the new games), and which table
  * how the calendar names the year (it says "October 2015"; the weekdays of October 2026 are the same) and
    whether September shows (the real season starts on 29 September)
  * whether the All-Star game between the two All-Star slots is needed or in the way
  * whether Season mode plays with 32 teams (Seattle and Vegas, all teams trimmed to 80 games)
  * whether the draft years in the roster (115-120) are what the calendar's year comes from (CAL 4: +11)

Every roster starts from the same roster as it is (no update step, so the Season-mode fixes of the update are in,
but nothing else is changed). Only the 32-team test writes game files: the database description and database as the
game patch does (patchinstall.write_db; "game-patch remove" undoes them) and, with --photos, the pictures and names the
way "Photos, logos and team names" does ("photos remove" undoes them).
"""
from . import datasource, gamepatch, layout as L, patchinstall, savedata, schedule
from .builder import Data
from .pipeline import SCHEDULE, build, patch_roster
from .roster import Roster
from .verify import _team

YEAR_TABLE, YEAR_FIELD = 'vaHq', 'dnFq'      # exhibitiondraftpick.year (the roster's only years: 115-120 = 2015-2020)
YEARS_LATER = 11                              # 2015 -> 2026
RUNGS = (("CAL 1 thirty teams", schedule.THIRTY, 0), ("CAL 2 thirty + all-star", schedule.ALL_STAR, 0),
         ("CAL 3 all 32 teams 80 games", schedule.ALL, 0), ("CAL 4 thirty teams year +11", schedule.THIRTY, YEARS_LATER))
CHECKLIST = ("Season mode > Select Team > Anaheim > Calendar. Look at: the month and YEAR it names, the weekdays, "
             "whether September is there, Anaheim's games (below), then play a game or two, simulate a week, open the "
             "standings. Note what is the same as before and what is different. For CAL 3 also Season mode with 32 "
             "teams: do Seattle and Vegas appear in the team list and the standings?")


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _slot_name(R, slot):
    return _team(R, slot) if slot < R.T.cur_rec else f"#{slot}"


def first_games(R, slot, n=8):
    """['4 Oct home vs Florida Panthers', ...]: the first `n` games of a team in the schedule the roster has."""
    games = [(m, d, h, a) for m, d, h, a in schedule.read(R) if slot in (h, a)]
    games.sort(key=lambda g: ((g[0] - 8) % 12, g[1]))
    return [f"{d + 1} {MONTHS[m]} " + (f"home vs {_slot_name(R, a)}" if h == slot else f"at {_slot_name(R, h)}")
            for m, d, h, a in games[:n]]


def calendar_test(folder, slot, say=print):
    """Save the rungs next to `slot` (a roster save) in the save folder `folder`; write calendar_test.txt into the
    program's reports folder. Returns the new saves."""
    raw = savedata.read_roster(slot)
    L.check_base(Roster(raw))
    pack = datasource.load_pack(offline=True)
    games = pack.get('schedule')
    if not games:
        raise RuntimeError("this program has no schedule in its data (tools/build_datapack.py --refresh schedule)")
    season = pack.get('season', 2026)
    lines = [f"Calendar test, from \"{slot.name}\" ({slot.folder}); schedule: {games[0][0]} to {games[-1][0]}, "
             f"{len(games)} games of NHL.com.", CHECKLIST, ""]
    saved = []
    for name, variant, years in RUNGS:
        say(f"{name}: building")
        result = build(raw, Data(season_year=season, schedule=games, calendar=variant), [SCHEDULE])
        data = result.data
        if years:
            R = Roster(data)
            T = R.f[YEAR_TABLE]
            for i in range(T.cur_rec):
                T.set(i, YEAR_FIELD, min(255, T.get(i, YEAR_FIELD) + years))
            data = R.f.build()
        new = savedata.install(folder, slot, data, name)
        saved.append(new)
        info = result.builder.calendar
        per = info['per_team']
        lines.append(f"{new.name} ({new.folder}): {info['games']} games, {info['first']} to {info['last']}, "
                     f"{min(per.values())}-{max(per.values())} games per team"
                     + (f"; the draft years are {years} later" if years else "")
                     + ("; checks: " + "; ".join(result.problems[:2]) if result.problems else ""))
        lines.append("    Anaheim: " + "; ".join(first_games(Roster(data), 0)))
    with open(datasource.app_dir('reports', 'calendar_test.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    for line in lines:
        say(line)
    return saved


_INTRO_LINE = ("   Optional, each on its own: \"" + gamepatch.INTRO_ENTRY + "\" (the game starts at Press Start) and \""
               + gamepatch.LOGIN_ENTRY + "\" (no online boxes at start; online modes still sign in when opened).")
YEAR_CHECKLIST = (
    "1. Close RPCS3's game. In RPCS3: Manage > Game Patches, drop the file " + "{patch}" + " on that window (or "
    "Import), tick \"" + gamepatch.YEAR_ENTRY + "\" under NHL Legacy, Save.",
    _INTRO_LINE,
    "2. Start the game, Customize > Save/Load/Delete > Load > Rosters: \"YEAR 2026\".",
    "3. Season mode > Select Team > Anaheim > Calendar: which month and YEAR does it name, are the weekdays right (the "
    "first game, Anaheim's, below)? Then a player's card: is the age right (below)? The draft (Be a GM): which year?",
    "4. Note anything that still says 2015, and anything odd (contracts, retirements after a simulated week).",
    "5. Afterwards untick the year entry again (the intro entries may stay): other rosters keep birth years for the "
    "game's own 2015.")


def year_test(folder, slot, say=print):
    """The year patch's in-game check: one LAB roster made for the patch ("YEAR 2026": the thirty-team 2026-27 calendar,
    birth years and draft picks the patched way) and the patch file in the program's reports folder. Returns the save."""
    raw = savedata.read_roster(slot)
    L.check_base(Roster(raw))
    pack = datasource.load_pack(offline=True)
    games = pack.get('schedule')
    if not games:
        raise RuntimeError("this program has no schedule in its data (tools/build_datapack.py --refresh schedule)")
    season = pack.get('season', 2026)
    result = build(raw, Data(season_year=season, schedule=games, calendar=schedule.THIRTY), [SCHEDULE])
    if result.problems:
        raise RuntimeError("the roster does not pass the checks: " + "; ".join(result.problems[:3]))
    R = Roster(result.data)
    gamepatch.year_shift(R, result.builder.stale_years)
    problems = gamepatch.check_years(R, season)
    if problems:
        raise RuntimeError("the years are not right: " + "; ".join(problems[:5]))
    data = R.f.build()
    patch = datasource.app_dir('reports', 'NHL_Legacy_year_2026_patch.yml')
    with open(patch, 'w', encoding='utf-8', newline='\n') as f:
        f.write(gamepatch.patch_text())
    new = savedata.install(folder, slot, data, "YEAR 2026")
    R = Roster(data)
    P = R.P
    ages = []
    for prow in range(P.cur_rec):
        if P.get(prow, 'RMbQ') in ('Crosby', 'Ovechkin', 'Bedard', 'Celebrini') and P.get(prow, 'NYKk'):
            ages.append(f"{P.get(prow, 'PedH')} {P.get(prow, 'RMbQ')} born {P.get(prow, 'dnFq') + 1900 + gamepatch.YEARS_LATER}")
    lines = [f"Year test, from \"{slot.name}\" ({slot.folder}): saved \"{new.name}\" ({new.folder}).",
             *[line.replace('{patch}', patch) for line in YEAR_CHECKLIST],
             "    Anaheim: " + "; ".join(first_games(R, 0, 3)),
             "    Players: " + "; ".join(ages)]
    with open(datasource.app_dir('reports', 'year_test.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    for line in lines:
        say(line)
    return new


TEAMS_NAME = "32 TEAMS 2026"
_LETTERS = [name.split(' - ')[0].rsplit(' ', 1)[1] for name, *_ in gamepatch.TEAM_STAGES]
TEAMS_CHECKLIST = (
    "1. Close RPCS3's game. In RPCS3: Manage > Game Patches, drop the file {patch} on that window (or Import). Under NHL "
    "Legacy tick \"" + gamepatch.YEAR_ENTRY + f"\" and the {len(_LETTERS)} \"NHL Legacy 32 teams\" entries "
    + ", ".join(_LETTERS[:-1]) + f" and {_LETTERS[-1]}, Save.",
    _INTRO_LINE,
    "2. Start the game. In RPCS3's log (File > Open log, or the Log window) find \"Applied patch\": every ticked entry "
    "is named with its number of changes; note any line that says a patch was not applied.",
    "3. Customize > Save/Load/Delete > Load > Rosters: \"" + TEAMS_NAME + "\".",
    "4. Start a NEW Season (one made before this roster and the game's database description keeps Vegas without "
    "players). Season mode > Select Team: are Seattle and Vegas there (\"User Teams 1/32\")? Pick Seattle. Calendar: Seattle's first "
    "games (below)? Standings: 32 NHL teams, Seattle and Vegas in the Pacific, Utah in the Central?",
    "5. Play or simulate one game, then simulate a week. Look at the standings and Seattle's farm team (Coachella "
    "Valley). AHL standings: 32 clubs in four divisions (the Pacific has 10)? Coachella Valley and Henderson with players?",
    "6. Be a GM: start one with Vegas. Does it start? Look at the roster, the farm team, the money screen.",
    "7. If the game stops or crashes: the step and screen, and the last lines of RPCS3's log. Then untick only entries "
    "C and N (keep the year, A, B and D) and try Season mode again: A, B and D alone should change nothing.",
    "8. Afterwards untick the year and the 32-team entries again (the intro entries may stay): other rosters are not "
    "made for them.")


def team32_test(folder, slot, say=print, art_rpcs3=None, rpcs3=None, title_id=None):
    """The 32-team patch's in-game check: one LAB roster made for the whole patch ("32 TEAMS 2026": the 32-team 2026-27
    calendar with all 84 games (its tables grown to hold them) and the All-Star game as a team against itself, the patched years, the farm league of
    entries L and M (32 AHL clubs, the AHL's own calendar), Utah in the Central and Seattle and Vegas in the Pacific,
    EASHL 1 / 2 as the Eastern / Western All-Stars) and the patch file with every entry in the program's reports folder. With `rpcs3` (a savedata.Rpcs3, closed) the game's database description and database made
    for 32 teams (gamepatch.fit_meta, fit_db, from that RPCS3's copy of the game; the database also holds this roster's
    calendars for the next seasons) go into its game folder as loose files ("game-patch remove" puts back what was there).
    With `art_rpcs3`
    (the same) the menus' team names, the NHL logos and the Utah / Seattle / Vegas jerseys go there too, as with "Photos,
    logos and team names" (without them Season shows Seattle and Vegas as the All-Star teams). "photos remove" puts back
    what was there. `title_id` (BLUS31540) saves for that version of the game instead of the source's. Returns the save."""
    registry = meta = db = None
    title = title_id or slot.title_id
    rpcs3 = rpcs3 or art_rpcs3
    if rpcs3 is not None:
        from .art import install
        install.check(rpcs3, title)
    if art_rpcs3 is not None:
        from .art import portraits
        registry = portraits.Registry()
    raw = savedata.read_roster(slot)
    source = Roster(raw)
    L.check_base(source)
    pack = datasource.load_pack(offline=True)
    games = pack.get('schedule')
    if not games:
        raise RuntimeError("this program has no schedule in its data (tools/build_datapack.py --refresh schedule)")
    season = pack.get('season', 2026)
    # the AHL step too: it gives the farm clubs' contract players their NHL team's rights (rights_fit makes sure; Vegas's
    # once patch_roster has given them six bits, gamepatch.rights_wide)
    result = build(raw, Data(season_year=season, schedule=games, calendar=schedule.ALL_PATCH, leagues=pack['leagues']),
                   [SCHEDULE, 'ahl'], art_registry=registry)
    if result.problems:
        raise RuntimeError("the roster does not pass the checks: " + "; ".join(result.problems[:3]))
    data, problems, farm_count = patch_roster(result, raw, pack, season)
    if problems:
        raise RuntimeError("the roster does not pass the checks: " + "; ".join(problems[:5]))
    if rpcs3 is not None:
        # the game's database with the same six bits, and this roster's next seasons' calendars for when another
        # roster (or none) is in the game's memory at the new year (gamepatch.NEXT_SEASON_TABLES)
        meta, db = patchinstall.db_files(rpcs3.game_disc(title), data)
    patch = datasource.app_dir('reports', 'NHL_Legacy_32_teams_patch.yml')
    with open(patch, 'w', encoding='utf-8', newline='\n') as f:
        f.write(gamepatch.patch_text(teams=True))
    new = savedata.install(folder, slot, data, TEAMS_NAME, title_id=title)
    if meta is not None:
        meta_path, db_path = patchinstall.write_db(rpcs3, [title], meta, db)
        say(f"The game's database description for 32 teams (Vegas's team numbers in six bits): {meta_path}")
        say(f"The game's database with the same six bits (the Season takes them from here) and this roster's "
            f"calendars for the next seasons: {db_path}")
    if art_rpcs3 is not None:
        _team32_art(result, data, pack, art_rpcs3, title, registry, say)
    R = Roster(data)
    info = result.builder.calendar
    per = info['per_team']
    lines = [f"32-team test, from \"{slot.name}\" ({slot.folder}): saved \"{new.name}\" ({new.folder}); "
             f"{info['games']} NHL games, {min(per.values())}-{max(per.values())} per team, patch {gamepatch.TEAMS_VERSION}.",
             *[line.replace('{patch}', patch) for line in TEAMS_CHECKLIST],
             "    Seattle: " + "; ".join(first_games(R, 30, 3)),
             "    Vegas: " + "; ".join(first_games(R, 31, 3)),
             "    All-Star game: " + "; ".join(f"{d + 1} {MONTHS[m]} ({_slot_name(R, gamepatch.ALL_STAR_SLOTS[0])} v "
                                               f"{_slot_name(R, gamepatch.ALL_STAR_SLOTS[1])})"
                                               for m, d, h, a in schedule.read(R) if h == a),
             f"    Farm league: 32 AHL clubs, {farm_count} games of the AHL's 2026-27 calendar; Seattle's farm team "
             f"{_slot_name(R, gamepatch.FARM_SLOTS[30])}, Vegas's {_slot_name(R, gamepatch.FARM_SLOTS[31])}.",
             "    " + "; ".join(f"{name}: " + ", ".join(_slot_name(R, s) for s in slots)
                              for _, _, name, slots in gamepatch.FARM_DIVISIONS)]
    with open(datasource.app_dir('reports', 'team32_test.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    for line in lines:
        say(line)
    return new


def _team32_art(result, data, pack, rpcs3, title, registry, say):
    """The pictures and names for the 32-team test roster: the names, the NHL logos (the calendar-only build draws none)
    and the new jerseys, installed as the update's "Photos, logos and team names" does (art/install.py keeps the game's
    own files for "photos remove")."""
    from .art import install
    from .pipeline import install_looks
    registry.save()
    portraits_, logos, names = result.art
    T = Roster(data).T
    for code, url in sorted((pack.get('nhl_logos') or {}).items()):
        slot = L.API_TO_SLOT.get(code)
        if slot is not None:
            colours = tuple(tuple(T.get(slot, f"{c}color_{x}") for x in 'rgb') for c in ('primary', 'secondary'))
            logos.setdefault(T.get(slot, 'artid'), (url, colours))
    install_looks(result, rpcs3, title, [title], say)
    install.install(rpcs3, title, portraits_, logos, say, names=names)
