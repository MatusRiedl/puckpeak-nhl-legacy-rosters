# Season and Be a GM in the newest season: study and plan

State on 2026-10-03. This is a plan, not a feature: nothing here is built yet. It answers whether
NHL Legacy's **Season** and **Be a GM** modes can play the real 2026-27 season (calendar,
schedule, playoffs, current divisions), lists the experiments that settle the open questions, and
recommends a way forward. Facts come from the roster save, the game disc's database description
(`db/nhlng-meta.xml`) and NHL.com; FORMAT.md sections 6 and 8 have the details.

## Short answer

- **Season mode (30 teams) with the real 2026-27 games: probably possible**, if the game reads the
  schedule from the roster save (experiment C1/C2 tells). The schedule would be trimmed to fit
  the table and to the teams the mode knows.
- **Season mode with all 32 teams: unknown.** Seattle and Vegas sit in the two All-Star slots. They
  have All-Star division values and play no season games. Whether the mode accepts them once they get
  real divisions and games is what experiments C3/C4 answer.
- **Be a GM with 32 teams: unlikely** without changing the game itself. Its per-team data and its
  draft picks are sized for exactly 30 teams.
- **Recommendation: partial, step by step.**
  1. Run the cheap experiments C1–C3.
  2. If the game reads the save's schedule, offer an experimental "Season schedule 2026-27" switch
     for 30 teams.
  3. Go to 32 only if C3/C4 pass.
  4. Leave Be a GM alone until the community projects the modder mentioned show a way.

## What the roster save holds (measured)

| Thing | What is there | Limit |
|---|---|---|
| NHL schedule (`nhlschedule`) | The 2015-16 calendar: 7 Oct to 9 Apr, 82 games for each of slots 0–29. Opening night: MTL at TOR, NYR at CHI, VAN at CGY, SJ at LA | 1,291 games (1,231 used) |
| Second NHL schedule (`nhlfutureschedule`) | Another 82-game calendar (8 Oct to 11 Apr), presumably for the following season | 1,291 |
| Other leagues | AHL, OHL, QMJHL, WHL, SHL, Liiga, DEL, Extraliga, National League each have their own schedule table; Norway has none | stock size + 60 each |
| A game | day, month, home team, away team (plus round and status, always 0). **No year** | team ids 5 bits (NHL, AHL), 4 bits (European) |
| Divisions | `conferencegroup` / `divisiongroup` on each team: NHL conferences 1 West, 2 East; divisions 3 Pacific, 4 Central, 5 Atlantic, 6 Metropolitan | 6 bits each |
| Seattle, Vegas (slots 30/31) | All-Star groups (2/2 and 1/1); in the schedule only one game, against each other (the All-Star game) | – |
| Utah (slot 22) | Arizona's place: Pacific division, Arizona's 82 games | – |
| Draft picks (`exhibitiondraftpick`) | 6 years (2015–2020) × 30 teams × 7 rounds | 1,260, full |
| Salary extras | one row per team 0–29 | 30, full |

**The real 2026-27 season** (NHL.com `club-schedule-season`) has 84 games per team, from 29 Sep to
10 Apr. For 32 teams that is 1,344 games, more than the table holds (1,291):

| Season | Games | Fits? |
|---|---|---|
| 82 games × 32 teams | 1,312 | no |
| 80 games × 32 teams | 1,280 | yes |
| 30 teams, only the games between them | 30 × 84 − (games against SEA/VGK) ≈ 1,180 | yes |

**What the game builds when a mode starts** is not in the roster save:
- `leagueteams`: up to 128 teams;
- `leaguescheduletable`: up to 4,000 games;
- **`leaguegmdata`: 30 teams**;
- `leaguedraftpick`: 1,260;
- standings, stats and states.

So a Season can in principle hold more teams, but Be a GM's own per-team data has room for 30.

**The calendar and ages:**
- The game's calendar starts in 2015, and the schedule has no year, so real dates would be shown on
  the game's 2015-16 calendar. Weekdays will not match reality; nothing else depends on them.
- This roster family stores birth years as year − 1910, so that ages came out right for 2025-26.
- **In 2026-27 every player is one year too young in the game.** A shift of − 1911 would be right.
  That is a separate decision: it touches every player, and the updater, its matching and the
  community roster all use − 1910 today.

## What the modder told the owner

- Season mode has "no Vegas or Seattle".
- It "maybe" becomes possible once the community projects "zamboni roster" or "muzzes database" are finished.
- "No one has figured out the scheduling."

The facts above agree: the two slots play no season games.

## Open questions and the experiments that answer them

Each experiment uses its own new roster save; nothing existing is changed. C1 needs no tool. C2–C6
need a small hidden command that writes such rosters (`lab`). It would be written only after the owner
agrees to run them, and it would be marked LAB in the roster name.

| # | Experiment | The owner does | It answers |
|---|---|---|---|
| C1 | Start a Season with today's roster | Note the first five games of a team (date, opponent) and compare with the list above (opening night MTL at TOR, 7 Oct) | Does the Season use the roster's schedule at all? |
| C2 | A LAB roster whose opening night is changed (for example Utah at Toronto, 7 Oct) | Start a new Season with it and look at Toronto's first game | Does it read **this** roster's schedule (and not a copy on the disc)? |
| C3 | A LAB roster with real divisions: Utah to Central, Seattle and Vegas to Pacific / West, and a few games for Seattle and Vegas | Start a Season: are Seattle and Vegas in the team list, the standings, the schedule? Crash? | Can the two extra teams join the Season at all? |
| C4 | A LAB roster with the real 2026-27 schedule trimmed to 80 games for 32 teams (1,280 games) | Start a Season, simulate a month, look at standings; then simulate to the playoffs | Does a full 32-team season play, including the playoffs? |
| C5 | The same roster in Be a GM | Pick Seattle or Vegas if offered; open trades, salary, draft | What breaks in Be a GM with 32 teams? |
| C6 | `nhlfutureschedule` filled with the 2027-28 dates (when published) | Play into a second season | Is the second schedule used for the next season? |

If C1 or C2 says the Season does not read the roster's schedule, the schedule lives in the game itself
(`db/nhlng.db` on the disc, or the program). Then only a loose replacement `db/nhlng.db` could change
it. That is EA's file: it would have to be built on the player's PC from his own disc, like the art,
and it is a bigger risk.

## The plan, step by step (once C1–C3 are known)

1. **Schedule source.** Fetch the 2026-27 NHL schedule from NHL.com (`club-schedule-season` per team,
   one season file in the data pack). Map NHL.com codes to slots (`layout.API_TO_SLOT`).
2. **Trim to fit.**
   - 30 teams: drop the games against Seattle and Vegas, about 78–80 games each.
   - 32 teams: drop games so that every team plays 80, keeping home and away even and the calendar
     intact.
   - Keep dates as day and month.
3. **Divisions:** Utah Central, Seattle and Vegas Pacific; only if C3 passes.
4. **Write `nhlschedule`.** Rows in date order, `index` = row number, round/status 0. Teach `verify.py` the
   rules first: every team's game count, no team twice on one day, ids in range, at most 1,291 rows.
5. **Optional:** the AHL and the European and junior leagues the same way (their own tables, if C1/C2 show
   the game uses them). Each league's feed has a schedule endpoint (HockeyTech `schedule`, Sportality
   `game-schedule`, liiga.fi …).
6. **Ship it** as an experimental switch "Season schedule 2026-27" (NEW), off by default.

## Effort and risk

| Part | Effort | Risk |
|---|---|---|
| `lab` command for C2–C4 | about a day | none for existing saves (new LAB rosters only) |
| Schedule step for 30 teams | 2–3 days | the game may ignore the table (then: wasted, nothing harmed) |
| 32 teams (divisions + schedule) | 1–2 days on top | Season or playoffs may crash with the All-Star slots; standings may miscount |
| Be a GM with 32 teams | unknown (game code, `leaguegmdata` 30) | high; not recommended now |
| Correct ages (− 1911) | about a day, plus a community decision | every player changes; mixing old and new rosters would confuse ages |

## Questions for the modder (sportshacker)

1. What exactly are "zamboni roster" and "muzzes database", and do they change the game's own
   database (`db/nhlng.db`) or its program?
2. Has anyone tested whether Season mode reads `nhlschedule` from the roster save?
3. Do they know where the game's start year (2015) comes from?
   - the program: an RPCS3 patch could change it;
   - or the database: `leaguestates`, `dynasty` tables.
4. Did anyone try giving the All-Star slots real division values?
5. How is the community's portrait pack laid out (folders for ids above 12,000)? This one belongs to
   Phase B, but is worth asking at the same time.

## Recommendation

**Partial now, 32 teams only on evidence, Be a GM later.**
1. The owner runs C1 now (no tool needed).
2. If the answer is yes, the `lab` command gets built for C2–C4.
3. With C2 passing, the 30-team real schedule ships as an experimental switch.
4. With C3 and C4 passing too, the switch covers 32 teams.
5. Be a GM waits for the community projects or for a way around its 30-team tables.
