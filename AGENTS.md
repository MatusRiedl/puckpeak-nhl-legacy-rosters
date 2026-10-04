# Start here (for AI agents and new developers)

**NHL Legacy Roster Updater** keeps the rosters of *NHL Legacy Edition* (PS3, played on the
RPCS3 emulator) up to date. Players start a Windows exe, pick `rpcs3.exe`, choose a roster and
what to update, and get a **new** roster save named with the date and time. It is built for the
NHL Legacy community. Explain changes to the project owner in plain words, without jargon, and
leave decisions about publishing, credits and game-design trade-offs to them.

The window carries the look and logo of **Puck Peak**, the owner's other NHL project. Keep it.

## Read in this order

1. [README.md](README.md): what players see and do.
2. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how the exe works, from button to new save, and
   where new features plug in.
3. [docs/DEVELOPING.md](docs/DEVELOPING.md): setup, tests, how to make common changes, debugging,
   pitfalls.
4. [docs/MAINTAINING.md](docs/MAINTAINING.md): refreshing data, new seasons, releases, broken feeds.
5. [docs/ROADMAP.md](docs/ROADMAP.md): league checklist, pending in-game checks, capacity facts,
   open decisions, ideas.
6. [docs/FORMAT.md](docs/FORMAT.md): the save format, the rules the game enforces, the art files and
   the schedule tables.
7. [docs/SEASON_PLAN.md](docs/SEASON_PLAN.md): the study of Season / Be a GM in the newest season
   (a plan with experiments, not built yet).

## Rules that must not be broken

1. **Never change, overwrite or delete an existing save.** Every update is a new folder
   `<TITLEID>02NN` (`savedata.install`).
2. **Never add a team and never change a team's league.** The team table is full (252 records,
   8-bit ids) and leagues are fixed per slot; only existing slots can be refilled. At most 40
   players per team. `verify.py` enforces this; keep it that way.
   The one exception is the in-game league test (`cli league-test`, `lab.LEAGUE_MOVES`, ROADMAP
   "League test"), which may move named custom slots into a real league in a LAB roster. Only
   after the owner has played it may the league steps do the same.
3. **Nothing is saved unless `verify()` reports no problem.** If you teach the builder something
   new about the game's rules, teach `verify.py` first.
4. **A build on its own output must be byte-identical** (tests check it). New steps must be
   deterministic.
5. **Never write test output into the owner's real RPCS3 folder.** Use the tests, `--dry-run`, a
   copy of the savedata folder, or `tools/window_shot.py` (it makes a fake RPCS3).
6. **No git commit or push, and nothing published, without the owner's explicit go-ahead.**
   The project is public at https://github.com/MatusRiedl/puckpeak-nhl-legacy-rosters (0.6.0
   and 0.7.0 committed, pushed and released on 2026-10-04 with the owner's go-ahead). Every further commit,
   push or release needs the go-ahead again. Before pushing, check that no base roster (`work/`),
   photo pack, EA file, personal path or user name goes in.
7. **The base roster is not ours to ship** (another modder's work on EA data). It stays out of
   git (`work/` is ignored); a bundling switch stays off until its author agrees.
8. **Public pictures must not show the owner's user name, desktop or other programs.** Use
   `tools/window_shot.py --show-path`.
9. The engine (`legacy_roster/` except `gui.py`, `widgets.py`, `theme.py` and `editor/`) uses the
   standard library only; the one exception is `art/images.py` (Pillow, imported only when "Photos
   and logos" is on). The window may use CustomTkinter, and Pillow for pictures
   (`editor/pictures.py`). Leave `work/` (the original lab) untouched.
10. **Photos and logos ship inside the exe; EA files never ship.** The owner decided (2026-10-03,
    and 2026-10-04 for a single program) that this community project carries the drawn photos and
    logos inside `NHLLegacyRosterUpdater.exe` (`legacy_roster/data/photopack.zip`, made by
    `tools/build_photopack.py`, kept out of git). Pictures missing from it are downloaded and kept
    on the player's PC. Art files are always made on the player's PC from templates of their own
    game disc, and the game's own roster (`stock.py`) is read from their disc: no EA bytes are
    shipped. The base roster is still not shipped (rule 7).
11. **Pictures that were in the game folder before are never lost.** The installer keeps a copy of
    every file it replaces (also one another picture pack put there later), never overwrites a
    kept copy with its own file, and "Restore the game's own pictures" puts them back
    (`art/install.py`).

## Commands

```
python -m pytest -q                                            # tests (need a base roster, see DEVELOPING.md)
python -m legacy_roster                                        # the window, from source (needs customtkinter)
python -m legacy_roster list   --rpcs3 <rpcs3.exe>             # the command line
python -m legacy_roster update --rpcs3 <rpcs3.exe> --dry-run   # build and check, write nothing
python -m legacy_roster update --rpcs3 <rpcs3.exe> --for both  # save for the EU and the NA version
python -m legacy_roster update --rpcs3 <rpcs3.exe> --source disc   # start from the game's own roster (no community roster)
python -m legacy_roster stock-test --rpcs3 <rpcs3.exe>         # the in-game check of the game's own roster (owner only)
.venv\Scripts\python tools\window_shot.py <state> out.png      # picture of the window: none|ready|updating|done|details|failed|editor|editor-preview
python tools\build_datapack.py --refresh ratings,iihf,liiga,extraliga,shl,del,nl,norway,ahl,chl,nhl   # refresh the data pack
python tools\capacity.py                                       # player records and pool room a full update needs
python -m legacy_roster update --rpcs3 <rpcs3.exe> --photos    # also install photos and logos (RPCS3 closed)
python -m legacy_roster photos remove                          # take them away again
python -m legacy_roster update --rpcs3 <rpcs3.exe> --edits     # also apply the Roster editor's edits
.venv\Scripts\python tools\build_photopack.py                  # the photo pack inside the exe (after the data pack; build.ps1 needs it)
python -m legacy_roster art-test install|remove --rpcs3 <rpcs3.exe>   # the one-off in-game art test (done)
powershell -ExecutionPolicy Bypass -File packaging\build.ps1   # build dist\*.exe (close a running copy first)
```

## Environment

- Windows 10/11. Python 3.10+ (developed on 3.13).
- `.venv` (made by `packaging\build.ps1`) holds PyInstaller, CustomTkinter and, for images and
  screenshots, Pillow. The tests run with any Python that has pytest.
- Tests and screenshots need a roster save of the 2025-26 community family ("ROSTER2526") in
  `work/backup/BLES021530202/` or at `LEGACY_ROSTER_BASE`. Without it most tests skip. Ask the
  owner for one. The tests of the game's own roster also need `LEGACY_ROSTER_DISC` (a disc image of
  the game, read only; DEVELOPING.md).
- The program's own files on a PC: `%LOCALAPPDATA%\NHLLegacyRosterUpdater\` (settings, caches,
  reports, error log).

## How to check your work

1. Tests green, with the base roster present.
2. Engine change: the second-run tests still pass.
3. Window change: look at it with `tools/window_shot.py` at 100 %, 150 % and 200 % scaling and on a
   768-line screen.
4. Shipped change: build the exe and run the smoke test (MAINTAINING.md).
5. Anything that changes what goes into the save: the owner loads a roster in the game before the
   change leaves `pipeline.EXPERIMENTAL` and ROADMAP.md's list of checks (the window shows no mark).

## Where things are

| Area | Files |
|---|---|
| Save format, tables | `tdb.py`, `sfo.py`, `schema.py`, `schema_names.py`, `roster.py`, `layout.py` |
| The update | `pipeline.py` (order of steps), `builder.py`, `leagues/`, `lines.py`, `ratings.py`, `estimate.py`, `donors.py`, `matching.py`, `report.py` (the list of changes as a page) |
| The game's own roster | `stock.py` (from the disc, made updatable), `savedata.DiscSlot`, `savedata.roster_sfo` |
| Safety | `verify.py` |
| Data | `datasource.py` (NHL.com, data pack), `tools/build_datapack.py`, `tools/providers/`, `tools/club_slots.json` (club → slot for every league), `tools/capacity.py` |
| RPCS3 and saves | `savedata.py` (also the game's own folder and disc: `Rpcs3.game_folder`, `game_disc`; the versions EU / NA: `GAMES`, `Rpcs3.games`, `install(title_id=)`) |
| Menu art and names (portraits, logos, team names) | `art/` (`loc.py` the game's text file; `disc.py` the player's own disc, `bigf.py`, `refpack.py`, `dds.py`; photos and logos: `portraits.py` ids in the roster, `images.py` drawing, `install.py` download, write, undo; `lab.py` the one-off art test), `tools/providers/wiki_logo.py`, `tools/names_report.py` |
| Front ends | `gui.py` (tabs Update and Roster editor), `widgets.py`, `theme.py`, `progress.py`, `cli.py` |
| Roster editor | `editor/model.py` (a roster as teams and players; as is vs to be), `editor/view.py` (the tab), `editor/pictures.py` (the player's picture on the card), `edits.py` (the player's edits, kept in edits.json and applied after every update) |
| Packaging | `packaging/build.ps1`, `packaging/make_assets.py` |

## Writing for players

Window texts, errors and the README are read by players, not programmers: short sentences,
no jargon, and say what to do next ("Pick the file rpcs3.exe in your RPCS3 folder."). Engine
progress messages are shown to players too, and the progress bar recognises them by their
wording (`progress.py`).

## Current state

Version 0.7.0 (2026-10-04): fixes for two problems a tester had with 0.6.0 (nothing new goes into
the save):
- **Certificates:** the exe carries Mozilla's list of trusted certificates (certifi's
  `cacert.pem`, added by `build.ps1`) besides Windows' own, which lacked search.d3.nhle.com's
  Let's Encrypt root on the tester's PC. A check that still fails gives a plain message
  (`datasource.NotSafe`: PC clock, antivirus web scanning).
- **Missing files at start:** the window checks its unpacked files (`theme.missing_files`) and asks
  the player to start it again instead of crashing (an antivirus or cleaner removed them).

Version 0.6.0 (2026-10-04), built after the owner's checks of 0.5.0 (passed in the game:
photos, logos and team names; Save for EU + NA; the refilled national teams):
- **The game's own roster** (`stock.py`): players without a community roster start from the
  roster on their disc (window: last row "The game's own roster"; cli `--source disc`). No custom
  copies. 2014's players of 30+ retire to make room. Waiting for `cli stock-test` in the game.
- **NHL.com positions** for every NHL player (Cole Smith RW: Chicago has three right wings) and
  wingers on their own side of the lines. NHL players matched by name get NHL.com's birthdate; a
  goalie never matches a skater's record. Waiting for the in-game check.
- **Favourite-team logos** (`teamlogosreflection/r`, NHL slots only). Waiting for the in-game check.
- **One program** with every picture inside. Downloaded pictures are kept on the PC
  (`PictureCache`). Kept copies of replaced pictures are safer; the button is now "Restore the
  game's own pictures".
- **Readable results:** one line per part in the window (`BuildResult.lines`). "List of changes" is
  an HTML page grouped by part and team (`report.py`); the change log rows carry their part
  (`builder.ChangeLog`).
- **Window:** EU / US flags (drawn, `widgets.flag_image`), fewer redraws (background roster scan,
  rows kept, `configure_if_changed`, batched progress, the banner kept during an update).
- **Player links** of removed roster places are given back (`Builder.finish`), so repeated updates
  no longer fill the link table.

Version 0.5.0 (2026-10-04):
- **EU and NA:** rosters of both versions are listed with a tag; "Save for" (window) / `--for`
  (command line) saves for EU, NA or both; photos, logos and names go into both games. Saving into
  the NA version is waiting for the owner's in-game check.
- **Community rosters:** the community's 2026-27 roster is accepted (custom copies out of step) and
  updated; every empty national team is filled (IIHF rosters for 20 countries in the data pack).
- **Custom team names** use keys in the game's style (COACHELLA_VALLEY); the 0.4 names did not show
  for custom teams. Waiting for the in-game check.
- **Window:** no NEW tags, everything on by default; in the Roster editor "To be" runs the update
  by itself ("Refresh update" runs it again) and the card shows the player's picture
  (`editor/pictures.py`).
- **Disk space:** the owner's project drive has run full during work (another program filling it);
  check free space before builds and data refreshes.

Earlier (0.4.0, 2026-10-03):
- **Done:** NHL, ratings, national teams, and Liiga and Extraliga (confirmed in the game).
- **Experimental**, waiting for the owner's in-game check: SHL, DEL, National League, Norway, AHL and CHL.
- **Capacity:** with every league on, every spare player record is used. Junior depth players are
  skipped; every club still dresses 20.
- **Nothing published** (until 0.6.0).
- **Phase B:** the art test passed in the game (2026-10-03). "Photos, logos and team names" is
  built: current photos and logos made on the player's PC, with undo. Team names are written into
  the game's text file (`art/loc.py`): Utah, Seattle and Vegas instead of Arizona and the All-Star
  teams, every rebuilt club, and texts for the custom teams. The prospect pools in the custom
  slots get logos of their own. The owner saw the renamed clubs in the game (2026-10-04); the
  custom team names were still missing (keys the installer adds, see ROADMAP.md).
- **League test** (`cli league-test`): built, not played yet. It moves Coachella and Henderson into
  the AHL, Jokerit into Liiga, Ajoie into the National League and Penticton into the WHL in a LAB
  roster.
- **Phase C:** docs/SEASON_PLAN.md is written. Experiment C1 waits for the owner.
- **0.4.0:** three programs (plain, Photos with every picture inside, command line); the Puck Peak
  link and tagline in the header; the **Roster editor** tab (as is / to be, edit basics, ratings,
  team, new players, a player's own photo, a team's name, city, abbreviation and logo; edits kept
  and re-applied after every update). Waiting for the owner's check.

Details and next steps in [docs/ROADMAP.md](docs/ROADMAP.md).
