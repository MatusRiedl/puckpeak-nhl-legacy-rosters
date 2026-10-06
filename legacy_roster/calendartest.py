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
but nothing else is changed); nothing here writes a game file.
"""
from . import datasource, layout as L, savedata, schedule
from .builder import Data
from .pipeline import SCHEDULE, build
from .roster import Roster

YEAR_TABLE, YEAR_FIELD = 'vaHq', 'dnFq'      # exhibitiondraftpick.year (the roster's only years: 115-120 = 2015-2020)
YEARS_LATER = 11                              # 2015 -> 2026
RUNGS = (("CAL 1 thirty teams", schedule.THIRTY, 0), ("CAL 2 thirty + all-star", schedule.ALL_STAR, 0),
         ("CAL 3 all 32 teams 80 games", schedule.ALL, 0), ("CAL 4 thirty teams year +11", schedule.THIRTY, YEARS_LATER))
CHECKLIST = ("Season mode > Select Team > Anaheim > Calendar. Look at: the month and YEAR it names, the weekdays, "
             "whether September is there, Anaheim's games (below), then play a game or two, simulate a week, open the "
             "standings. Note what is the same as before and what is different. For CAL 3 also Season mode with 32 "
             "teams: do Seattle and Vegas appear in the team list and the standings?")


def _slot_name(R, slot):
    return R.team_name(slot) if slot < R.T.cur_rec else f"#{slot}"


def first_games(R, slot, n=8):
    """['4 Oct home vs Florida Panthers', ...]: the first `n` games of a team in the schedule the roster has."""
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    games = [(m, d, h, a) for m, d, h, a in schedule.read(R) if slot in (h, a)]
    games.sort(key=lambda g: ((g[0] - 8) % 12, g[1]))
    return [f"{d + 1} {months[m]} " + (f"home vs {_slot_name(R, a)}" if h == slot else f"at {_slot_name(R, h)}")
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
