# Developing

How to set up, test, change and build the updater. Read [ARCHITECTURE.md](ARCHITECTURE.md) first
for how the pieces fit; [FORMAT.md](FORMAT.md) for the save format; [MAINTAINING.md](MAINTAINING.md)
for data refreshes and releases; [ROADMAP.md](ROADMAP.md) for what is done and what is next.

## Setup (Windows)

| Need | For | How |
|---|---|---|
| Python 3.10+ (developed on 3.13) | everything | python.org |
| `.venv` with PyInstaller, CustomTkinter | the window, the exe | `powershell -ExecutionPolicy Bypass -File packaging\build.ps1` creates it (and builds) |
| Pillow in `.venv` | images, window screenshots | `.venv\Scripts\python -m pip install pillow` |
| pytest | tests | `python -m pip install pytest` (any Python that can import the package) |
| **A base roster save** | most tests, screenshots | see below |

**The base roster cannot be in git.** It is another modder's work on top of EA's data. Tests
and `tools/window_shot.py` look for a roster save folder (with `SYS-DATA`, `PARAM.SFO`,
`ICON0.PNG`) of the 2025-26 community family at `work/backup/BLES021530202/`, or wherever
`LEGACY_ROSTER_BASE` points. `work/` is git-ignored. On a fresh clone, ask the project owner
for one, or save the community roster in the game and copy its folder. Without it, the tests
that need it are skipped (and say so).

**The game's own roster** (`tests/test_stock.py`) needs the game itself: set `LEGACY_ROSTER_DISC`
to a disc image (`.iso`) or extracted game folder of NHL Legacy Edition, EU or NA. It is only
read, never changed. Without it those tests skip. In PowerShell:
`$env:LEGACY_ROSTER_DISC = 'D:\...\NHL Legacy Edition (USA).iso'`.

Run from source:

```
python -m legacy_roster                                   # the window (needs customtkinter)
python -m legacy_roster list   --rpcs3 <path to rpcs3.exe>
python -m legacy_roster update --rpcs3 <path> --dry-run   # build and check, write nothing
```

## Layout

```
legacy_roster/   the program (see ARCHITECTURE.md for what each module does)
  tdb.py sfo.py schema.py schema_names.py roster.py layout.py      the save and its layout
  builder.py lines.py ratings.py estimate.py donors.py matching.py the update
  stock.py                                                         the game's own roster (from the disc)
  report.py                                                        the list of changes as a page
  leagues/clubs.py leagues/pools.py                                club leagues, pool relocation
  art/disc.py art/bigf.py art/refpack.py art/dds.py art/lab.py     menu art: the game's file format, the art test
  verify.py                                                        integrity checks
  datasource.py savedata.py pipeline.py                            data, saves, the job
  gui.py widgets.py theme.py progress.py cli.py __main__.py        front ends
  data/             data pack, icon, header logos, fonts (Source Sans 3, OFL)
tools/           maintainer scripts, not part of the exe
  build_datapack.py   the data pack            providers/   one module per data source (web.py: shared helpers)
  club_slots.json     club -> team slot        decode_schema.py, isotools.py   game disc
  capacity.py         records and pool room an update needs (read only)
  names_report.py     slots that still show an old name (read only)
  window_shot.py      picture of the window in any state
tests/           pytest suite
packaging/       build.ps1 (exe), launcher*.py, make_assets.py (images)
docs/            this folder
work/            the original lab scripts and backups (git-ignored, local only; leave untouched)
```

## Tests

```
python -m pytest -q                 # about a minute (every league is built twice)
```

| File | Guards |
|---|---|
| `test_tdb.py` | checksums; an untouched roster rebuilds byte-identical; field read/write; real names as aliases; record add/delete; broken chain detected |
| `test_sfo.py` | PARAM.SFO strings, name length, real save keeps its size |
| `test_pipeline.py` | the full NHL/ratings/national build: integrity, every NHL player on his team, NHL.com's positions (Cole Smith), wingers on their side, mirrors, hard limits, legal line-ups, exact attributes, untouched fields, clean new players, styles, **second run identical**, steps on their own, line builder rules, an unknown layout refused |
| `test_stock.py` | (needs `LEGACY_ROSTER_DISC`) the game's own roster: the save made from the disc matches a real save's tables and wrapper; prepare makes room once; a full update passes every check, skips nobody and a second run is identical; clubs in switched-off custom slots left out |
| `test_leagues.py` | every club league in the pack, built together: real names and listed players (allowing for spelling, NHL call-ups, players another league keeps, skipped players, line-up fillers), playable clubs, contracts, plausible ratings per league, pools moved and nobody lost (on a team or a free agent), free agents without contracts but with their rights, AHL players on NHL contracts belong to the parent club, second run identical, a league added later, running out of records, twins, birthdate matching |
| `test_providers.py` | every feed parser on small samples (no network): HockeyTech rows, Sportality players, DEL roster page, National League players, places to countries |
| `test_datasource.py` | the newest readable pack wins; a pack for a newer program is skipped |
| `test_art.py` | RefPack round trips; art files read and take a new image (parts, trailer kept); 32-bit logos exact; the art test installs into a fake RPCS3 and removes itself, restoring a file that was there before (synthetic art, no EA data); the logo styles incl. the favourite-team `r`, only for NHL teams; pictures downloaded once (cache) and originals always kept (another pack's file, a lost list of installed files) |
| `test_savedata.py` | finding RPCS3 (relocated `dev_hdd0`, several users, folder inside RPCS3, plain-word errors), listing, installing without touching the source, folder numbering, names; an RPCS3 with no roster but the game listed (the game's own roster, PARAM.SFO from scratch byte-identical to a real one, the disc's icon) |
| `test_progress.py` | progress mapping replays a real update's messages in order; every other message is a known remark (`progress.REMARKS`) |

The build tests use the bundled data pack only (its NHL snapshot instead of live NHL.com), so
they are reproducible offline.

## Checking a change

Before calling a change done:

1. `python -m pytest -q` is green (and not because the base roster is missing: look for skips).
2. For engine changes: the second-run tests still pass. A build on its own output must be
   byte-identical; if your step is not, it has hidden order or randomness.
3. For window changes: look at it. `tools/window_shot.py` opens the window on a temporary fake
   RPCS3 (never your real saves) in any state and saves a picture:
   ```
   .venv\Scripts\python tools\window_shot.py ready  shot.png
   .venv\Scripts\python tools\window_shot.py done   shot.png --all          # runs a real offline update
   .venv\Scripts\python tools\window_shot.py ready  shot.png --scale 0.5 --screen-lines 768   # 100 % laptop, on a 200 % screen
   ```
   Check 100 %, 150 % and 200 % scaling and a 768-line screen. The pretend RPCS3 has an EU and
   an NA roster (flags, "Save for"); `--disc <your game image>` (read only) lets the Roster editor's
   card show real portraits and adds the game's own roster to the list. The window reads the
   rosters in the background; `window_shot.py` waits for `App.scanning` to end.
   **Pitfall:** `--scale` below 1 (100 % on a 150 % screen: 0.667) leaves the list of switches in
   card 3 blank in the picture: CustomTkinter places its rows outside the scrolled area at that
   emulated scaling. Version 0.4.0 shows the same; at real scalings (1.0 and up) the list is fine.
   Judge the rest of the 100 % picture, and the switches at 150 % / 200 %.
4. For anything shipped: build the exe and start it (MAINTAINING.md, "Smoke test").
5. Anything that changes what is written into the save (new step, new rule, new league) also
   needs a test **in the game** by the project owner before it leaves `pipeline.EXPERIMENTAL`
   (the list of parts still waiting for that check; the window no longer marks them): load the
   roster, open Roster Management, Team Management and lines, and play a game with the
   changed teams.

**Never write test output into the real RPCS3 folder.** Use `--dry-run`, the tests, a copy of
the savedata folder, or `tools/window_shot.py`.

## Common changes

### Change what an update does

The steps are in `pipeline.build()` and run in a fixed order (ARCHITECTURE.md). Engine rules:

- Standard library only; never import Tk in the engine.
- Report progress with `self.progress(...)` / `say(...)` in plain sentences. If the window
  should show progress for a new message, add a pattern to `progress.STAGES`.
- Log every change to `b.log` as `[team, change, player, detail, number]`; the report and the
  summaries are built from it.
- Remove roster entries by adding them to `b.deleted` (removed in `finish()`), never directly.
  To take a player off his team, use `b.release(e, live)`. It puts him on the free-agent list when
  he has no club left. A record left teamless and not a free agent would be reused on the next run
  and break the byte-identical second run.
- A new player record comes from `b.take_record()` (donors), never by growing the table. Club
  leagues pass `required=False` and skip the player when none is left.
- Keep it deterministic: sort with explicit keys, no `random`, no dependence on dict order of
  external data.
- If you make the game accept something new, add the rule to `verify.py` and FORMAT.md
  section 5.

### Add an update step

1. `pipeline.py`: a key, a label in `STEP_LABELS`, the call in `build()` at the right place,
   and the key in `CORE_STEPS` (always offered) or among the club leagues (offered when the data
   pack has it).
2. The code: a `Builder` method or a new module that takes the `Builder`.
3. `progress.STAGES`: a pattern for the step's first message.
4. `BuildResult.headline()` / `summary()`: a line about what it did.
5. Tests in `tests/`. The window and the command line pick the step up through
   `pipeline.steps_for()` (switched on by default); list it in `pipeline.EXPERIMENTAL` and in
   ROADMAP.md until it has been played in the game.

### Add a club league

Every league the game has is in place now (ROADMAP.md). The recipe still applies when a feed has to
be replaced, or for a hand-made source.

1. **The provider.** Write `tools/providers/<name>.py` with `fetch(season_year, sources=(), log=print)`
   returning `{club name in the feed: [player, ...]}`. Use `providers/web.py` for downloads
   (`get_json`, `get_text`, polite pauses, retries), units (`inches_to_cm`, `pounds_to_kg`) and
   countries (`country_of_place`, `ISO2`).
   - **Player fields:** `first`, `last`, `birth` `[y, m, d]`, `pos` (`C L R D G`, or `F` when the
     feed does not split forwards). Where known: `shoots`, `num`, `height_cm`, `weight_kg`,
     `country` (ISO or IOC code), `letter` (`C`/`A`), `rookie`.
   - **AHL:** also `nhl_contract`.
   - **A feed with ages only:** set `birth_approx` (see `penny_del.birth_from_age`).
   - **Season check:** make the provider stop when the feed is not for `season_year`.
2. **The slot map.** Map clubs to team slots in `tools/club_slots.json`: `source` (name in the feed),
   `full`, `short`, `abbr`, `art`.
   - **`art`:** keep the slot's original art abbreviation, so logo and jersey stay the original club's.
     A pool slot's original art is in the stock team table on the disc.
   - **Several of the game's leagues** behind one switch go under `parts`, each with its
     `league_id` (see `chl`).
   - **One slot in another game league:** a slot may carry its own `league_id` (Coachella Valley,
     Henderson: 13).
   - **More clubs than slots:** the game's slots are fixed, so some clubs are left out. They are
     listed in the pack's `left_out` and shown in the window.
3. **Registration.** Add the feed to `FEEDS` in `tools/build_datapack.py`, keyed by the part's name. Check that
   `estimate.LEAGUE_GAP` and `pipeline.LEAGUE_ORDER` have the league (all the game's leagues are there).
4. **Build and test.**
   - Run `python tools/build_datapack.py --refresh <league or part>`. Read the printed counts and any
     "left out … birthdate is not possible" lines.
   - Run `python tools/capacity.py`: records and pool places still enough?
   - Run the tests, add a parser test with a small sample to `tests/test_providers.py`, and add the
     league to `pipeline.EXPERIMENTAL`. `leagues/clubs.py` does the rest.

A league without a usable feed can be supplied the same way from a hand-made JSON turned into
that structure.

### Change the window

- Components live in `widgets.py`, placement and behaviour in `gui.py`, colours and fonts in
  `theme.py` (Puck Peak's tokens). Keep text for players short and plain.
- After any change that affects what is possible (a selection, a running update), call
  `App.refresh_state()`.
- The engine runs in a worker thread; send results to the window through `self.queue` and
  handle them in `App.poll()`. Never touch widgets from the worker.
- Images: `.venv\Scripts\python packaging\make_assets.py "<puck-peak>\assets"` rebuilds the
  header logos (`logo_100/125/150/200.png`, one per screen scaling) and `app.ico` from Puck
  Peak's `BB.png` and favicon. The results are committed.
- A picture for the README: `tools/window_shot.py done docs/window.png --all --show-path
  "C:\Games\RPCS3\rpcs3.exe"`, then scale it to about 1000 px wide. Never publish a picture
  that shows a real user name, desktop or other programs.

## Building the exe

```
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Creates `.venv` if needed, installs PyInstaller, CustomTkinter, Pillow and certifi there (certifi's
`cacert.pem` goes into the exe as `legacy_roster\data\cacert.pem`, see "Things that are not
obvious"), and writes
`dist\NHLLegacyRosterUpdater.exe` (window, with `--collect-all customtkinter`) and
`dist\NHLLegacyRosterUpdater-cli.exe` (without Tk). Both carry Pillow for "Photos and logos";
its image readers are named with `--hidden-import` because Pillow loads them by name.
Close a running copy first: Windows does not let a running exe be replaced (the script stops
with a message). `build/` and `dist/` are git-ignored.

## Debugging

| Symptom | Look at |
|---|---|
| What did an update change? | the report CSV (`%LOCALAPPDATA%\NHLLegacyRosterUpdater\reports\`), or the window's "List of changes" |
| The window says "Something went wrong" | `%LOCALAPPDATA%\NHLLegacyRosterUpdater\logs\error.log` (traceback) |
| "Could not connect safely" / `CERTIFICATE_VERIFY_FAILED` | the PC's date and time, antivirus HTTPS scanning, and whether the exe carries `cacert.pem` ("Things that are not obvious") |
| The safety check failed | the problems in the details panel / CLI output; `verify.py` explains each check |
| A table's contents | `python -m legacy_roster export --rpcs3 <exe> --source <folder> --out tables` (CSV, real column names) |
| The game crashes or ignores a roster | RPCS3's `log\RPCS3.log`: search `ShowSaveDataList` (what was loaded), `Access violation` (crash), `sys_fs_open(path=` (files opened). RPCS3 keeps the log open: read it with shared access |
| A checksum question | `tdb.check_chain(raw)`, FORMAT.md sections 2 and 3 |
| Reproduce an old lab build | hidden `update --research work/research` uses the lab's saved inputs instead of live data |

## Things that are not obvious

- **Hard limits**: 252 team records (table full, team ids 8 bits), league id per team fixed,
  40 entries per team, `proteam`/`draftteam` 5 bits (the team in slot 31, Vegas, cannot hold
  rights). See FORMAT.md section 5.
- **Birth years** are stored as year − 1910 in this roster family (stock: − 1900). Records nobody
  updated since EA's 2015 database still hold − 1900 and read ten years young. Their draft year
  (stored − 1900 everywhere) gives them away: `donors.real_birth_year`. About 1,250 teamless
  records are like that.
- **Second runs must be byte-identical**, and the club leagues taught what breaks that. Each of these
  looks harmless but changes the next run:
  - a record left teamless without being a free agent (it becomes a donor next time);
  - a player listed by two feeds (keep him with the first league: `b.placed`);
  - a feed listing a player twice;
  - estimating ratings EA would set once the record exists (`b.ea_rating_for`);
  - fillers chosen from people who only become available later in the run.

  `test_a_second_run_with_club_leagues_changes_nothing` catches them. To find the cause, build twice
  and compare the tables record by record.
- **Records are the scarce resource**:
  - goalies most of all (a skater record can switch position, a goalie's cannot);
  - with every league on, every spare record is used;
  - `tools/capacity.py` shows the numbers.
- **Ratings** are stored as rating − 36 in 6 bits; the exact field per attribute is in
  `schema.py`. An older correlation-guessed map (`work/research/attr_map.json`) was wrong; do
  not revive it.
- **Mirrors** (custom teams 222–233) must stay identical to their NHL team or the game shows
  different rosters for the "same" team. Community rosters may come with them out of step:
  `check_base` recognises them by name, `sync_mirrors` makes them copies again and releases a
  player who was only on the copy (the 2026-27 roster's Ben Hutton) as a free agent.
- **Custom team names** are the game's text under the team's `shortname`; only keys in the game's
  own style (capitals, digits, underscores: LAS_VEGAS) showed. Write a custom team's city with
  `layout.set_city`, never `T.set(..., 'shortname', ...)`. Texts added to the text file keep their
  key's case (`loc.LocFile.set`). About 11,700 of the game's own text records carry a hash that is
  not that of their stored key; leave them alone.
- **EU and NA** read the same `SYS-DATA` and their discs hold the same art and text files. Code that
  works with a game folder or disc takes the title id of the roster in hand (`Slot.title_id`),
  never a fixed `BLES02153`.
- **The team table of a core build stays untouched** (`test_hard_limits_...`): only steps that name
  teams (club leagues, pools, team edits, team names) may write it.
- **Name fields** are limited in UTF-8 bytes, not characters (`Builder.set_text`).
- **Matching**: twins share last name and birthdate, so first names must agree; club matching
  requires the birthdate (the DEL, which gives ages, matches by full name and birth year);
  EA name-only matching is limited to NHL and AHL teams; `norm()` spells out ø, æ, ß, ł (otherwise
  "Øby-Olsen" loses a letter). Each rule came from a real mismatch.
- **Positions and styles**: defencemen have playing styles 1–4, forwards 5–10. A skater who
  changes between them needs a style of the new range (`Builder.set_position`).
- **Engine messages are an interface** for the progress bar (`progress.py`).
- **CustomTkinter**: `bind()` on a CTk widget binds its inner parts; use `tk.Frame.bind` for the
  widget's own size event. Scaling below 100 % makes 1-pixel outlines disappear.
- **One-file exe** unpacks itself on every start (about 3 s) and is unsigned (SmartScreen). It
  unpacks into Windows' temporary folder (`%TEMP%\_MEI...`), where an antivirus or a cleaning
  program can remove files (a player's `couldn't open ...\_MEI...\logo_100.png`, fixed in 0.7.0). The window
  checks its own files at start (`theme.missing_files`) and asks the player to start it again.
- **Certificates**: Python checks sites against Windows' own list, which Windows fills only when
  its own programs need a root. A player's PC lacked the Let's Encrypt root of search.d3.nhle.com
  (`CERTIFICATE_VERIFY_FAILED ... certificate has expired`, fixed in 0.7.0) while api-web.nhle.com (Google)
  worked. The exe carries Mozilla's list too (`datasource.tls_context`, `CA_BUNDLE`, added by
  `build.ps1`; not in git, so from source only Windows' list is used). A check that still fails
  becomes `NotSafe`: a plain message about the PC's clock and antivirus web scanning.
- `work/` is the reference lab: original scripts, the golden output of the old scripts and the
  base roster backups. Read it, do not change it.
