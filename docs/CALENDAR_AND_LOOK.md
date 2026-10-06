# The 2026-27 calendar, Utah/Seattle/Vegas jerseys and the ice logo (hand-over for the next AI)

Read [AGENTS.md](../AGENTS.md) first (rules, commands, where things are). This page is for the session that
runs the owner's in-game tests of three things that are **built but never played**, and then builds
what the results allow. The owner is not a programmer: they run a test in RPCS3 and tell you in plain
words what they saw (or send `log\RPCS3.log` and screenshots). Translate their words with the tables below,
then do the "if ..." step. Nothing is committed, pushed or published without their explicit go-ahead
(AGENTS rule 6).

State when this was written (2026-10-06, version 0.8.1 released): the owner confirmed in the game that the
Tampa Bay and Toronto logos, the Select Teams names (Utah Mammoth, Seattle Kraken, Vegas Golden Knights) and Season
mode with a full update all work. The three things below are what is left of that round.

## What the owner wants (their words, 2026-10-06)

1. **The calendar**: "update the calendar to 2026-2027, the latest season, with correct dates and games being
   played, so players can play the current year". Goal: a normal switch of the update, on by default once proven.
2. **Jerseys and the home-ice logo**: "a way to change jerseys and the home ice logo on the ice; Arizona is gone, so
   update that as well". Goal: Utah (slot 22, art id 22, formerly Arizona), Seattle (30) and Vegas (31) look right;
   later other teams' new uniforms; maybe a way for the player to bring their own picture (not decided: ask).

## The three in-game tests (all are run by the owner with RPCS3 **closed** when the command runs)

All three write only LAB rosters or loose files and never touch an existing save or file without a kept copy.
Start rosters must be the community roster **as downloaded**, not one of our own outputs: the game's save
overwrites the roster in `BLES021530200` when the player saves in the game, and our test builds from our own output
test the wrong thing (this cost a round on 2026-10-06). Use `--source "file:<path to the downloaded SYS-DATA>"`;
ask the owner where it is (they used `Downloads\SYS-DATA`).

### 1. Calendar: `python -m legacy_roster calendar-test --rpcs3 <rpcs3.exe> --source "file:<SYS-DATA>"`

Code: `legacy_roster/schedule.py` (writes and checks), `calendartest.py` (the command), data pack part `schedule`
(`tools/providers/nhl_facts.py` `schedule()`, refreshed with `tools/build_datapack.py --refresh schedule`).
It saves four new rosters next to the others and writes `reports\calendar_test.txt` (also printed, with Anaheim's first
eight games of each):

| Roster | What it is |
|---|---|
| CAL 1 thirty teams | 1,180 real games between the 30 original slots (Seattle/Vegas games left out; teams play 76-80) |
| CAL 2 thirty + all-star | CAL 1 plus one All-Star game (slot 30 v 31) on 6 Feb 2027, inside the real break |
| CAL 3 all 32 teams 80 games | all 32 slots, every team trimmed to exactly 80 games (40 home), 1,280 rows |
| CAL 4 thirty teams year +11 | CAL 1 with `exhibitiondraftpick.year` (115-120) raised by 11: does the calendar's year change? |

What the owner does: load each (Roster Management > Load Roster), Season mode > Select Team > pick a team >
Calendar. Look at: the month and **year** the calendar names (before: "October 2015"), the weekdays, whether
**September** exists (the real season starts 29 Sep 2026), Anaheim's games against the list printed by the command
(first: 4 Oct home v Florida, 7 Oct home v Edmonton, 9 Oct at Winnipeg, 10 Oct at Calgary, 13 Oct home v Calgary,
16 Oct home v Boston, 19 Oct at NY Rangers), then play a game or two, simulate a week, open the standings. For CAL 3:
do Seattle and Vegas appear and play. If the game crashes: leave RPCS3 open and send `log\RPCS3.log`.

How to read the answers:

| The owner says | It means | Do |
|---|---|---|
| Anaheim's games match the list | the game reads `nhlschedule` from the roster | make it a normal step: drop the exclusion in `pipeline.default_steps`, take `SCHEDULE` out of `pipeline.EXPERIMENTAL`, choose the variant (30 or 32 teams, see below), fix the window note in `gui.py` and the CHANGELOG |
| Still the old 2015-16 games (Oct 10 at San Jose, Oct 12 home Vancouver ...) | the calendar does not come from the roster tables we write, or comes from another table | read `docs/FORMAT.md` section 8 and `docs/SEASON_PLAN.md`; test writing `nhlfutureschedule` too (Season 2?) and the league tables; look in the RPCS3 log for `db/nhlng.db` or `fe/resource_kernel/seasonphase.brk` opens (the game looks for loose copies first: an EA-file lever, ask the owner before using it; EA files must be made on the player's PC, AGENTS rule 10) |
| Games right but still "2015" | the year label is not in the roster | harmless; if CAL 4 changes it, the draft-pick years drive it (then think about shifting them in the real step, check the draft board and contracts first); if not, it is in code or `db/nhlng.db`: leave it, tell the owner |
| September missing or the weekdays are off | the game's own calendar months/weekdays (March-April can be one day off because the game's 2016 has a 29 February) | note it; do not fight it without the owner |
| CAL 3 plays with 32 teams without a crash | Seattle/Vegas can be in the season | decide with the owner: default 32 teams (80 games each) or 30 (76-80); the Season-mode tables are sized for 30 teams in places (`leaguegmdata` 30 rows), so watch for crashes in Be a GM/trades |
| CAL 3 crashes (log: `Access violation` at `0x00381c24` again, or elsewhere) | 32 teams do not work | keep 30 teams; All-Star row decides CAL 1 v CAL 2 |
| CAL 2 differs from CAL 1 only by the extra game | the All-Star game is harmless/needed | pick by what the owner prefers (it exists in the real season) |

Facts you need (full detail: `docs/FORMAT.md` section 8): `nhlschedule` (tag `ihmS`, 1,231 rows, max 1,291) is the real,
unrevised 2015-16 schedule and the owner's calendar screenshot matches it row by row; `favoriteteamschedule` (`Iwiq`, max
1,431) is a byte copy; `nhlfutureschedule` (`byED`) is the real 2014-15 one. A row = `month` (0 = January), `day`
(0-based), `index` (= row number), `home`, `away` (team slots), `round`/`status` 0; **no year, no time**. Real 2026-27:
1,344 regular-season games, 84 per team, 29 Sep 2026 to 10 Apr 2027, no games on 20 Nov, 26 Nov, 23-25 Dec, 4-7 Feb; 43
games were already played by 2026-10-06 (the table cannot hold results: a season starts from game 1). `schedule.trim`
makes the 80-game version (a deterministic flow over home/away pairs). The data pack part is a flat list of
`[date, home code, away code]`; refresh it before each release (`--refresh schedule`; the checks `check_drops` apply).
`verify.py` runs `schedule.check` only when the step ran, and insists the schedule tables are the source's otherwise.

### 2. Loose 3D textures: `python -m legacy_roster rendering-test --rpcs3 <rpcs3.exe> [--version EU|NA]`

Code: `legacy_roster/art/rpsgl.py` (the file format), `art/rendering.py` (the test), `art/lab.py` `Disc.render`,
`art/install._Writer` (kept copies, `installed.json`, "Restore the game's own pictures": AGENTS rule 11). It writes loud
versions of Utah's files into `<game folder>\rendering\...`: all home/away jerseys `texlib_{0,1}_22_{0,1,3,4}.rpsgl` with
red and blue swapped, and `icesurface\centerlogo_22_cm.rpsgl` replaced by a magenta ring with a yellow disc reading
"UTAH TEST".

What the owner does: Play Now, the Utah Mammoth at home (then as the visitor), start a game, look at the jerseys and
the centre-ice circle. Afterwards press "Restore the game's own pictures" in the window (or `photos remove`). If
nothing shows, ask them to send `log\RPCS3.log`: search for `rendering/jersey` and `centerlogo` in `sys_fs_open` lines.

| The owner says | It means | Do |
|---|---|---|
| Utah jerseys blue (not red) and a magenta "UTAH TEST" circle | the game takes loose `rendering` files | build the real thing (below) |
| Only the ice shows, or only a jersey | the game takes loose files; jersey variant/style choice differs | the log shows which `texlib_<style>_22_<variant>` it opened: write all variants of that style |
| Nothing changed | loose files were not used, or the game picked other files, or a cache | log: if it opened `/dev_hdd0/game/<TITLEID>/USRDIR/rendering/...` and read it, check the file is the right one (names, sizes, EU v NA game folder: the test writes into the version RPCS3 lists first; use `--version`); if it never asked for it the names differ: copy the exact names from the log; if loose files are ignored, the only lever left is repacking the disc archive (hard, 1.7 GB: tell the owner, do not do it) |
| The game crashes or shows garbage | a malformed file | `photos remove`, read the log, compare with the disc file (`rpsgl.Rpsgl(...).build()` must equal the disc's bytes for an unchanged file) |

Facts (details and file names in `docs/FORMAT.md` section 7, "3D textures"): archives `nocacherender.big` (1.7 GB) and
`cacherender.big` (1.4 GB), EU and NA identical; a file is "chunkzip" + RenderWare PS3 + named DXT1/DXT5 rasters with
all mipmaps; our repack equals the disc's bytes (60 of 60 tried); a raster is replaced by a same-size picture only.
Files are named by the team's art id (22 Utah, 30 Seattle, 31 Vegas): `rendering/jersey/texlib_<style>_<art>_<variant>`
(rasters `jersey_.._cm` colour, `_sm` spec, `_0_nm` normal; `font_.._cm/nm/sm` numbers and letters; one UV layout for all
teams, so a recolour plus a crest paste works), `jersey/name_..`, `pant/texlib_..`, `sock/sock_.._cm`,
`icesurface/centerlogo_<art>_cm` (1024x1024 DXT5, the centre-ice logo; a transparent strip about x 488-536 is where the
red line crosses; Arizona's reads "ARIZONA ARENA" around the coyote, slots 30 and 31 share the 2016 All-Star logo),
`icesurface_<arena art>_bm` (overhead rink picture, what it is used for is unproven), `banner_<art>_cm`,
`crowd/prop_team_*`. Menu previews of jerseys: `fe/ion/artassets/jerseys/jersey_<style>_<art>_<variant>.big` (BIGF: the
existing `bigf`/`dds` code reads them). Utah has variants 0, 1, 3, 4 in both styles (3 and 4 are home and away); Seattle
and Vegas variants 4 and 5; which style Play Now uses is not known (the test writes both).

Roster side: the community roster already has Utah/Seattle/Vegas arenas (`exhibitionarena` rows 181, 186, 162), city names
and colours in `ttOk`; the game's own roster has Arizona's and the All-Star slots' (Nashville's arena for both): 
`builder.nhl_identity` (`NHL_LOOK`) sets arena, city and colours for that source (new in 0.8.1, not yet looked at in the game:
ask the owner to open a game of Utah from "The game's own roster" and check the arena name/colours).

### 3. What to build after the loose-file test passes (in this order)

1. **Centre-ice logos** for slots 22, 30, 31 (smallest piece): a `centerlogo(img, size)` in `art/images.py` (1024x1024 RGBA,
   keep the transparent strip, optional arena-name arc: a font is needed, orientation must be checked in the game), taken
   from the ESPN logos already downloaded (`install.plain_logo_url`), installed by `install.install` like the other
   pictures (add the files to the plan in `portraits.plan`/`install`, a drawing-version tag like `LOGO_DRAWING` so they are
   redrawn once, behind the "Photos, logos and team names" switch, undone by "Restore the game's own pictures").
2. **Utah, Seattle, Vegas home and away jerseys** (+ pants, socks, number sheet `font_..`, normal/spec maps so no coyote relief
   stays, + the menu previews): palette swap and crest paste on the shared layout; ~4.5 MB per team; either overwrite the
   Arizona/All-Star variants or add rows (`stockteamjerseys` `wgjx`, `stockteamequipmenttable` `vbHh`: the community did this
   for Ducks variant 5 etc.). Draw the crest from the club logos we already have. The owner reviews pictures before anything ships.
3. Other teams' 2025-26/2026-27 uniform changes, arenas (`stadium_*`), banners, crowd props: later, one by one, with the owner.
4. Optional, ask the owner first: let the player choose their own picture for a team's centre-ice logo or jersey crest in the Roster
   editor's "Edit this team" (it already takes a logo picture).

Rules for all of it: EA bytes never ship (files are made on the player's PC from their own disc, AGENTS rule 10); a loose file the
game folder already had is kept and restored (rule 11); a change to the roster needs `verify.py` taught first and the build must
stay byte-identical on its own output (rules 3 and 4); owner's in-game check before a step leaves `pipeline.EXPERIMENTAL`.

## Practical notes

- The owner's real RPCS3 is read-only for you except through the commands above, which the owner runs themselves (rule 5).
  Their log is at `<rpcs3>\log\RPCS3.log`, held open by RPCS3: open it with full sharing (CLAUDE.md).
- Tests: `python -m pytest -q` (needs the base roster; `LEGACY_ROSTER_DISC` for the disc tests incl. `tests/test_rendering.py`).
  Calendar tests: `tests/test_schedule.py`; textures: `tests/test_rendering.py`; arena/colours: `tests/test_identity.py`.
- Files in this repo use CRLF line endings in the working copy (git `autocrlf`); keep them. Python run from a shell heredoc can
  mangle a backslash-x escape into raw bytes: write byte literals like `b'\x00\xff'` through a file edit, not a shell string, and check
  for NUL bytes after editing.
- Version bumps: `legacy_roster/__init__.py`; releases: `docs/MAINTAINING.md` ("Releasing a new version"), only with the owner's go-ahead.
- Season mode is confirmed to work with the updater's full update (2026-10-06). `cli season-test` exists to bisect a regression.
  A roster made by 0.8.0 and updated again gets its free agents relinked (`Builder.relink_free_agents`): not played in the game yet.
- "Update this roster" (in place) is new in 0.8.1 and still needs the owner's start-up check: which roster does the game load at boot
  (ROADMAP row "Round 3: update in place")?
