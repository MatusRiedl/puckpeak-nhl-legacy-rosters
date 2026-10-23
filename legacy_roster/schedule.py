"""The game's calendar: the real schedule of a season written into the roster's schedule tables.

`nhlschedule` is the table Season mode's calendar reads (it matched the owner's screenshot row by
row) and `favoriteteamschedule` holds a copy of it; the others (`nhlfutureschedule`, the club leagues')
are left alone. A row is one game: `month` (0 = January), `day` (0-based), `index` (the row's own
number), `home` and `away` (team slots). There is no year and no time of day in a row; the year the
calendar shows is not in the roster (docs/FORMAT.md section 8, docs/ROADMAP.md "Calendar").

Three ways to fill it, because the game's tables hold 1,291 games and the real season has 1,344 (84
games for each of 32 teams), and because Seattle and Vegas sit in the two All-Star slots, 30 and 31:

    THIRTY      only games between the 30 slots that have always been teams (Seattle and Vegas left out;
                the teams play 76 to 80 games)
    ALL_STAR    the same plus an All-Star game (slot 30 against slot 31, in the break the real season has)
    ALL         all 32 teams, 80 games each (every team loses the same number of home and away games)
    ALL_PATCH   for the game patch: all 32 teams, all 84 games (the real season), and the All-Star game (gamepatch stage J):
                one row of a team against itself in the break (the patched calendar loader makes that row the All-Star
                game). Its tables grow to PATCH_ROWS, room the game has only with the patch's db/nhlng-meta.xml
                (gamepatch.META_ROWS)

None of this has been played in the game yet (pipeline.EXPERIMENTAL 'schedule'; `cli calendar-test`).

The club leagues have tables of their own (`LEAGUES`; Season mode plays each of them and reads its table, lab round
46). `apply_league` writes a league's real season there: only games between clubs the game has a slot for, a row's team
is its place in the league (slot - the league's first slot).
"""
import datetime

from . import layout as L

TABLE, FAVOURITE = 'ihmS', 'Iwiq'          # nhlschedule, favoriteteamschedule (the tags in the save)
ROW = {'round': 'XpWK', 'status': 'fdgg', 'day': 'iwsK', 'month': 'pLKJ', 'index': 'qEfv', 'home': 'qkhY',
       'away': 'rOMv'}
THIRTY, ALL_STAR, ALL, ALL_PATCH = 'thirty', 'thirty + all-star', 'all 32', 'all 32 + all-star (game patch)'
VARIANTS = (THIRTY, ALL_STAR, ALL, ALL_PATCH)
ALL_PER_TEAM = 80
PATCH_PER_TEAM = 84                                       # the real 2026-27 season
PATCH_ROWS = 32 * PATCH_PER_TEAM // 2 + 1                # 1,345: every game and the All-Star row
FIRST_ALL_STAR_SLOT, SECOND_ALL_STAR_SLOT = 30, 31
# the club leagues' calendars: data pack part (`schedules`; the AHL's is `ahl_schedule`) -> (table, the league's slots in
# place order). Norway has no table. The AHL's is the unpatched game's: 30 clubs (the patch writes its own, farm_fit)
LEAGUES = {'ahl': ('AJKN', range(32, 62)), 'shl': ('LmeT', sorted(L.SHL)), 'liiga': ('RBQQ', sorted(L.LIIGA)),
           'del': ('Njxh', sorted(L.DEL)), 'extraliga': ('RzQW', sorted(L.EXTRALIGA)), 'nl': ('inlv', sorted(L.NL)),
           'ohl': ('uiEj', sorted(L.OHL)), 'qmjhl': ('ySfc', sorted(L.QMJHL)), 'whl': ('kTZD', sorted(L.WHL))}
LEAGUE_TAGS = tuple(tag for tag, _slots in LEAGUES.values())
LEAGUE_LABELS = {'ahl': "AHL", 'shl': "SHL", 'liiga': "Liiga", 'del': "DEL", 'extraliga': "Extraliga",
                 'nl': "National League", 'ohl': "OHL", 'qmjhl': "QMJHL", 'whl': "WHL"}
SEASON_MONTHS = (8, 9, 10, 11, 0, 1, 2, 3, 4, 5)          # September to June (month 0 = January)


class ScheduleError(ValueError):
    """The games cannot be made into the tables (the message says why)."""


def slot_games(games):
    """[(date, home slot, away slot)] of NHL.com's [date, home code, away code] games, in the order given
    (games of a team the game has no slot for are dropped)."""
    out = []
    for date, home, away in games:
        if home in L.API_TO_SLOT and away in L.API_TO_SLOT:
            out.append((date, L.API_TO_SLOT[home], L.API_TO_SLOT[away]))
    return out


def all_star_date(games):
    """The date of the All-Star game: the middle of the longest run of days without games between 20 January and
    20 February (the real season's break), as an ISO date."""
    dates = sorted({datetime.date.fromisoformat(g[0]) for g in games})
    year = dates[-1].year
    day, run, best = datetime.date(year, 1, 20), [], []
    while day <= datetime.date(year, 2, 20):
        if day in set(dates):
            run = []
        else:
            run.append(day)
            if len(run) > len(best):
                best = list(run)
        day += datetime.timedelta(days=1)
    if not best:
        raise ScheduleError("the schedule has no break for an All-Star game")
    return best[len(best) // 2].isoformat()


def trim(games, per_team):
    """`games` [(date, home, away)] with some left out so that every team plays exactly `per_team`, the same number of
    home and away games taken from each team (a flow over home -> away pairs: deterministic)."""
    count = {}
    for _d, h, a in games:
        count[h] = count.get(h, 0) + 1
        count[a] = count.get(a, 0) + 1
    out = {t: n - per_team for t, n in count.items()}
    if any(v < 0 for v in out.values()):
        raise ScheduleError(f"a team plays fewer than {per_team} games")
    home_cut = {t: v // 2 for t, v in out.items()}
    away_cut = {t: v - v // 2 for t, v in out.items()}
    pairs = {}
    for i, (_d, h, a) in enumerate(games):
        pairs.setdefault((h, a), []).append(i)
    # a flow: source -> each team's home allowance -> the games it hosts against a team -> that team's away allowance -> sink
    cap = {}

    def edge(u, v, c):
        cap.setdefault(u, {})[v] = cap.get(u, {}).get(v, 0) + c
        cap.setdefault(v, {}).setdefault(u, 0)
    for t in sorted(home_cut):
        edge('s', ('h', t), home_cut[t])
        edge(('a', t), 't', away_cut[t])
    for (h, a), idx in sorted(pairs.items()):
        edge(('h', h), ('a', a), len(idx))
    wanted = sum(home_cut.values())

    def push(u, seen):
        if u == 't':
            return True
        seen.add(u)
        for v in sorted(cap[u], key=repr):
            if cap[u][v] > 0 and v not in seen and push(v, seen):
                cap[u][v] -= 1
                cap[v][u] += 1
                return True
        return False
    done = 0
    while done < wanted and push('s', set()):
        done += 1
    if done < wanted or sum(away_cut.values()) != wanted:
        raise ScheduleError(f"{per_team} games for every team cannot be made without changing who plays whom")
    flow = {(h, a): len(idx) - cap[('h', h)][('a', a)] for (h, a), idx in pairs.items()}
    cut = set()
    for (h, a), idx in pairs.items():
        mid = len(idx) // 2
        order = sorted(range(len(idx)), key=lambda k: (abs(k - mid), k))      # from the middle of the season outward
        cut.update(idx[k] for k in order[:flow[(h, a)]])
    return [g for i, g in enumerate(games) if i not in cut]


def rows_for(games, variant=THIRTY):
    """[(date, home, away)] sorted by date for `variant`: the games the tables get."""
    played = slot_games(games)
    if variant in (ALL, ALL_PATCH):
        played = trim(played, PATCH_PER_TEAM if variant == ALL_PATCH else ALL_PER_TEAM)
        if variant == ALL_PATCH:
            date = all_star_date(games)
            busy = {t for d, h, a in played if d == date for t in (h, a)}
            team = min(t for t in range(32) if t not in busy)
            played.append((date, team, team))
    elif variant in (THIRTY, ALL_STAR):
        played = [g for g in played if g[1] < FIRST_ALL_STAR_SLOT and g[2] < FIRST_ALL_STAR_SLOT]
        if variant == ALL_STAR:
            played.append((all_star_date(games), FIRST_ALL_STAR_SLOT, SECOND_ALL_STAR_SLOT))
    else:
        raise ScheduleError(f"unknown calendar {variant}")
    return sorted(played, key=lambda g: g[0])         # a stable sort: a day's games stay in NHL.com's order


def apply(R, games, variant=THIRTY):
    """Write the schedule into nhlschedule and favoriteteamschedule of the roster `R`. `games` as the data
    pack has them ([date, home code, away code]). Returns {'variant', 'games', 'first', 'last', 'per_team'}."""
    rows = rows_for(games, variant)
    if variant == ALL_PATCH:
        for tag in (TABLE, FAVOURITE):
            if R.f[tag].max_rec < PATCH_ROWS:
                R.f[tag].grow(PATCH_ROWS)
    first = R.f[TABLE]
    if len(rows) > first.max_rec or len(rows) > R.f[FAVOURITE].max_rec:
        raise ScheduleError(f"{len(rows)} games do not fit in the game's schedule ({first.max_rec})")
    for tag in (TABLE, FAVOURITE):
        T = R.f[tag]
        for i in range(T.cur_rec):                  # the old rows would stay behind the new ones otherwise
            for field in ROW.values():
                T.set(i, field, 0)
        T.cur_rec = 0
        for i, (date, home, away) in enumerate(rows):
            d = datetime.date.fromisoformat(date)
            T.add_record({ROW['round']: 0, ROW['status']: 0, ROW['day']: d.day - 1, ROW['month']: d.month - 1,
                          ROW['index']: i, ROW['home']: home, ROW['away']: away})
    per_team = {}
    for _d, h, a in rows:
        for t in (h, a) if h != a else ():           # the All-Star row is nobody's game
            per_team[t] = per_team.get(t, 0) + 1
    return {'variant': variant, 'games': len(rows), 'first': rows[0][0], 'last': rows[-1][0], 'per_team': per_team}


def league_schedules(pack):
    """{part: games} of the club leagues' calendars the data pack has (LEAGUES)."""
    out = {part: games for part, games in (pack.get('schedules') or {}).items() if part in LEAGUES}
    if pack.get('ahl_schedule'):
        out['ahl'] = pack['ahl_schedule']
    return out


def league_rows(games, slots):
    """[(date, home slot, away slot)] in date order of `games` ([date, home, away], a club without a slot named) that the
    league of `slots` can hold: both clubs have a slot there, September to June, a club at most once a day (the first
    game of a feed's double stays)."""
    rows, busy = [], set()
    for date, home, away in sorted(games, key=lambda g: g[0]):     # a stable sort: a day's games stay in the feed's order
        if home not in slots or away not in slots or home == away:
            continue
        if datetime.date.fromisoformat(date).month - 1 not in SEASON_MONTHS or {(date, home), (date, away)} & busy:
            continue
        rows.append((date, home, away))
        busy |= {(date, home), (date, away)}
    return rows


def apply_league(R, part, games):
    """Write the league `part`'s season (`games` as the data pack has them) into its table (LEAGUES) of the roster `R`.
    Returns {'part', 'games', 'first', 'last', 'per_team' {slot: games}}; ScheduleError when it does not fit."""
    tag, slots = LEAGUES[part]
    rows = league_rows(games, set(slots))
    T = R.f[tag]
    if not rows:
        raise ScheduleError(f"the {LEAGUE_LABELS[part]} has no games between clubs of the game")
    if len(rows) > T.max_rec:
        raise ScheduleError(f"{len(rows)} {LEAGUE_LABELS[part]} games do not fit in the game's calendar ({T.max_rec})")
    place = {slot: n for n, slot in enumerate(slots)}
    for i in range(T.cur_rec):                      # the old rows would stay behind the new ones otherwise
        for field in ROW.values():
            T.set(i, field, 0)
    T.cur_rec = 0
    per_team = {}
    for i, (date, home, away) in enumerate(rows):
        d = datetime.date.fromisoformat(date)
        T.add_record({ROW['round']: 0, ROW['status']: 0, ROW['day']: d.day - 1, ROW['month']: d.month - 1,
                      ROW['index']: i, ROW['home']: place[home], ROW['away']: place[away]})
        for t in (home, away):
            per_team[t] = per_team.get(t, 0) + 1
    return {'part': part, 'games': len(rows), 'first': rows[0][0], 'last': rows[-1][0], 'per_team': per_team}


def read_league(R, part):
    """[(month, day, home slot, away slot)] of the league `part`'s calendar in the roster `R` (rows of a team the league
    has no slot for left out)."""
    tag, slots = LEAGUES[part]
    return [(m, d, slots[h], slots[a]) for m, d, h, a in read(R, tag) if max(h, a) < len(slots)]


def check_league(R, part, expected):
    """Problems of the league `part`'s calendar in `R` when apply_league made it (`expected`: its return value): plain rows
    in date order, September to June, teams of the league, nobody against himself or twice a day, the counts written."""
    tag, slots = LEAGUES[part]
    T, name = R.f[tag], LEAGUE_LABELS[part]
    problems = []
    if T.cur_rec != expected['games'] or T.cur_rec > T.max_rec:
        problems.append(f"the {name} calendar has {T.cur_rec} games, expected {expected['games']}")
    days_in = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    seen, last, per_team = set(), (-1, -1), {}
    for i in range(T.cur_rec):
        row = {k: T.get(i, f) for k, f in ROW.items()}
        month, day, h, a = row['month'], row['day'], row['home'], row['away']
        if row['round'] or row['status'] or row['index'] != i:
            problems.append(f"{name} calendar row {i} is not a plain game row")
        if month not in SEASON_MONTHS or day >= days_in[month]:
            problems.append(f"{name} calendar row {i} has the date {month + 1}/{day + 1}")
            continue
        order = ((month - 8) % 12, day)
        if order < last:
            problems.append(f"{name} calendar row {i} is out of date order")
        last = order
        if h == a or max(h, a) >= len(slots):
            problems.append(f"{name} calendar row {i}: {h} against {a}")
            continue
        for t in (h, a):
            if (month, day, t) in seen:
                problems.append(f"{name} team {slots[t]} plays twice on {month + 1}/{day + 1}")
            seen.add((month, day, t))
            per_team[slots[t]] = per_team.get(slots[t], 0) + 1
    if {int(k): v for k, v in expected['per_team'].items()} != per_team:
        problems.append(f"the {name} teams play other numbers of games than its calendar says")
    return problems[:20]


def read(R, tag=TABLE):
    """[(month, day, home, away)] (the game's own numbers: month 0 = January, day 0-based) of a schedule table."""
    T = R.f[tag]
    return [(T.get(i, ROW['month']), T.get(i, ROW['day']), T.get(i, ROW['home']), T.get(i, ROW['away']))
            for i in range(T.cur_rec)]


def dated(rows, first):
    """[(datetime.date, home, away)] of calendar rows ((month, day, home, away), month and day from 0) read as the season
    that starts in the autumn of `first`: July to December in `first`, January to June in the year after."""
    return [(datetime.date(first + (month < 6), month + 1, day + 1), home, away) for month, day, home, away in rows]


# --- the calendar as the window shows it (app/calendar.py) ------------------------------------------------------------
GAME_SEASON = 2015              # the game's own calendar is 2015-16's (it has games on 29 February 2016)


def season_of(rows, season):
    """The autumn year of the season calendar rows are: `season` (this program's calendar, the data pack's season), or
    GAME_SEASON for the game's own calendar, known by its games on 29 February in a season without one."""
    import calendar
    leap = any(month == 1 and day == 28 for month, day, *_ in rows)
    return GAME_SEASON if leap and not calendar.isleap(season + 1) else season


def split_all_star(rows):
    """(games, All-Star rows) of calendar rows ((month, day, home, away)): the All-Star game is a team against itself
    (ALL_PATCH) or slot 30 against slot 31 when neither plays anyone else (ALL_STAR, the game's own calendar). Nobody's
    game: not counted for a team."""
    others = {t for _m, _d, h, a in rows if {h, a} != {FIRST_ALL_STAR_SLOT, SECOND_ALL_STAR_SLOT} for t in (h, a)}
    games, stars = [], []
    for row in rows:
        h, a = row[2], row[3]
        star = h == a or ({h, a} == {FIRST_ALL_STAR_SLOT, SECOND_ALL_STAR_SLOT} and not {h, a} & others)
        (stars if star else games).append(row)
    return games, stars


def read_ahl(R):
    """[(month, day, home slot, away slot)] of the AHL calendar of a roster made for the game patch (ahlschedule, teams by
    their farm place: gamepatch.FARM_SLOTS), or None on any other roster (the unpatched game numbers its AHL teams in a
    way not known)."""
    from . import gamepatch
    if not gamepatch.is_patch_roster(R):
        return None
    A, F, slots = R.f[gamepatch.FARM_TABLE], gamepatch.FARM_ROW, gamepatch.FARM_SLOTS
    out = []
    for i in range(A.cur_rec):
        h, a = A.get(i, F['home']), A.get(i, F['away'])
        if max(h, a) < len(slots):
            out.append((A.get(i, F['month']), A.get(i, F['day']), slots[h], slots[a]))
    return out


def check(R, source, expected, others=()):
    """Problems of the calendar `R` has when `apply` made it (`expected`: its return value): the rules the game
    needs (rows in order, valid dates, nobody twice a day, nobody against himself but the one All-Star row of ALL_PATCH,
    in January or February) and that nothing else changed (`others`: schedule tables checked elsewhere, which may
    differ)."""
    problems = []
    for tag in (TABLE, FAVOURITE):
        T = R.f[tag]
        if T.cur_rec != expected['games'] or T.cur_rec > T.max_rec:
            problems.append(f"schedule {tag} has {T.cur_rec} games, expected {expected['games']}")
    if read(R, FAVOURITE) != read(R, TABLE):
        problems.append("favoriteteamschedule is not the same as nhlschedule")
    T = R.f[TABLE]
    teams = 32 if expected['variant'] == ALL else 30 if expected['variant'] == THIRTY else 32
    seen, last = {}, (-1, -1)
    per_team, all_star = {}, 0
    days_in = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    for i in range(T.cur_rec):
        row = {k: T.get(i, f) for k, f in ROW.items()}
        month, day = row['month'], row['day']
        if row['round'] or row['status'] or row['index'] != i:
            problems.append(f"schedule row {i} is not a plain game row")
        if not (month < 12 and day < days_in[month]) or not (month >= 8 or month <= 5):
            problems.append(f"schedule row {i} has the date {month + 1}/{day + 1}")
            continue
        order = ((month - 8) % 12, day)
        if order < last:
            problems.append(f"schedule row {i} is out of date order")
        last = order
        h, a = row['home'], row['away']
        if h == a and expected['variant'] == ALL_PATCH and month in (0, 1) and h < teams:
            all_star += 1
            if (month, day, h) in seen:
                problems.append(f"team {h} plays on the All-Star day {month + 1}/{day + 1}")
            seen[(month, day, h)] = True
            continue
        if h == a or max(h, a) >= teams:
            problems.append(f"schedule row {i}: {h} against {a}")
        for t in (h, a):
            if (month, day, t) in seen:
                problems.append(f"team {t} plays twice on {month + 1}/{day + 1}")
            seen[(month, day, t)] = True
            per_team[t] = per_team.get(t, 0) + 1
    if all_star != (expected['variant'] == ALL_PATCH):
        problems.append(f"the calendar has {all_star} All-Star rows")
    if {int(k): v for k, v in expected['per_team'].items()} != per_team:
        problems.append("the teams play other numbers of games than the schedule says")
    for tag in R.f.tables:                           # no other schedule changed
        if tag in (TABLE, FAVOURITE) or tag in others:
            continue
        T0, T1 = source.f[tag], R.f[tag]
        if tag in ('byED',) + LEAGUE_TAGS and (
                T0.cur_rec != T1.cur_rec or any(T0.record_bytes(i) != T1.record_bytes(i) for i in range(T0.cur_rec))):
            problems.append(f"schedule table {tag} changed")
    return problems[:20]
