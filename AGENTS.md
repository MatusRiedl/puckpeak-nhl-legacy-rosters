# Start here (for AI agents and new developers)

**NHL Legacy Roster Updater** keeps the rosters of *NHL Legacy Edition* (PS3, played on the
RPCS3 emulator) up to date. Players start a Windows exe, pick `rpcs3.exe`, choose a roster and
what to update, and get that roster updated (a backup first) or a **new** roster save named with the date
and time. It is built for the NHL Legacy community. Explain changes to the project owner in plain words, without jargon, and
leave decisions about publishing, credits and game-design trade-offs to them.

The window carries the look and logo of **Puck Peak**, the owner's other NHL project. Keep it.

## Read in this order

1. [README.md](README.md): what players see and do ([CHANGELOG.md](CHANGELOG.md): what each version changed).
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
8. [docs/CALENDAR_AND_LOOK.md](docs/CALENDAR_AND_LOOK.md): the hand-over for the 2026-27 calendar, the Utah /
   Seattle / Vegas jerseys and the home-ice logo: what is built, the three in-game tests the owner runs, how to
   read their answers, and what to build next. **Read it when the owner talks about testing the calendar,
   jerseys or the ice.**
9. [docs/GAME_PATCH.md](docs/GAME_PATCH.md): the RPCS3 game patch (the year 2026, 32 teams in Season / Be a GM): every
   entry and why, the lab and its rounds, reading a crash, adding a stage, what is open. **Read it when the owner talks
   about the patch, the lab, 32 teams, All-Stars or a crash in Season / Be a GM.**

## Rules that must not be broken

1. **Never change, overwrite or delete an existing save by yourself.** An update is a new folder
   `<TITLEID>02NN` (`savedata.install`) unless the player chose "Update this roster" (the window's default
   since 2026-10-06, owner's wish): `savedata.update_in_place` replaces the picked roster's `SYS-DATA` after
   a backup copy in the program's own folder (the newest 10 per roster are kept; only those copies are ever
   pruned), never while RPCS3 runs, never the game's own roster, never a folder that is not a roster save
   directly in the save folder. The one removal is the player's own **Delete** button next to a roster:
   `savedata.trash_save` moves it to the Recycle Bin / Trash, with a question first, never permanently.
   A **Be a Pro career** (`<TITLEID>05NN`; owner, 2026-10-23) is changed only when the player presses Save on it in the
   window (`savedata.update_career`): first the whole folder is copied to the program's backups (the newest 10 per career
   are kept), never while RPCS3 runs or within 5 s of the game writing it, and only if `verify.career_problems` finds
   nothing. Tests and the lab use copies.
2. **Never add a team and never change a team's league.** The team table is full (252 records,
   8-bit ids) and leagues are fixed per slot; only existing slots can be refilled. At most 40
   players per team. `verify.py` enforces this; keep it that way.
   The one exception is the in-game league test (`cli league-test`, `lab.LEAGUE_MOVES`, ROADMAP
   "League test"), which may move named custom slots into a real league in a LAB roster. Only
   after the owner has played it may the league steps do the same.
   A second exception (owner, 2026-10-19): on a roster for the patched game, Coachella Valley and Henderson (slots
   234 / 235) carry the AHL Pacific's league fields (`gamepatch.league_fit`, last in `pipeline.patch_roster`; the
   patch's stage Y lists and names them there). Reading a patch roster puts Custom's fields back (`unleague`, so the
   builder works as before), and the unpatched game keeps them under Custom (`unpatch_roster`). `verify` allows exactly
   this pair, nothing else.
3. **Nothing is saved unless `verify()` reports no problem.** If you teach the builder something
   new about the game's rules, teach `verify.py` first.
4. **A build on its own output must be byte-identical** (tests check it). New steps must be
   deterministic.
5. **Never write test output into the owner's real RPCS3 folder.** Use the tests, `--dry-run`, a
   copy of the savedata folder, or `tools/window_shot.py` (it makes a fake RPCS3).
6. **No git commit or push, and nothing published, without the owner's explicit go-ahead.**
   The project is public at https://github.com/MatusRiedl/puckpeak-nhl-legacy-rosters (0.6.0
   and 0.7.0 released on 2026-10-04, 0.8.0 on 2026-10-05, 0.8.1 on 2026-10-06, 0.50.0 on 2026-10-23, each with the owner's go-ahead). Every further commit,
   push or release needs the go-ahead again. Before pushing, check that no base roster (`work/`),
   picture pack (`private/packs/`, a zip in `legacy_roster/data/`), anything from `private/`, personal path or user name
   goes in, and that `python tools/clean_check.py` finds nothing.
7. **Public pictures must not show the owner's user name, desktop or other programs.** Use
   `tools/window_shot.py --show-path`.
8. The engine (`legacy_roster/` except `window/`, `web/`, `gui.py`, `widgets.py`, `theme.py` and `editor/`) uses the
   standard library only; the exceptions are `art/images.py`, `art/looks.py` and `art/crests.py` (Pillow, imported only when "Photos
   and logos" is on). `app/` (the window's logic) uses the standard library, and Pillow only inside functions.
   pywebview is imported only in `window/`. `web/` is the page: plain files, offline (React and htm vendored in
   `web/vendor/`, no Node, no build step, nothing loaded from the internet). The classic window (`gui.py`,
   `widgets.py`, `theme.py`, `editor/view.py`, `editor/uniforms.py`) may use CustomTkinter; it is frozen in 0.10.x
   and goes in 0.11. Leave `work/` (the original lab) untouched.
9. **Pictures are downloaded, never inside the exe** (owner, 2026-10-20, 0.32.0). The photos and logos (`photos.zip`,
    made by `tools/build_photopack.py`) and this season's jerseys, centre-ice logos and menu pictures (`looks.zip`) are
    kept in `private/packs/` (never in git) and on the program's file server (`datasource.FILES_URL`, put there by
    `tools/publish_packs.py`, which also sends the data pack). The program downloads them while "Photos, logos and team
    names" is on (`packs.py`, `UpdateController.download_pictures`, `cli packs`); pictures missing from them are
    downloaded one by one and kept on the player's PC. Art files are always made on the player's PC from templates of
    their own game disc, and the game's own roster (`stock.py`) is read from their disc. The base roster is still not
    shipped (rule 7). No tracked file and no shipped file names where the game's content came from: `tools/clean_check.py`
    checks it (`tests/test_clean.py`, `build.ps1`, `build.sh`, `publish_packs.py`); source details stay in `private/`.
10. **Pictures that were in the game folder before are never lost.** The installer keeps a copy of
    every file it replaces (also one another picture pack put there later), never overwrites a
    kept copy with its own file, and the Photos row's "Restore" (or "Restore default") puts them back
    (`art/install.py`).

## Commands

```
python -m pytest -q                                            # tests (need a base roster, see DEVELOPING.md)
.venv\Scripts\python -m legacy_roster                          # the window, from source (needs pywebview; --classic: the old one)
python -m legacy_roster list   --rpcs3 <rpcs3.exe>             # the command line
python -m legacy_roster update --rpcs3 <rpcs3.exe> --dry-run   # build and check, write nothing
python -m legacy_roster update --rpcs3 <rpcs3.exe> --for both  # save for the EU and the NA version
python -m legacy_roster update --rpcs3 <rpcs3.exe> --source disc   # start from the game's own roster (no community roster)
python -m legacy_roster stock-test --rpcs3 <rpcs3.exe>         # the in-game check of the game's own roster (owner only)
.venv\Scripts\python tools\window_shot.py <state> out.png      # picture of the window (headless Edge): none|setup|ready|patch|updating|done|details|failed|delete|export|roster|lines|strategy|jerseys|calendar|office|contract|equipment|face|downloading|misfit|prospects|prospects-pro|prospects-make|prospects-class|prospects-import; --tab ID, --size WxH, --scale, --screen-lines, --live, --browser
python tools\build_datapack.py --refresh ratings,iihf,liiga,extraliga,shl,del,nl,norway,ahl,chl,nhl   # refresh the data pack
python tools\capacity.py                                       # player records and pool room a full update needs
python -m legacy_roster update --rpcs3 <rpcs3.exe> --photos    # also install photos and logos (RPCS3 closed)
python -m legacy_roster photos remove                          # take them away again
python -m legacy_roster update --rpcs3 <rpcs3.exe> --edits     # also apply the Roster editor's edits
.venv\Scripts\python tools\build_photopack.py                  # the photo pack, private\packs\photos.zip (after the data pack)
python tools\publish_packs.py <ssh-host>:<folder> [--dry-run]   # the packs + the data pack onto the file server (owner's go-ahead)
python -m legacy_roster packs download|status|remove            # the picture packs on this PC
python tools\clean_check.py                                     # no tracked or shipped file names where the content came from
python -m legacy_roster art-test install|remove --rpcs3 <rpcs3.exe>   # the one-off in-game art test (done)
python -m legacy_roster draft-test --rpcs3 <rpcs3.exe>         # LAB roster: where does the draft see prospects (owner)
python -m legacy_roster season-test --rpcs3 <rpcs3.exe>        # LAB rosters with more and more update steps: which one crashes Season mode (owner)
python -m legacy_roster rendering-test --rpcs3 <rpcs3.exe>     # loud Utah jerseys / centre-ice logo as loose files (owner; undo: photos remove)
python -m legacy_roster looks-test --rpcs3 <rpcs3.exe>        # new Utah/Seattle/Vegas jerseys + centre-ice logos as loose files (owner; undo: photos remove)
python -m legacy_roster equipment-test --rpcs3 <rpcs3.exe>        # LAB roster: every tuck / tape colour / tint / pads / pants number on a player (owner)
python -m legacy_roster calendar-test --rpcs3 <rpcs3.exe> --source file:<community SYS-DATA>   # LAB rosters with the real 2026-27 calendar (owner)
python -m legacy_roster year-test --rpcs3 <rpcs3.exe>          # LAB roster + patch file for the year 2026 game patch (owner; gamepatch.py)
python -m legacy_roster team32-test --rpcs3 <rpcs3.exe> [--photos]   # LAB roster + patch file + db/nhlng-meta.xml, db/nhlng.db for the 32-team game patch (owner; lab only; RPCS3 closed; --photos: names, logos, looks; undo: photos remove; docs/GAME_PATCH.md)
python tools\audit_patch.py <EBOOT.ELF>                        # check the game patch's words against the decrypted EBOOT
python -m legacy_roster update --rpcs3 <rpcs3.exe> --in-place  # update the picked roster itself (backup first)
python -m legacy_roster game-patch install [--skip-intro] [--no-login] --rpcs3 <rpcs3.exe>   # patch RPCS3 (32 teams, year 2026; RPCS3 closed; docs/GAME_PATCH.md section 7)
python -m legacy_roster update --rpcs3 <rpcs3.exe> [--game-patch]   # follows RPCS3: patched -> 32-team roster, else normal (a patch roster is turned back); --game-patch patches first
python -m legacy_roster game-patch status|remove --rpcs3 <rpcs3.exe>   # is RPCS3 patched / unpatch it
powershell -ExecutionPolicy Bypass -File packaging\build.ps1   # build dist\*.exe (close a running copy first)
bash packaging/build.sh                                        # the same on a Mac or a Linux PC (its own system only)
```

## Environment

- Windows 10/11 (also runs on macOS and Linux: `packaging/build.sh`). Python 3.10+ (developed on 3.13).
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
3. Window change: look at it with `tools/window_shot.py` at 100 %, 150 % and 200 % scaling, on a
   768-line screen and in the smallest window (`--size 940x640`), every tab it touches (`--tab`).
4. Shipped change: build the exe and run the smoke test (MAINTAINING.md).
5. Anything that changes what goes into the save: the owner loads a roster in the game before the
   change leaves `pipeline.EXPERIMENTAL` and ROADMAP.md's list of checks (the window shows no mark).

## Where things are

| Area | Files |
|---|---|
| Save format, tables | `tdb.py`, `sfo.py`, `schema.py`, `schema_names.py`, `roster.py`, `layout.py` |
| The update | `pipeline.py` (order of steps), `builder.py` (also free agents and retiring, goalie gear), `leagues/`, `lines.py`, `ratings.py`, `estimate.py`, `donors.py`, `matching.py`, `draft.py` (real draft data), `sticks.py` (sticks in team colours), `report.py` (the list of changes as a page) |
| The game's own roster | `stock.py` (from the disc, made updatable), `savedata.DiscSlot`, `savedata.roster_sfo` |
| Safety | `verify.py` |
| Data | `datasource.py` (NHL.com, data pack), `tools/build_datapack.py`, `tools/providers/` (`nhl_facts.py`: last season's players, drafts), `tools/club_slots.json` (club → slot for every league), `tools/capacity.py` |
| Contracts | `contracts.py` (units of $5,000, money scale `REAL` on game-patch rosters / `GAME` = 71.4 / 104.0, `default_terms`, `rescale`, `terms`, `problems` for verify), `Builder.real_contracts` (data pack `contracts`), `pipeline.build` (`b.money`, one rescale), `private/contracts_db.py` (dev only; `SOURCE_SLOT`: the source numbers Vegas before Seattle), `misplaced` (`tools/build_datapack.py` refuses a pack whose deals belong to another team's players), docs/notes/contracts.md. Contract status / UFA year (round 41): `status_fit` / `status_problems` (`QwoG`: Team Rosters' CONT / SAL), `ufa_fit` / `ufa_problems` (`zKKG` = birth year + 27: Be a GM's UFA / RFA). **Contract edits** (0.50.0, seen in the game in round 41): `deal_of` / `real` / `money` / `cap_in` / `edit_problems` / `organisation`, edits.json `players[key]['contract']` (real dollars), `edits.apply_contracts` right after `b.real_contracts()` in `pipeline.build`, `verify.contract_edit_problems`; the window: `app/office.py` `contract_*`, `web/js/office.js` |
| Front office | `frontoffice.py` (`org`: NHL / farm / prospects of an organisation, `seasons`, `cap_space`, `season_label`, 5 seasons 2026-27..2030-31, always real dollars), `app/office.py` (`OfficeController`: groups, sort, the contract window, record and standings from a season save), `web/js/office.js`; `tools/window_shot.py office` |
| RPCS3 and saves | `savedata.py` (also the game's own folder and disc: `Rpcs3.game_folder`, `game_disc`; the versions EU / NA: `GAMES`, `Rpcs3.games`, `install(title_id=)`) |
| Menu art and names (portraits, logos, team names) | `art/` (`loc.py` the game's text file and the Puck Peak texts `PROMO`; `menus.py` the main menu without the dead online entries; `disc.py` the player's own disc, `bigf.py`, `refpack.py`, `dds.py`; photos and logos: `portraits.py` ids in the roster, `images.py` drawing, `install.py` download, write, undo; `lab.py` the one-off art test; `crests.py` Coachella's / Henderson's crests as create-a-team logos 72 / 80), `tools/providers/wiki_logo.py`, `tools/names_report.py` |
| The window (0.10; nine tabs since 0.50) | `window/` (`main.py` start and fallback, registers the slices `update`, `editor`, `rail`, `lines`, `strategy`, `uniforms`, `calendar`, `office`, `contract`, ...; `host.py` pushes state to the page at most 25 times a second, `api.py` the page's calls (`tab`, `rail_league` / `rail_team` / `rail_step`, `calendar_*`, `office_*`, `contract_*`), `webview2.py`, smallest window 940 x 640), `app/` (controllers holding all state: `update.py`, `editor.py` (also the team list's owner: `follow_with`, `show_tab`, `rail_snapshot`, `team_view`; the six team tabs' controllers are followers that work only while their tab shows), `lines.py`, `strategy.py`, `uniforms.py`, `calendar.py`, `office.py`, `season.py`; `jobs.py`, `settings.py`, `texts.py`, `dataurl.py`), `web/` (`index.html`, `css/` (`teams.css`: the team list, calendar, front office), `js/`: `main.js` (the tabs: Setup, Game patch, Update | Roster, Lines, Strategy, Jerseys & ice, Calendar, Front office; Ctrl+1..9, Ctrl+PgUp/PgDn, Alt+Up/Down), `rail.js` (the team list), `update.js` (`SetupTab`, `UpdateTab`, `PatchTab`), `editor.js` (`RosterTab`, `LinesTab`, `StrategyTab`, `JerseysTab`, `SaveBar`, the pop-up windows), `calendar.js`, `office.js` (`OfficeTab`, `ContractWindow`), `ui.js`, `shell.js`, `bridge.js`, `store.js`, `demo.js`), `editor/card.py` (the player card's checks), `progress.py`. Mockups of new screens: `private/mockup/` (git-ignored; `serve.py --open` serves its files over `web/`) |
| Front ends | `cli.py`; the classic window (fallback, `--classic`): `gui.py`, `widgets.py`, `theme.py`, `editor/view.py`, `editor/uniforms.py` |
| Jerseys and ice | `app/uniforms.py` (a follower: loads a team 250 ms after the pick, only while the tab shows) + `web/js/editor.js` `JerseysTab` / `UniformsBody` (the Jerseys & ice tab for every team of any league with jerseys of its own, `looks.editable`: colours + crest, one row per version (NHL: all, elsewhere home and away, `looks.team_versions`): this season's (the look pack) / the game's own / from the colours / the player's own picture, the centre-ice logo (locked where `looks.own_ice` says the game shows another); the game's and this season's templates to paint on), by art id (`looks.team_art`), kept in edits.json (`uniforms`, `ice`), installed by `looks.looks_from` / `install_looks` with the photos; `tools/window_shot.py jerseys --team <slot>`; AHL art ids docs/notes/ahl-art-ids.md; classic window: `editor/uniforms.py` (NHL only, frozen). Shared ice (national 501, DEL 197, EASHL 255): `looks.ice_group` / `ice_note`, one picture for the group (lowest slot wins). Winter Classic / EASHL 2: `looks.window_team` shows the owner's jerseys. Custom slots 222-251 (create-a-team drawing): `custom_kit.py` (`ttOk` design fields, `NDEo` pieces `PIECES`, `fill`, `write`, `free_logo`, `problems` for verify; lab round 37, docs/notes/lab-round-37.md), edits.json `teams[slot]['kit']` (`edits._team_kit`), `app/teamkit.py` (`TeamKit`, the game's Create a Team menu pictures), `web/js/editor.js` `CustomKitBody`, crest pictures by `art/crests.py` (`pictures=`) |
| 3D textures | `art/rpsgl.py` (jerseys, ice: read, replace a raster, repack), `art/rendering.py` (`cli rendering-test`, done), `art/looks.py` (the real Utah/Seattle/Vegas jerseys, pants, socks, numbers, menu pictures, centre-ice logo; `cli looks-test`; `tools/look_preview.py` makes PNG sheets) |
| Game patch (RPCS3) | `gamepatch.py` (the year entry, `TEAM_STAGES` A-Y with every word and why, `league_fit` / `unleague` / `check_league_fit` (Coachella / Henderson in the AHL, stage Y), `INTRO_ENTRIES` (the optional intro skip / no boot login, and `NEWS_ENTRY`: the main menu's offline news also when signed in, ticked with the patch, `patchinstall._wanted`), `all_star_fit` / `check_all_star`, `patch_text`, the roster rules `year_shift` / `farm_fit` / `divisions_fit` / `future_fit` (`FUTURE_DAYS`) and their checks, the db files `fit_meta` / `fit_db`), `PLAYER_ENTRY` / `player_patch_text` (the one entry players switch on), `is_patch_roster` / `unshift` / `mend_years`), `patchinstall.py` (RPCS3's `patches/` and `config/patch_config.yml` as text, the db files in the store `patch`, `state`, `remove`), `pipeline.update(game_patch=)` / `patch_roster`, `rights_wide` / `rights_narrow` / `rights_fit` / `check_rights` (six-bit rights on patch rosters, 0.23), `calendartest.team32_test` / `year_test` (the lab rosters), `tools/audit_patch.py` (words against the decrypted EBOOT), docs/GAME_PATCH.md |
| Calendar | `schedule.py` (the real schedule into `nhlschedule` / `favoriteteamschedule`, `check`; every club league's table: `LEAGUES` (tag, slots), `league_schedules` (data pack part `schedules` + `ahl_schedule`), `league_rows`, `apply_league`, `read_league`, `check_league` (verify), `pipeline.CALENDAR_STEP`; for the Calendar tab `read`, `dated`, `season_of`, `split_all_star`, `read_ahl` (patch rosters' AHL)), `calendartest.py` (`cli calendar-test`), data pack part `schedule` (`tools/providers/nhl_facts.py`); the tab: `app/calendar.py` (`CalendarController`: month, day, mode, `season(on)` = My season), `web/js/calendar.js`; `tools/window_shot.py calendar` |
| Be a Pro careers (`careersave.py`, P6) | `careersave.py` (a `<TITLE>05NN` save read and built again byte for byte: `Career` = the database + ten chunks, chunk 8 the pro as the career began, chunk 24 his XP earned / spent; the game shows and plays the database's `wiLv` `c_` ratings; `Pro`, `set_xp` (to spend = earned - spent), `set_ratings` (40-99, skaters), `set_name`, `sub_title` / `renamed_label` (the Load Pro label the game made: LAST + slot + 1), `EDITABLE`, `find`, `read` (5 s settle), `pieces`), `verify.career_problems` (only the allowed bytes / rows change), `savedata.update_career` (backup of the whole folder, newest 10, never while RPCS3 runs; `label=` sets PARAM.SFO's SUB_TITLE), tests/test_careersave.py (copies under `LEGACY_ROSTER_CAREERS`: every one byte for byte), docs/notes/be-a-pro-save.md; the window: `app/career.py` (`CareerController`, slice `career`: `look`, `open`, `set` name / XP / ratings, `save` asks first (rule 1), `closing`), Draft & Pro's last view `careers` (`app/prospects.CAREERS`), `web/js/prospects.js` `CareerTab` / `CareerPro`, api `career_*`, tests/test_career_app.py, `tools/window_shot.py prospects-career` (needs `LEGACY_ROSTER_CAREERS`). The birth year is not shown (a patched game's career keeps it shifted) |
| No Press Start (`art/pressstart.py`, lab 47d) | `skip_file` / `skip_files`: the disc's `03_pressstart.big` (cacheboot.big, `SIZE` / `SHA1`) with `transitionDone` calling `startPressed(0)` after a quick boot (found by name, 18 bytes, same length); tests/test_pressstart.py, docs/notes/press-start.md |
| Season / Be a GM saves (read only) | `seasonsave.py` (`find`, `read` -> `Season`: `today`, `human` / `farm`, `games` with scores, `results`, `records`, `standings`, `place`; refuses a save written in the last 5 s), `app/season.py` (`SeasonSource`: the picked roster's game version, newest save, cached), docs/notes/season-saves.md; never writes |
| Season-mode test | `seasontest.py` (`cli season-test`) |
| Lines and strategies (Roster editor) | `lines.py` (`GROUPS`, `check_lineup`: the rules, `set_lineup`, `slot_label`), `strategy.py` (table `oYeE`: `SECTIONS`, `CHOICES` words, ranges `top`, `clean`, `write`, `out_of_range` for verify; the game's menu order and words, lab round 28, docs/notes/strategies.md), `edits._team_lines` / `_team_strategy` (edits.json `teams[slot]` `lines` / `strategy`, applied in `apply_teams`), `app/lines.py`, `app/strategy.py` (followers of the team list; drafts not applied are kept per team), `web/js/editor.js` `LinesTab` / `StrategyTab`; `tools/window_shot.py lines|strategy` |
| Roster editor | `editor/model.py` (a roster as teams and players, `apply_edits`), `editor/view.py` (the tab: the picked roster as it is plus this visit's edits; saves in place or as new), `editor/pictures.py` (the player's picture on the card), `edits.py` (the player's edits, kept in edits.json and applied after every update); player type: `ratings.STYLES` / `GOALIE_STYLES` / `STYLE_CHOICES` (all named in the lab 2026-10-16), `style_label` / `style_choice`, `Builder.set_style`, `verify.style_problems`; face: `faces.py` (`DaPp` / `QDTK` / `jfuZ`, valid heads = table `vuqu`, `problems` for verify), `app/editor.py` `face_open` / `face_search` / `face_pick_*` (the "Face of a player" window), docs/notes/faces.md; **created look** (the game's Create Player: head shape, skin tone, hair, facial hair, eyebrows, eyes, black eye, scars, freckles; P1b): `faces.LOOK` / `write_look` / `read_look` / `random_look` / `look_problems` (verify), only on the reserved Create Player records 16000-16179 (`faces.RESERVED`, `free_reserved` highest id first, `KEEP_FREE` 10 skaters / 5 goalies for the game), edits.json `players[key]['look']` (`edits._look_records` / `_set_look`, `_create`), the card's Look... window (`app/editor.py` `look_open` / `look_set` / `look_random` / `look_done`, slice `look_pics`: the menu's pictures from the disc; `editor.js` `LookPart` / `LookWindow`; `tools/window_shot.py prospects-look`), docs/notes/draft-class.md "How the program makes a created look" |
| Draft classes and my pro (P1 engine, P2 tab, P3 class files + random maker built; plan docs/plans/another-context-window-is-sorted-liskov.md) | `draftclass.py` (`DRAFT_SLOTS` European + CHL clubs, `TIER_BANDS` potential per growth tier, `eligible_year` 15 September rule, `apply` after the last `draft.apply`, `problems` for verify), a class player = a new player in edits.json with a `prospect` block (`class`, `tier`, `potential`); records held before the leagues (`edits.records_needed`, `Builder.hold_records`, `held_records`); a new player without his own number takes a free one (`edits._move(wins=False)`); `'draft classes'` / `'new player records'` experimental; the tab "Draft & Pro" (10th, Ctrl+0): `app/prospects.py` (`ProspectsController`, a follower; Add / pick open the editor's card: `EditorController.new_player(preset, extra)`, `open_person`), `web/js/prospects.js` (`ClassRail` in the team list's place, `ProspectsTab`), the card shared with the Roster tab (`editor.js` `useCardForm`); class files `draftclass.class_file` / `read_class` (JSON `legacy-roster-draft-class` v1, cards as typed, club by league + name, `shift_birth` to another draft; `ProspectsController.export_class` / `import_class` / `import_text`, report window), random maker `draftclass.make` (seeded; names mixed from non-NHL players of the same country, never a roster full name; `tiers_for` by strength; potential as the game's stars `draftclass.stars`; class files carry a created look; `spread` over the league's clubs; `ProspectsController.make_open` / `make_set` / `make`; `EditorController.next_note`); `tools/window_shot.py prospects|prospects-pro|prospects-make|prospects-class|prospects-import`; lab round 44 docs/notes/lab-round-44.md, research docs/notes/draft-class.md |
| Picture packs (downloaded, 0.32.0) | `packs.py` (`manifest`, `path`, `have`, `missing`, `sync`, `fetch`, `prune`, `remove_all`; folder `app_dir('packs')`, `<name>-<sha12>.zip` + `state.json`; `LEGACY_ROSTER_PACKS`), `datasource.FILES_URL` / `files_url` (`LEGACY_ROSTER_FILES_URL`), `art/photopack.py` / `art/lookpack.py` open `packs.path(...)`, `app/update.py` `download_pictures` / `_photos_row` (the Photos row, first and gold), `tools/publish_packs.py`, `tools/clean_check.py`; the server: docs/notes/pack-hosting.md |
| Packaging | `packaging/build.ps1`, `packaging/build.sh` (refuse a zip in `legacy_roster/data/` and a `clean_check` hit), `packaging/make_assets.py` |

## Writing for players

Window texts, errors and the README are read by players, not programmers: short sentences,
no jargon, and say what to do next ("Pick the file rpcs3.exe in your RPCS3 folder."). Engine
progress messages are shown to players too, and the progress bar recognises them by their
wording (`progress.py`).

## Current state

**Version 0.50.0 (2026-10-20 night, the owner's pick; released 2026-10-23 with the owner's go-ahead; plan
docs/plans/listen-right-now-the-robust-walrus.md):** the owner compared the window with the NHL19 companion app (notes
docs/notes/nhl19-app-ui.md), approved a clickable mockup (`private/mockup/`) and asked for it as "absolutely major
update" 0.50.0. Everything since 0.10.4 (the 0.35.0 entry below and older test builds) goes out with it in one commit;
CHANGELOG.md has one 0.50.0 entry (the release text is made from it).
- **Nine tabs** (`web/js/main.js`): Setup, Game patch, Update | Roster, Lines, Strategy, Jerseys & ice, Calendar, Front
  office. One team list (`web/js/rail.js`, slice `rail`) for the six team tabs, owned by `EditorController`
  (`follow_with`, `show_tab`, `team_view`); the team tabs' controllers are followers (`follow(team)`, `hide()`,
  `roster_changed()`) that work only while their tab shows; Lines / Strategy drafts are kept per team; Jerseys loads 250 ms
  after a pick. One Save bar (`SaveBar`). Smallest window 940 x 640. Lines, Strategy and Jerseys are tabs now (Equipment,
  Face, Team, My edits, the custom-team kit stay pop-up windows).
- **2026-10-21 (owner, after a "damaged" roster in the patched game):** tab order Setup, Game patch, Update; the window
  always opens on Setup (`main.js` `startTab`). `UpdateController.misfit` marks a roster the game as RPCS3 has it cannot
  load (normal roster + patched version, 32-team roster + unpatched; `texts.MISFIT_*`) in Setup, the Update tab's bar and
  the Game patch tab; after Patch / Unpatch the next scan asks to update the picked roster (`_ask_fit`, "Update it now"
  = in place, its own name, whatever the save mode: `_fit` in `start`). News bodies: "Updates, patches, statistics! Join
  us on gg.puckpeak.com" (`loc._NEWS`, `PROMO_VERSION` '#3'). `tools/window_shot.py misfit`. Not seen in the game yet.
- **Calendar** (`app/calendar.py`, `web/js/calendar.js`): month page from the roster's own calendar (`schedule.read`,
  `dated`, `season_of`, `split_all_star`), the AHL on patch rosters (`schedule.read_ahl`), a day's games, the team's list.
- **Front office** (`frontoffice.py`, `app/office.py`, `web/js/office.js`): payroll, cap and space for five seasons (always
  real dollars), NHL / farm / prospects. **Contract edits** (seen in the game, lab round 41): the contract window, edits.json `players[key]['contract']`, `edits.apply_contracts` after `b.real_contracts()`,
  `verify.contract_edit_problems` first.
- **My season** (`seasonsave.py`, `app/season.py`, docs/notes/season-saves.md): the player's newest Season / Be a GM save,
  read only (never while it was written in the last 5 s): results, today, next game, playoffs in the Calendar; record,
  place and standings in Front office. Checked on 13 lab saves (records = the game's own for every team); the Standings
  screen's tie order and the preseason are not checked (ROADMAP "Checks of 0.50.0").
- **Seattle / Vegas contracts fixed**: the data pack had their deals swapped (`private/contracts_db.py` `SOURCE_SLOT`);
  `contracts.misplaced` + `tools/build_datapack.py` refuse such a pack now. The local pack is rebuilt and was published
  on 2026-10-23 (owner's go-ahead).
- **Round 41 (2026-10-21, the owner's report; plan docs/plans/ok-let-me-know-soft-wilkes.md, docs/notes/lab-round-41.md):**
  Team Rosters' CONT / SAL "N/A" (Eichel, Hanifin at Vegas) = contract status `cPbu.QwoG` 0: `contracts.status_fit` /
  `status_problems`. Be a GM's UFA / RFA come from `cPbu.zKKG` = birth year + 27 (the disc's rule): `contracts.ufa_fit` /
  `ufa_problems`. Both run in `pipeline.build` after `b.finish()` (all records after a step that moves players, else only
  contract-edited rows / none) and in `patch_roster`. Roster Management's AHL lacked Coachella Valley / Henderson on a
  roster from the game's own (the list walk `0x128348` stopped at 223): patch **0.22**, stage Y's cave `0x1283bc`. Played
  in the lab: all three fixed; real and edited contracts in Team Rosters, a new Be a GM and Be a Pro Central, so
  `'contracts'` and `'contract edits'` left EXPERIMENTAL. Checked again through the built exe (Patch 0.22 + update,
  Unpatch + update, both money scales). Open: the game booted another roster than the one updated in place (ROADMAP
  "Checks of round 41").
- **Round 42 (2026-10-22, the owner's asks: contracts for every club, Coachella's real roster, an editor without locks;
  plan docs/plans/ok-let-me-know-soft-wilkes.md, docs/notes/lab-round-42.md):** the AHL's 32 rosters come from the source
  (data pack part `leagues.ahl`, `private/club_rosters_db.py`; rights from the list's `org`, `clubs._rights`). Real deals
  wherever a player plays; **starter deals** (`contracts.STARTER` / `starter_terms`, `Builder.starter_contracts`) for
  every club player without a deal or NHL rights; status / UFA / verify for every club (`contracts.contract_clubs`);
  contract edits for anyone on a club (free bounds outside NHL organisations, `contracts.organisation`); Front office,
  the contract window and the card for every club, free agents can be signed. **Patch 0.23**: the roster's player rights
  `cPbu.WBbd` have six bits on patch rosters (`gamepatch.rights_wide` / `rights_narrow`, `tdb.Table.widen` / `narrow`,
  the db description's proteam at six: `META_TEAMS`), so Henderson is Vegas's farm (`vegas_depth` is gone);
  `UpdateController.misfit` marks a patch roster whose bits differ from the installed patch (`MISFIT_VERSION`,
  `patchinstall.installed_rights`). `pair_farms` runs before the NHL step; `clubs._fill_lineup` takes players near the
  club's level and never one under an NHL contract no list names. Played in the lab: Henderson In the System, call-ups,
  a Vegas Be a GM through the season, the 2027 draft and free agency.
- **Round 43 (2026-10-22, through the built exe; docs/notes/lab-round-43.md):** Patch 0.23 + update in place, Team
  Rosters with every club's deals and both edits, Play Now at Coachella; Unpatch + update: the unpatched game loads it at
  the $71.4M scale. Fixed: `savedata.update_in_place` sets PARAM.SFO's `SAVEDATA_DIRECTORY` to the folder's own name (a
  hand-copied folder loaded its original); the load path told to players is "Customize > Save/Load/Delete > Load >
  Rosters" (`texts.HOW_TO_LOAD*`, cli, README, QUICKSTART). Note: Unpatch puts back what RPCS3 had before the first
  Patch, also an older patch of ours put in by hand.
- **Draft & Pro, rounds 44-45 (2026-10-22; plan docs/plans/another-context-window-is-sorted-liskov.md, notes
  docs/notes/lab-round-44.md, lab-round-45.md):** the 10th tab (rows "Roster editor" and "Draft classes" above). Round
  45: a career copies a created look only for a player listed through his Create Player record's own link (`caBZ` BERR 1,
  qEfv = qFky = game id); the builder lists new players that way, verify refuses another link (`faces.link_problems`); a
  new Be a GM career then showed the created face (my pro in Be a Pro: not played). Edits reach Season / Be a GM / Be a
  Pro when a career is started (the game copies the roster then); running careers are never changed (P6 not built).
- **Main menu news (2026-10-22, owner: "all these texts should say the same gg.puckpeak.com"):** `loc.PROMO` '#4' (every
  news title and body, also the fighting tip and NHL 94: "Puck Peak" / the gg.puckpeak.com line); patch **0.24** = 0.23's
  words + `gamepatch.NEWS_ENTRY` (0x7e8d58, ticked with the patch): signed in, the game showed the server's news (the
  2014 texts) over our text file; the entry keeps the offline ones. Lab: boots, the panel shows the line (signed out).
  Online is the owner's check (docs/notes/promo-texts.md section 5).
- **Round 46 (2026-10-22/23, the owner's report; plan top section of docs/plans/another-context-window-is-sorted-liskov.md,
  notes docs/notes/lab-round-46.md, league-calendars.md):** (1) the exe showed a test's fake RPCS3: a test's late rescan
  wrote the real settings.json; `tests/conftest.py` `pytest_configure` points LOCALAPPDATA / XDG_* (HOME off Windows) at
  one temp folder for the whole run (`test_app` checks it), and the exe neither uses nor remembers an RPCS3 in the temp
  folder (`app/update.temporary`, `start_up`, `_scanned`). (2) **Calendars of
  every league** (`'league calendars'`, out of EXPERIMENTAL since the exe round 46c): Season mode plays all ten leagues
  with a table from the roster (lab: DEL, SHL, OHL patched, AHL unpatched, game for game); data pack part `schedules` (9 leagues, on the server since 2026-10-23);
  `schedule.LEAGUES` / `apply_league` / `check_league` (verify), written in the calendar step for every league whose clubs
  step runs (`pipeline.CALENDAR_STEP`); the Calendar tab shows every league (Norway from the pack, "game's own" note).
  (3) Coachella's plain jersey: `layout.OWN_DESIGN` (`jerseystyle` 1) in `clubs.own_kit`; centre ice showed the crest in
  the lab. (4) The owner's pro was in Be a Pro under Overall 80-89 (the filter opens on 70-79): `prospects.PRO_WHERE`.
  Lab trap: "Unpatch" in the lab puts back the lab's old hand-installed test patch (0.18 stages ticked), under which a
  normal roster is "damaged"; switch the lab's entries off for an unpatched check (lab-round-46.md, 46c).
- **Round 47 (2026-10-23, the owner's report; plan top section of docs/plans/another-context-window-is-sorted-liskov.md,
  notes docs/notes/be-a-pro-save.md, press-start.md):** the owner's Florida pro was never in the game (made after the last
  Save; the game loaded the older file). (A) **My pro**: row states read from the roster as saved (`in` / `unsaved` /
  `waiting`, `ProspectsController._saved` on `editor.raw`); new players of edits.json the saved roster lacks join the
  visit's `session` when a roster opens (`EditorController._not_saved`), so Save writes them after a restart; the pro's
  team is an NHL team or a CHL club (`pro_team`, Apply refuses others); a gold "Not in the game yet" line; closing with
  edits not saved asks Save now / Close anyway / Cancel. (B) **Running Be a Pro careers** (P6 v1, rule 1's career text):
  `careersave.py`, `verify.career_problems`, `savedata.update_career`, Draft & Pro's last view "Be a Pro careers"
  (`app/career.py`): the pro's name (also the Load Pro label the game made from it), his ratings (`c_`, 40-99; not for a
  goalie career yet) and the XP to spend in Player Growth (earned - spent); the Overall is not shown (the game works it
  out when the career loads). (C) **No Press Start**: `art/pressstart.py`, put in by `patchinstall.set_press` with "Skip
  the intro" (`NO_PRESS = True` since lab 47d passed on the EU disc; the NA file is the same bytes), removed on Unpatch;
  `'no press start'` experimental. **Lab round 47** (docs/notes/lab-round-47.md): 47d boots to the main menu with no
  press (profile and roster autoload, Be a Pro, Season, Save and Exit; Be a GM and online not tried); 47a: the game loads
  at boot the **oldest roster written since the last boot** (round 41's open point; what the program should do is the
  owner's call, ROADMAP), a pro with 98 everywhere is "99 Overall" under 90-99; 47b: six one-change copies of a career
  load, play, save and reload (be-a-pro-save.md). A misfit roster (older patch rights) crashed Pick an NHL Pro (already
  marked by `misfit`). 47c (the built exes): the window edited a lab career, the game loaded it (Player Growth showed
  the XP and rating, Overall worked out by the game), boot with no key pressed, Unpatch removed the press files.
- Tests 562 passed, 3 skipped (with the disc; 2026-10-23 afternoon; since then only
  `test_the_pages_server_takes_many_connections_at_once`, run alone; a last full run was stopped at the owner's word).
  Built again for release 2026-10-23 17:25 (window 26.4 MB, cli 18.5 MB, no code change since 16:00), `clean_check` 0
  hits; smoke test: the window opens with the ten tabs (not blank), `cli list` / `game-patch status` on the lab.
  **Released 2026-10-23** (the owner's go): commit and tag `v0.50.0`, GitHub release with `NHLLegacyRosterUpdater.exe`
  and `SHA256SUMS.txt` (no data pack asset: MAINTAINING.md step 8).
  **Blank window fixed** (found in lab 47c): pywebview's local server listened with Python's queue of 5 connections and
  Windows refused the page's other font / script requests, so the window could stay empty (4 of 4 starts with WebView2's
  debug port, from source too); `window/main.roomy_server` sets the queue to 64 before `webview.start` (0 of 8 blank). The Jerseys test
  (`test_the_jerseys_window_says_this_seasons_come_with_the_photos`, 120 s wait) timed out once while a build ran beside
  the suite; alone it passes.

**Version 0.35.0 (2026-10-20; now part of 0.50.0, never released on its own):** everything since 0.10.4 in one version
(0.20.0 to 0.32.0 below were test builds, never on GitHub); its CHANGELOG entry became the 0.50.0 entry. Its last part is the picture fix below. Players who still show a silhouette (no photo anywhere the
program looks): not built, "just a couple of people" (owner); findings in docs/notes/missing-photos.md.

**Picture fix (2026-10-20, in 0.35.0; plan docs/plans/giggly-squishing-candy.md, notes docs/notes/player-pictures.md):**
testers of 0.10.4: an own picture (Troy Terry) never showed; "almost all player images are wrong". Owner's picks: own
pictures always go in; clashes: move ours, give theirs back; a failed photo keeps the old picture.
- **Own pictures** (`'own pictures on save'` experimental): `Builder.own_photos` / `own_logos` (edits.py);
  `pipeline.Pictures(own_only=True)` plans and installs only those (no names, menus, jerseys, crests, masks, pool logos):
  on the Roster editor's Save (`app/editor.save`, RPCS3 closed; also photos / logos of earlier visits,
  `_picture_edits`; never at the same time as an update, `saving_pictures`) and on an update with Photos off.
- **Picture numbers** (`'picture numbers'` experimental): `install.scan_claims` -> `portraits.Claims` (every roster
  save of every RPCS3 user, every portrait file); `same_person` (no birth year); `Registry.id_for` never gives out a
  number someone else uses, new ones from `FRESH_IDS` (40,000); `forget_conflicts` + `install.give_back` after the
  save. Simulated on the owner's rosters (read only): 0 strangers after updating both, 127 before.
- **Failed photos keep the old picture**: `install.prefetch` before `plan` (`Builder.bad_pictures`, `art_line` "could
  not be made"); `images.stand_in` (NHL.com's grey silhouette; downloaded links only); `tools/build_photopack.py` leaves
  stand-ins out. Pick time: `NO_FACE` for a cut-out without a head.
- Tests: tests/test_pictures.py, `test_app` editor Save. Checks: ROADMAP "Checks of the picture fix".
- Lab round 40 (agent, docs/notes/lab-round-40.md): the Roster editor's Save with Photos off gave Troy Terry an own
  picture, shown on his card in the game. Built (window 26.1 MB, cli 18.4 MB) and smoke-tested.

**Version 0.32.0 (2026-10-20, not committed; plan docs/plans/ok-new-plan-check-sprightly-dragonfly.md top part, notes
docs/notes/pack-hosting.md, private/NOTES.md):** the owner wants none of the game's content inside the exe and no word
pointing to where it came from.
- **Packs leave the exe** (rule 9): `photos.zip` (102.8 MB) and `looks.zip` (54.6 MB) are downloaded from
  `https://puckpeak.com/legacy-roster/` (`manifest.json` format 1: per pack `file`, `size`, `sha256`, `built`; files named
  `<name>-<sha12>.zip`, so a pack open on Windows is never replaced; the old one is pruned at the next start). The
  window starts the download at start and when the Photos switch goes on (`UpdateController.download_pictures`); an
  update pressed meanwhile waits ("Waiting for the download..."); a failed download leaves the update to run with
  pictures one by one, and the result says "Some pictures could not be downloaded". The classic window and `cli update
  --photos` call `packs.sync()` first. Window exe 26.1 MB (was 172.8), cli 18.4 MB.
- **The server stands alone**: `/opt/nhl-legacy/` with its own nginx container (read-only, 0.5 CPU, 64 MB, 4 MB/s per
  download, 50 at once, GET / HEAD only, 404 outside the manifest / data pack / packs), one Caddy route in puckpeak.com's
  block. puckpeak.com and cheerin.quest checked after. `tools/publish_packs.py` sends packs, the data pack, then the
  manifest last.
- **Data pack format 2**: parts `ratings_list` / `ratings_full` (renamed), neutral `sources` labels, served from the same
  folder (`datasource.PACK_URL`); 0.10.x programs refuse format 2 and keep their own.
- **Neutral names everywhere** (`tools/clean_check.py`, `tests/test_clean.py`): "this season's" jerseys, "current
  ratings", `looks.PACK = 'pack'`, experimental `'current ratings'`; the source tools and their tests moved to
  `private/` (git-ignored). README: "Unofficial fan project, not affiliated with or endorsed by the game's makers or the
  league."
- **Window**: "Photos, logos and team names" is the first row of step 4, highlighted in gold (`featured`, gold toggle,
  a thin progress bar), with texts that never say where from (`texts.PHOTOS_*`, `photos_will`); Patch is a gold button,
  Unpatch a gold outline; "Restore default" is a small red glowing button (the page's "Restore the game's own pictures"
  is gone: the Photos row's Restore does it); no "RPCS3 is running" pill in step 1 and no close-RPCS3 line in step 2
  (Patch / Unpatch / the switches stay on and check RPCS3 when pressed); the "?" next to Patch (`texts.PATCH_INFO`,
  `ui.Info`) says everything the patch does; the Jerseys
  window says "This season's jerseys come with Photos, logos and team names" without the look pack.
  `tools/window_shot.py downloading`.
- Built and smoke-tested; lab round 39 (agent, docs/notes/lab-round-39.md): the packs downloaded by the exes, a Utah
  home game with this season's jersey and centre ice, the lab put back. Checks: ROADMAP "Checks of 0.32.0".

**Version 0.31.0 (2026-10-20, not committed; plan docs/plans/ok-new-plan-check-sprightly-dragonfly.md top part, notes
docs/notes/lab-round-37.md):** the owner asked why Coachella Valley could not change jerseys and for "editable
everything". Owner's picks: shared ice edited as a group with a note; custom colours "quick + detailed".
- **Custom teams 222-251** (`'custom team kits'` experimental): the game draws them like Create a Team teams. Lab round
  37 named the `ttOk` design fields (`jerseybackhome` / `away` 0-8, `pantsstyle` / `sockstyle` / `font` 0-5;
  `jerseystyle` left alone) and the 11 `NDEo` pieces (1-4 goalie glove / blocker / pads / stick, 5 gloves, 6 socks,
  7 pants, 8 helmet, 9 jersey, 10 numbers, 11 crest). `custom_kit.write` sets designs, `primarycolor` /
  `secondarycolor`, three team colours painted on every piece (`fill`), then the pieces set one by one; the crest is a
  create-a-team logo (`artid` 20001 + n), the team's own (234 / 235) or a picture on a free logo (`free_logo`, never 54,
  never another team's `OWN_ART`). `verify` runs `custom_kit.problems` (ranges, `NDEo` rows unchanged, a crest picture's
  art id on one team only). `edits._team_kit` runs in `apply_teams`, before `club_gear` / `goalie_gear`.
- **Round 34's mistake fixed**: piece 1 is the catching glove, not the jersey; `layout.OWN_KIT` now paints Coachella's
  jersey (piece 9) navy.
- **Shared ice** (`'shared ice'` experimental): `looks.ice_group` (national 501, DEL 197, EASHL 255; never a group with
  an NHL slot), options the game's own / my picture, the window moves the picture to the saving team.
- **Winter Classic 216-219 / EASHL 2**: `looks.window_team` opens the team whose jerseys they wear, with a note.
- Lab round 38 played it through the program (patched game, docs/notes/lab-round-38.md): Coachella's new kit and hand-
  painted away helmet, a picture crest and a game logo on custom teams (jerseys, menus, centre ice), the national and DEL
  group ice. Not played: unpatched, goalie gear colours. Checks: ROADMAP "Checks of 0.31.0".

**0.30.0 addendum (2026-10-19 evening, not committed; plan docs/plans/ok-new-plan-check-sprightly-dragonfly.md, notes
docs/notes/league-menus.md, lab rounds 35 and 36):** the owner asked for Coachella Valley / Henderson under the AHL, in
the game and in the exe, and overruled rule 2 for them (rule 2 above). Round 36 played it through the program: patched
AHL of 32 named with crests, a Vegas pro, Unpatch + update back to Custom (docs/notes/lab-round-36.md).
- **Turn-back fix**: `PATCHED_TEAM_FIELDS` joins its parts per slot (`_joined`); before, NO_FARM's entry replaced
  Seattle's / Vegas's names and divisions, so a turned-back roster kept them in slots 30 / 31 (since 2026-10-18).
- **Patch 0.21** (`TEAMS_VERSION`): stage Y = 11 words of the front end's created-team gate (`0x128408`) + 5 name caves
  (`NAME_SITES`): a created team whose league is not Custom is listed in its league and named by its art code (CVF /
  HSK). Stage W gains `0x458ec8` (a Seattle / Vegas pro on the NHL roster crashed while loading Be a Pro).
  `tools/audit_patch.py`: 352 words, 0 problems.
- **Roster**: `gamepatch.league_fit` / `unleague` / `check_league_fit`, `LEAGUE_FIELDS` in `PATCHED_TEAM_FIELDS`;
  `verify` allows 234 / 235 between Custom and the AHL's Pacific only (`farm_patch` picks which). `'farm clubs in the AHL'`
  experimental.
- **Names**: `loc.key_hash` uses the game's rule (bytes & 0xdf; the upper-case CRC hid every key with a digit, which
  left 10 clubs blank in Select Teams); `set_select_lines` adds the lines a club lacks; `portraits.names` writes CVF /
  HSK's club texts next to the city key; `NAMES_VERSION` '#6'. Names still need "Photos, logos and team names".
- **Roster editor**: 234 / 235 under AHL only when the roster is for the patched game (`Snapshot(farm_ahl=)`).
- Checks: ROADMAP "Checks of 0.30.0, addendum". The version number stays 0.30.0 until the owner picks one.

**Version 0.30.0 (2026-10-19, not committed; plan docs/plans/the-0-21-0-exe-is-parallel-haven.md):** the owner asked why
only NHL teams could change jerseys, then for gear in team colours, crests for Coachella / Henderson and HUT hidden.
- **Jerseys for every league, per team** (`'jerseys every league'` experimental): the NHL-only lock is gone
  (`app/editor.py` `team_tools.uniforms` / `uniforms_why` from `looks.editable`). `looks.looks_from` is one loop and keys
  every look by art id; edits of clubs are honoured (before, slots 32+ got this season's whatever the player chose).
  "My picture" works in the classic cut (`Maker.cut_files`), "From the colours" only on the shared layout. A club's ice
  edit is refused where the game shows another file (`own_ice`; List of changes "Centre ice not installed").
- **This season's: home and away only** (owner): `looks.pack_versions` has no `third`; NHL thirds are the game's own again.
- **Templates**: "This season's template..." where the pack's colour map fits "My picture" (style 0, or a version on the shared
  layout), next to the game's.
- **Coachella Valley / Henderson crests** (`'own art ids'` experimental; lab round 34, docs/notes/lab-round-34.md): art
  900 / 901 gave a blue square (the game draws custom slots 222-251 from the create-a-team files whatever the art id),
  so `layout.OWN_ART` = 20073 / 20081 on every roster (also the game's own), `clubs.own_kit` writes `OWN_COLOURS` (ttOk)
  and `OWN_KIT` (table `NDEo`, eq 11 = the crest's colours), and `art/crests.py` installs `rendering/czlogo/logoct_72_*` /
  `logoct_80_*` with the photos (weights in `0_tm`, bump / shine maps from the closest of the game's own logos). Played: crests on the
  ice, the jerseys and Select Jerseys, Coachella navy.
- **HUT hidden** (owner, 0.30.0): `menus.DEAD` has `TXT_HUT` in the root menu and in Play (`MENUS_VERSION` '#3'); played.
- **Gear colours** (`'gear colours'` experimental): `Builder.club_gear` (vbHh helmets / gloves of clubs 32-213 in
  colours their club wears; NDEo is left alone), `goalie_gear(mend=)` (goalies in a colour off their club's hues get the
  nearest club colour), `equipment.fix_models` / `model_problems` (models the game draws plain blue, `DRAWABLE`); only
  with update steps, so the Roster editor's edits alone change nothing. tests/test_gear.py.
- **`matching.closest`** (verify's contract check only): a 'last+year' match (last name, birth year within one, first
  initial) gives up a record another person of the same list matches more closely (Aku / Aatu Räty: verify read
  Aatu's deal as Edmonton's and refused the update with NHL.com's rosters of 2026-10-19; 0.21.0 had it too). Doing
  this inside `match` broke the byte-identical second runs (7 tests): the builder's picks stay as they are.
- Version 0.30.0 (owner). Checks: ROADMAP "Checks of 0.30.0".

**Version 0.21.0 (2026-10-18, built and smoke-tested, not committed; plan docs/plans/the-game-patch-is-vectorized-scone.md,
top part):** the owner's review of the 0.20.0 exe. Lab round 33 played it (docs/notes/lab-round-33.md). Left out by the owner "until somebody complains": a jersey hem (Letang) and the
All-Star teams (ROADMAP.md). Checks: ROADMAP "Checks of 0.21.0".
- **Window:**
  - `window/main.fit` / `work_area` / `window_box` open it big and centred (90 % x 94 % of the free screen, at least
    1080 x 780, at most `LARGEST`).
  - Step 2 (patch) moved to the left column. The patched / unpatched result panel is gone; step 2's status line says it
    (`texts.patched_status`, `UNPATCHED`).
  - `.card.rosters` keeps a minimum height (a smaller one at 768 lines while a result shows); the percent shows once.
  - "No pop ups at start" is the label of `LOGIN_ENTRY`'s switch (the entry's name stays).
  - `tools/window_shot.py` draws the window at the size `fit` gives on the screen.
- **Equipment tables count teams as slot + 1** (`vbHh`, `nAUy`, `NDEo`; `sozv` by slot). `Builder.nhl_gear` had painted
  Philadelphia, Washington and Seattle; it now paints 22 / 30 / 31 in `NHL_GEAR` (Utah black, Seattle navy, Vegas gold /
  steel; Vegas's helmet comes out steel grey, as the real one: round 33, docs/notes/equipment.md) and repairs `GEAR_SLIPS` from the game's own roster (`own=`) or the team's colours (`_gear_back`).
  `'nhl gear'` is experimental.
- **Sticks in team colours** (`sticks.py`, `tools/stick_colours.py`): NHL skaters with a stick in a colour their team
  does not wear get a model of the same brand in a team colour, else a plain one. The swap runs in pipeline's NHL step,
  before the edits; `verify` runs `sticks.problems`. `'team sticks'` is experimental.
- **Puck Peak texts** (`loc.PROMO`, docs/notes/promo-texts.md): the game's old offline news panel and the tuner-set notices,
  with the names. Zamboni's news and the HUT banner stay (owner: keep Zamboni's messages and promotions).
  `'puck peak texts'` is experimental.
- **Dead online entries hidden** (`art/menus.py`, docs/notes/menus.md): View Player Hub, Leaderboards and Lobby
  (COMMUNITY) are marked `isHidden` in a loose `fe/ion/game/menus/mainmenuitems.big` made from the player's `boot.big`
  (`install.install_menus`, with the photos). HUT stays (Zamboni serves it, owner 2026-10-18). Lab probe 2026-10-18: the
  game reads the loose file before boot.big, hidden entries leave no gap, the cursor skips them, no crash.
  `'hidden menus'` is experimental.
- **Face of a player shows head pictures** (`app/editor.face_pics_view`, cache.big `createplayer/head/head<id>.big`).

**Version 0.20.0 (2026-10-18, not committed; plan docs/plans/the-game-patch-is-vectorized-scone.md):** the owner's asks
after the step-2 exe. The version jumps to 0.20.0 (the owner's pick: `app/selfupdate.parse_version` compares numbers, so
"0.2.0" would be older than 0.10.4).
- **Line-ups always dress** (the owner's Ottawa failure after Unpatch: NHL.com made MacDermid D a LW and the kept lines
  still had him on defence). `Builder.position_teams`, `nhl_lines` re-deals a team that is changed, had a position
  change or fails `lines.lineup_flaws`; `Builder.repair_lineups` (start of `contracts()`) calls up from the farm or signs
  a free agent when a team cannot dress 2 G / 6 D / its forwards (`call_ups`, `bring_in`; List of changes "called up to
  fill the line-up"); `clubs._feed_position` marks the club changed. tests/test_lineups.py.
- **Select Jerseys from the look pack's own menu pictures** (`teamjerseysxl/jersey_<cut>_<art>_0_<variant>`, format
  0x3c = BC3): the look pack holds `m/<slot>_<role>.webp` (55 MB now), `looks.menu_picture` fits it onto the game's
  figure, `PackKit.menu`, `pack_preview`; the Roster editor's thumbnails use it too (`app/uniforms._thumb`). Socks /
  pants that differ from this season's are listed in the owner's report (not changed in this round).
- **Sharp centre ice and jerseys** (the owner's blocky Utah ring): Pillow's DXT5 encoder never reached a block's end
  alpha values (stair steps, error up to 51) and mixed colour ends (purple blotches). `art/dds.py` re-encodes the poor
  blocks (`colour_block`, `alpha_block`, `encode_level`), mips are alpha-weighted with a 3-px colour bleed (`mipmaps`,
  `bleed`; `Rpsgl.replace(coverage=)`). Utah alpha p99 47 -> 11, colour p99 40 -> 16; about +8 % install time. Lab round
  32 still showed a hatch at the ring's soft edges (partial alpha on the ice), so the centre ice is now **flattened**
  onto the ice colour, every mip opaque or clear (`dds.flatten`, `FLAT_CUT` 64, `mipmaps(flat=)`, `looks.centre_file`
  `flat=ICE`); not seen in the game yet. `LOOKS_DRAWING` '#6'. tests/test_textures.py, docs/notes/centre-ice-quality.md.
- **Utah / Seattle / Vegas arena names on every roster**: the community roster still had Arizona Arena (Glendale) in 22
  and Nashville's arena in 30 / 31 (lab round 32); `Builder.nhl_identity(colours=)` now runs with the NHL step on every
  roster (colours only on the game's own roster; the community's own colours stay). Not seen in the game yet.
  Not done (options): portraits still use Pillow's DXT5 (`install._dds_bytes`), opaque DXT1 jerseys keep Pillow's blocks
  (`rpsgl.OPAQUE_SLACK`), no cache of encoded rasters.
- **Current ratings** for every player the data pack's full list has (`'current ratings'` experimental): data pack part
  `ratings_full` (6,968 players, made in `private/`). `ratings.full_index` / `match_full` (full name + birth, last name +
  birth with a fitting first name, a unique name within a year; goalies only with goalies), `write_full` (`c_*` - 36
  clamped, the biases / fighting / consistency as they are; `schema.FULL_RATED`, `FULL_ASIS`), `Builder.apply_full`
  first, then the ratings list (`ratings_list`), then `estimate.py` (also in `clubs.update_league`, `create_national`,
  `set_position`); type only when it fits the record's class; bio only where NHL.com has none. `verify.rating_problems`;
  verify's mirror check now uses the roster's own layout (`verify.layout_mirrors`). Result "Player ratings: 4612
  current, 573 estimated" (community base). `Builder.feed_letters`: `contract_strays` keeps only the league's own C / A
  letters (a second run moved Coachella's A). Not copied: potential, traits, growth. Options: refit
  `estimate.LEAGUE_GAP` on the full list (estimated players sit 1-2 above rated team-mates in Extraliga, DEL, NL).
  tests/test_full_ratings.py, docs/notes/full-ratings.md.
- **"No online login at start"**: the owner played online through Zamboni with it on; the "leave it off to play online"
  warnings are gone, the switch stays.
- **Promo texts** (main menu tiles, news): docs/notes/promo-texts.md, `tools/find_texts.py`; nothing changed yet, the
  owner writes the Puck Peak words later.

**Game patch as step 2 (2026-10-18, not committed; plan docs/plans/sunny-nibbling-goblet.md, GAME_PATCH.md section 7):**
the owner's wish after the test exe refused the game's own roster ("slot 234 holds only 0 F"). The patch is its own step
2 (Patch / Unpatch, the two switches, applied at once while patched); every update follows RPCS3 (patched: a patch roster
from any roster; not patched: a normal one, a patch roster is turned back with `gamepatch.unpatch_roster`); the game's own
roster gets Coachella Valley / Henderson from the AHL data and Vegas its depth. Tests green (322); lab played
2026-10-18 (GAME_PATCH.md section 7: own roster + patch, Be a GM Seattle / Vegas to 15 Nov; turned back and played
unpatched; community regression).

**Data of 2026-27 (2026-10-16, not committed; plan docs/plans/is-it-possible-to-jaunty-dongarra.md, private/NOTES.md):**
player type and face in the Roster editor (types named in the lab, `'type and face edits'` experimental); **real 2026-27
contracts** (data pack part `contracts`, `'contracts'` experimental; real dollars on a patch roster, x 71.4 / 104.0
otherwise; the result has a "Contracts" line; the 82 players under contract whom NHL.com's roster copy leaves out stay
with their team, notes contracts.md). **Stage X v2** (patch 0.20, `CAP_TABLE`): the real cap by season (2026-27
$104.0M, 2027-28 $113.5M, 2028-29 $127.5M, then held; floor, lowest and rookie maximum too; notes salary-cap.md) and the
year entry 0.8 (Contract Status columns "26-27"); lab round 30 played both through season 2's start. **This season's
jerseys** (the look pack, round 2, 2026-10-17; 214 teams, made in `private/`): `art/lookpack.py`, `looks.pack_team` /
`kit_palette` (style 1 and style 0), installed with the photos; **lab round 31 done** (a home game in every league but
the QMJHL; install 18 min, 834 MB per game version). The centre-ice file a home game shows depends on the league (NHL /
DEL: the arena's, national teams: 501, others: the team's own; `looks.shown_centre`, `own_ice`), so DEL clubs and
national teams keep the game's own ice. Loading hangs in SHL home games are RPCS3's / the game's own (also with nothing
of ours installed). MAINTAINING.md "The look pack".

**Game patch (2026-10-15, not committed, nothing published; docs/GAME_PATCH.md, plans docs/plans/fluffy-dazzling-scone.md,
this-was-written-from-stateful-bee.md):** the year 2026 and 32 teams in Season / Be a GM / Be a Pro, patch 0.19 (stages A-X), year 0.7, plus two
optional intro entries.
**84 games (0.14, rounds 18-20):** the real 2026-27 calendar (1,344 games + the All-Star row); the game sets a roster
calendar's room itself (1,291 rows, data table `0x1acc878`), stage S raises it to 1,345, so the patch roster's save is 864
bytes longer (`gamepatch.SECTION_SIZE`, `section_fit`; with S on a normal roster "appears to be damaged"). A new Be a GM
holds 32 x 84 and played a whole season with 84 GP for all 32, the playoffs, the June 2027 draft and season 2's calendar of
32 x 84 (round 20). **Stage T (0.15, round 21):** season 2's preseason crashed (the team rankings of 17 stats have room for
30 teams; `RANK_ROOM`); each ranking now keeps 30. **Rounds 21-22:** season 2 played to the end, 84 GP for all 32, the
playoffs; one hang in a computer team's game (25 Jan 2028, the engine's lineup for Vegas held strangers and empty places)
did not come back on a replay (GAME_PATCH.md section 6). **Stage U (0.16, round 22):** the second draft (June 2028) crashed:
the game keyed each year's picks for 30 teams, so a new year overwrote 14 first-round picks of the next draft; the keys are
now (year mod 6) x 224 + pick (`PICKS_PER_YEAR`); only a Season / Be a GM started with 0.16 has them. What 2026-27 still lacks: docs/notes/2026-27-gaps.md. Lab rounds 12-17 were played by the agent with a scratch
driver (docs/notes/autoplay.md; the owner asked not to be asked to test): 32 NHL + 32 AHL with their real parents, the All-Star
game (EASHL 1 / 2 with art 30 / 31, `ALL_STAR_RINK`), Seattle's call-ups (stage O), the trade deadline, the end of the season,
a 16-team bracket. A reloaded Vegas Season lost its team (the human-team mask `leaguestates.value` had 31 bits): fixed by
`META_MASKS` (32 bits in the db files), confirmed in the lab. Be a GM with Vegas (rounds 14-17): a full season, the playoffs,
the draft of 32 (stage K), the off-season; fixed: Seattle / Vegas roster upkeep loops (P), a season-2 crash in the game-day step
(Q), season 2's calendar left Anaheim / Calgary without games (R + the roster's `byED` = the 2026-27 calendar,
`gamepatch.future_fit`; confirmed: 32 x 80 NHL, 32 x 72 AHL). A human team under the roster minimum hangs its first game (the
game's own rule: call up / sign first). Run 17: season 2 to late October, a Vegas send-down / call-up, Save and Exit: no crash.
**Rounds 23-26 (2026-10-15):** stage U held through the June 2027 draft; at season 2's new year (13 Sep 2027) the computer
teams took stars off their NHL rows. Patch off (round 24) they did not: the computer GMs count ages from the league's own year
(2015), so **year 0.6** stores patch-roster birth years as real - 1911 (`year_shift`) and adds 11 back in the two date ages
(`0x1631e4`, `0x372008`). With right ages (round 25) four computer teams still sent 10-17 NHL players each to the farm at the new
year; round 26 (the year entry alone) did not. **Round 27 (full patch, Be a GM with Anaheim, 2026-10-15), all fixed and
played:** (1) computer-run Seattle / Vegas got no call-ups (the roster planner counted keys 30 / 31 as non-NHL), Vegas ran
short and a sim hung: **stage V** (0.17); (2) the stars on the farm came from the calendar's timing: with the real 29 Sep
opener season 2's preseason began before the game's fixed new year (11 Sep), its first day was not counted and the final
roster cut (`0x1ca618` mode 7) never ran; `future_fit` now stores the next seasons' calendar **a week later**
(`FUTURE_DAYS`), season 2 opens on 6 Oct and all 31 computer teams get the cut (run E7: 0 teams lost a third of their NHL
pay, 6 before; docs/notes/gm-brain.md, GAME_PATCH.md row 27). (3) **Intro skip** (owner's wish): two optional entries in
`patch_text`, `INTRO_ENTRY` (the game's own quick boot + no autosave notice: Press Start at once, one press to the main
menu) and `LOGIN_ENTRY` (no online login at boot; online modes still sign in when opened: the owner played through Zamboni with it on, 2026-10-18), played in the lab (docs/notes/intro-skip.md).
Also fixed: `donors.real_birth_year` made 75 community-updated undrafted records
(Krug, Goodrow) ten years older (now it needs `TNEo` at 12 or younger); this also touched the normal update.
**Round 28 (2026-10-16, docs/notes/be-a-pro.md):** season 2 to the June 2028 draft played (84 GP, all 7 rounds, no hang).
Be a Pro: Edmonton played; a Seattle prospect crashed while loading: **year 0.7** gives a new career's job list room for 16
(`0x33a4d0`; the year entry adds a 9th job), **stage W** (0.18) lets the "which team is this player on" query see keys 60-63
(Coachella Valley / Henderson) plus six Be a Pro compares; the career then loads, saves and plays. `gamepatch.NAMES_2026`
names slots 22 / 30 / 31 in the patch roster's team table (Be a Pro said "GREEN / RED organization"). Plain Season mode with
Vegas: 84 GP for all 32, the playoffs, the Cup (no crash). **Still to play:** the rare engine hang (rounds 21 / 23, not seen since). **The owner releases nothing until 32 NHL + 32 AHL + the All-Stars work, with 84
games.** **Phase D (2026-10-15, built, tests green, NOT played through the exe, not committed; plan
docs/plans/zazzy-leaping-stearns.md, GAME_PATCH.md section 7):** the window's row "32 teams and the year 2026 (game patch)"
(question first, "Skip the intro" / "No online login at start", Unpatch), `update --game-patch`, `game-patch status|remove`;
EU and NA. Next: the lab check through the exe (section 7, "To play"), then build and the owner's go-ahead. Later, the
owner's picks: the 2026-27 salary cap, 3-on-3 overtime.

Version 0.10.3 (2026-10-13, from the owner's tests of 0.10.2; plan: docs/plans/we-are-fixing-bugs-tidy-treehouse.md): **old window stuck after
"Update now"** fixed (`UpdateController.quitting`: `closing()` lets the window go once the new exe runs; `WebHost.quit` ends the process after
3 s; the new exe ends a stuck `<exe>.old` copy at start, `savedata.end_process_of`). **Equipment uses the game's menu words** (`equipment.OPTIONS`:
jersey tuck None/Left/Right/Full, sock tuck None/Front/Back/Full, tape 10 colours) and has visor tint, shoulder pads, pant length
(`CHOICES`, `NEW_PLAYER` defaults for created players); skaters have no neck guard field. Equipment / Jerseys-and-ice windows cover the logo
too (`.modal-back.full` fixed). `cli equipment-test` (`equipmenttest.py`) = the owner's in-game check of the numbers: NOT played yet.
Open: why Front / Back showed nothing in the game (probably the owner looked at Edit Pro, see docs/notes/equipment.md).

Version 0.10.2 (2026-10-12, from testers of 0.10.1; plan: docs/plans/i-got-some-bugs-polished-flamingo.md): **"Green / Red has 0 captain(s)"**
fixed: `edits._move` refuses a move that leaves a team that could dress 20 without 2 goalies / 18 skaters (`_too_few_without`; the editor says so
at Apply: `EditorController.too_few_without`), `_relines` keeps the letters when a team cannot dress, `verify` names slots 30 / 31 Seattle /
Vegas. **Equipment lists only models with a 3D picture on the disc** (`equipment.available`, `app/equipment._usable`: cacherender.big
file names; ids the roster already holds stay; NHL 10-14 models drew blue). **Equipment and Jerseys-and-ice windows fill the window**
(`Modal full`). **`stock.disc_icon`** takes any `ICON0.PNG` of the game folder, else the program's own picture. **Editor shows the player
type** (`ratings.STYLES`; 5 GRN, 6 PLY, 7 SNP, 8 PWF, 9 TWF, defence 1-4 unnamed); **the game's own OVR is NOT reproduced** (formula is in the
game program, `FUWe` is not it): research and next steps in docs/notes/overall.md. Not played in the game yet: helmet ids read from the
file names (`rendering/helmet/...`), goalie pads 85-88 have no file on the EU disc but are worn by 44 goalies (kept: worn ids stay).

Version 0.10.1 (2026-10-11, hotfix): European clubs' short codes are three plain letters (Frölunda FRO, Färjestad FAR, Davos DAV ...): `abbr` in `tools/club_slots.json` for SHL, Liiga, Extraliga, DEL, National League, Norway (AHL / CHL unchanged), data pack rebuilt (only `abbr` fields differ), `build_datapack.short_code` for left-out clubs. Reaches a roster on the next update with "Photos, logos and team names" on (the names hash includes the code). Not checked in the game yet.

Version 0.10.0 addendum (2026-10-11 evening, owner's testers): **Start RPCS3** really fixed: `savedata.launch()` also clears the
exe launcher's `SetDllDirectory` (the child inherited it; 0.10.0's first fix only cleaned PATH): NOT tried by the owner yet; if
the error stays, remove the buttons. **Equipment editor** (skaters): `equipment.py` (table `ajmx`, the choices), `app/equipment.py`
+ `web/js/editor.js` `EquipmentWindow` (the game's menu pictures from the disc, `cache.big` `createplayer/...`), edits.json
`equipment` per player and per team (`edits._set_equipment`, `_team_equipment`; a player's own choice wins over his team's);
research in docs/notes/equipment.md. Waiting for the owner: do the tuck / tape numbers match the labels (`equipment.OPTIONS`),
does the game show the stick / helmet / gloves; own equipment pictures (`rendering/glove/feglove_*`) not built (owner dropped them).
**Goalies** (same evening): `equipment.GOALIE_CHOICES` (table `lVMf`: mask, pads, blocker, trapper, stick, tape, tuck, neck) in the same window;
`mask_picture` edit: the goalie gets a mask number nobody wears (`edits._mask_picture`, reuses his own when he is its only wearer, so a
second run changes nothing) and `art/masks.py` writes the picture into `rendering/goaliehelmet/goaliehelmet_0_<n>_cm.rpsgl` (512x512 DXT1)
as a loose file with the photos (`pipeline.install_masks`). **NOT played**: does the game read the loose mask texture and does maskid
map to that file name (assumed; masktype 0 = 280 files, ids 234-245 have none). Goalie jersey = the team's jersey (Jerseys and ice).

Version 0.10.0 (2026-10-11, built, NOT committed, waiting for the owner's check): **the new window.** The CustomTkinter
window tore and redrew while it was moved or resized; it is replaced by a web page in a native window (pywebview: Edge
WebView2 on Windows, WebKit on Mac / Linux) in the look of the game's menus (the owner's Claude Design proposal + the game's
stadium blue, arcs and Help bar; Puck Peak logo kept). Plan: docs/plans/look-at-the-ux-ui-gleaming-noodle.md.
- Python holds all state (`app/` controllers, tested without a window: tests/test_app.py); the page only shows the JSON it
  is sent (`window/host.py`, at most 25 Hz) and calls `window/api.py`. Both tabs, Jerseys and ice, My edits, the Team
  window, questions (Delete, Restore default, close while busy) are in-page windows; file pickers are the system's own.
- The old window stays for 0.10.x: `--classic`, and used by itself when WebView2 / pywebview is missing or fails
  (logged in error.log). Delete it in 0.11.
- `tools/window_shot.py` now draws the page with headless Edge from the real controllers' state (`--live` for the
  real window). `editor/card.py`: ratings below 40 that the game's own roster has (Faceoffs 35) no longer block Apply.
- **Also in 0.10.0 (2026-10-11, from testers of 0.9.0; exe rebuilt with all of it, starts, tests 218 passed with the EU disc in
  `LEGACY_ROSTER_DISC`; NOT played in the game yet).** Plan: docs/plans/please-check-and-propose-fizzy-snowglobe.md.
  - *Fixed, waiting for the owner's check:* scoreboard short codes (`loc.apply_names` writes `X_XLA_TEAM_` / `Abbr3_` also when the
    full name matches; `NAMES_VERSION` '#5'; needs "Photos, logos and team names"); top-left logos centred
    (`images._crop_centred`, `LOGO_DRAWING` '#5'); Utah jersey shine map flattened (`looks.jersey_file`); helmet logo decals
    (`looks.decal_file`); helmet / gear colours of Utah, Seattle, Vegas (`builder.nhl_gear`, table `vbHh`, runs with the NHL step);
    Utah's rink picture `icesurface_22_bm` (`looks.ice_picture_file`); **Start RPCS3 from the tool** no longer fails with
    "vcruntime140.dll incorrectly installed" (`savedata.clean_environment`: the exe's `_MEI` folder was in RPCS3's DLL path; the
    fix is in the rebuilt exe, still to try by the owner).
  - *Already fixed earlier (0.9.2):* "Russia dresses 5 D" safety failure (`builder.fill_empty_national`, `room_for`); testers
    should use 0.9.2+.
  - *Open, not built:* Seattle / Vegas home ice (they share Nashville's arena art 16; arena art 30 / 31 files are incomplete, see
    docs/CALENDAR_AND_LOOK.md 2b); the helmet reflection cube map `enviro/helmet_<art>` still shows Arizona's ice; per-team ice size
    NHL / European (no field known; `exhibitionarena.arenatype` / `bouncemap` are the only candidates; owner: research later);
    Seattle / Vegas helmet colour mapping is a heuristic (`nhl_gear`).
  - Tests that need the disc: `$env:LEGACY_ROSTER_DISC` = the EU iso (where the owner keeps it:
    private/NOTES.md; read only). `.venv` has no pytest; run tests with `python`, pictures with `.venv\Scripts\python.exe`.
- **To check (owner):** move / resize the window while an update runs (smooth?), every button of both tabs, the size of
  the exe, and on a PC without WebView2 if possible. Nothing in the save changes.

Version 0.9.3 (2026-10-11, built, NOT committed; owner will do a UX/UI and logic redesign first): fixes from testers. Read
[docs/HANDOVER.md](docs/HANDOVER.md) and [docs/notes/select-teams-crash.md](docs/notes/select-teams-crash.md) first.
- **Select Teams crash on switching league** (SHL, Extraliga, AHL): most likely the program wrote empty team-name lines as texts of
  length 0 (the game's files never do; `loc.LocFile.set/set_existing` now mark an empty text absent) and over-long texts
  (`loc.fit`, `limits`, `select_lines`, `install_names` check; `NAMES_VERSION '#4'`). **Not confirmed in the game yet.**
- **Restore default** now starts from the game disc (`restore.default_slot`); before it took the updated roster as its own default.
- **Roster editor ratings:** unapplied card is applied on Save / player switch; national-team copy gets the same edits.
- **No roster / game not in RPCS3's list:** "Pick the game" buttons, `cli --game`, `savedata.NoGameError`, first save `...01`.
- **Draft step** skips placeholder records with impossible birth years (tester error "273 does not fit in 8 bits").

Version 0.9.1 (2026-10-07): **Restore.** `restore.py` (`default_slot`: the version's `...0200` save when `check_base` says it is the game's own
roster, else the disc; `copy_calendar`), `pipeline.update(restore_parts=, default=)` (ROSTERS: start from the default, written as it is when no step
is left; CALENDAR: copy `ihmS`/`Iwiq`, `verify(calendar_source=)`; PICTURES: `art.install.remove`), a Restore button per row (`widgets.SwitchRow(restore=)`,
`App.toggle_restore`) and the big **Restore default** (`App.restore_default`). The default is only read. Not built: balancing games played per team
(the 30-team calendar gives 76-80), per-kind picture removal (names / jerseys separately), equipment (docs: plan not built).

Version 0.9.0 (released 2026-10-07; CHANGELOG.md has the players' version), from the owner's tests of 0.8.1 on 2026-10-06:
- **Calendar 2026-27: confirmed in the game** (all four CAL tests matched NHL.com), now a normal step, on by default, 30 teams.
  The game's year label stays 2015 (not in any data file; owner: leave it). Seattle and Vegas cannot be in Season mode / Be a GM.
- **Loose 3D textures: confirmed** (`cli rendering-test`). **New, not played yet:** the real Utah / Seattle / Vegas jerseys, pants,
  socks, number sheets, Select Jerseys pictures and centre-ice logos (`art/looks.py`, installed with "Photos, logos and team names":
  `pipeline.install_looks`; `cli looks-test` writes only them), the Roster editor's **Jerseys and ice...** window for the 32 NHL teams
  (`editor/uniforms.py`; edits.json `uniforms` / `ice`), and **Export only SYS-DATA roster** (`pipeline.export_sysdata`, `cli export-roster`;
  for a PC without RPCS3). Docs/CALENDAR_AND_LOOK.md says what to check in the game and what is not built (extra jersey versions,
  old-layout versions from colours, the Jets throwbacks and old All-Star versions stay the game's own).

Version 0.8.1 (released 2026-10-06; CHANGELOG.md has the players' version): the owner's tests of 0.8.0 in the
game, in two rounds. **Confirmed in the game by the owner (2026-10-06):** the Tampa Bay and Toronto logos, the
Select Teams names (Utah Mammoth, Seattle Kraken, Vegas Golden Knights), Delete / Open folder, and Season mode
with the full update. **Still to be checked in the game** (ROADMAP "Round 3" rows): update in place (which roster
the game loads at boot), re-updating a roster made by 0.8.0, the Roster editor's save, the arena names and colours of
the game's own roster, and the **calendar 2026-27, the loose 3D textures (jerseys, ice) and the new jerseys / ice
logos, which the owner tests in a separate session: read docs/CALENDAR_AND_LOOK.md**.
First round:
- **Window:** every roster in step 2 has **Open folder** and **Delete** (`widgets.RosterRow`,
  `App.ask_delete` / `delete_save` / `open_save`, `savedata.trash_save`); `tools/window_shot.py delete`.
- **Logos:** the pictures with a white edge (`t`, `d`, `r`) are drawn from ESPN's plain logo
  (`install.EDGED_KINDS`, `plain_logo_url`), the others from the dark one; `LOGO_DRAWING` '#3';
  the photo pack was rebuilt with the 32 plain logos (kept out of git).
- **Team names:** Select Teams reads `TEAMLINE1/2_X`, `NICKLINE2_X`, `NHLTeamName_Abbr3_X` and the NHL
  slots' numbered texts, which `art/loc.py` now writes (`set_existing`, `set_select_lines`,
  `NAMES_VERSION`; FORMAT.md section 7). All three wait for the in-game check (ROADMAP).
Second round (evening):
- **Logos/names did not change in the game because the new code had never been installed** (the owner ran the
  0.8.0 exe; `installed.json` still had `#2`): after running the new exe with "Photos, logos and team names" on they
  were right. Calendar (`c`) and wide (`w`) logos now also take the plain logo where the dark one is a
  white silhouette and the game's own picture is coloured (Toronto; `LOGO_DRAWING` '#4').
- **Update in place** (default) or save as new: `savedata.update_in_place`, `pipeline.update(in_place=True)`,
  `cli update --in-place`, window card 4 and the editor's save bar share `App.save_mode`.
- **Roster editor** has one view (no As is / To be): the picked roster as it is plus this visit's edits.
- **Calendar 2026-27** (`schedule.py`, step `schedule`, OFF by default, `pipeline.EXPERIMENTAL`): written, tested
  offline, **not played yet** (`cli calendar-test`: CAL 1-4; hand-over in docs/CALENDAR_AND_LOOK.md).
- **Utah/Seattle/Vegas look, ice logo, jerseys**: `art/rpsgl.py` reads and rewrites the game's `.rpsgl` textures
  (byte-identical repack); `cli rendering-test` is the one in-game test (loose `rendering` files, never tried);
  `builder.nhl_identity` gives the game's own roster Utah's/Seattle's/Vegas's arenas and colours (the community
  roster has them). Real jerseys and centre-ice logos wait for the test (docs/CALENDAR_AND_LOOK.md).
- **Season mode crash: fixed** (owner played `season-test` rosters 1-4, the full update, 2026-10-06). The
  community roster names a removed player (Drouin) in two table headers and our update made him a free
  agent; `builder.drop_removed_player` removes him first, `verify.py` checks the header words; a roster
  made by 0.8.0 (stale markers) gets its free agents relinked (`Builder.relink_free_agents`, not played
  yet). `cli season-test` (`seasontest.py`) stays as the owner's check for sizes and regressions.

Version 0.8.0 (released 2026-10-05; CHANGELOG.md has the players' version): the testers' feedback on 0.7.0, with the
owner's decisions (ROADMAP.md, "Decisions taken ... testers' feedback"). Everything waits for the
in-game check (`pipeline.EXPERIMENTAL`: 'free agents', 'goalie gear', 'draft', 'own teams'):
- **Free agents:** `builder.would_retire` (retire_age: 30 on the game's own roster, 35 otherwise;
  never who played in the NHL last season, is on an NHL.com roster or is listed by a league or an
  IIHF squad). `settle_free_agents` retires old free agents, `add_unsigned` makes last season's
  unsigned NHL players free agents (created if missing). Data pack part `nhl_last`
  (`tools/providers/nhl_facts.py`). The game's own roster rebuilds its 2014 national teams on the
  first update (`clear_national`). All retirements happen before any player is created
  (DEVELOPING.md lists what breaks a byte-identical second run).
- **Real player data:** `draft.py` (data pack `drafts`, every pick since 2005) for every record,
  NHL.com's height, weight, hand and birthplace for every NHL player (`nhl_bio`). Name matching:
  full-name matches need a fitting birth year, namesakes go by the closest one, the DEL's age-only
  match accepts Nico / Nicolas.
- **Logos** in the game's own sizes (`images.LOGO_BOX`), ESPN's dark-background NHL logos,
  `install.LOGO_DRAWING` redraws installed logos once. Photo pack rebuilt.
- **Goalie gear** repainted in the new club's colours (`Builder.goalie_gear`, table `lVMf`).
- **Own teams:** a player's custom team named after a left-out club gets its players
  (`clubs.own_teams`, data pack `leagues.<key>.extra`); `stock.is_stock` no longer trips over one.
- Skipped pictures are named in the List of changes (`pipeline.note_skipped`); the Roster editor
  reads the unprepared disc roster's birth years right.
- After the owner's own test (2026-10-04/05):
  - players under 20 whom their league's list leaves out stay with their club (`clubs.STAY_AGE`,
    DuPont);
  - undrafted prospects of the next drafts (draft year still to come, round 0) in prospect pools, on
    the free-agent list or on no team join a real club of their country's league (`clubs.HOME_LEAGUE`,
    the CHL for the rest) inside that league's step (`_place_prospects`), as the game's own roster keeps its
    draft classes; `cli draft-test` (`art/lab.draft_lab`) remains to check where the draft looks;
  - pictures: Extraliga photos from hokej.cz's player pages (`tools/providers/czech.py`), last
    season's AHL/CHL photos for players this season's lists leave out (league `former`,
    `Builder.former_photos`); the National League publishes none;
  - the window keeps every step in view when the result shows (the big logo folds, the result's
    lines scroll: `App.fit_banner`, `compact_header`), and the cards have more contrast;
  - macOS and Linux: `savedata` finds RPCS3's data folder there (`data_folders`, `is_program`,
    `open_path`, `_running_posix`), `datasource.data_home`, `packaging/build.sh`,
    `.github/workflows/build.yml` (tests on three systems, Mac and Linux builds). Not tried on a real
    Mac or Linux PC yet.
  - without RPCS3 (a tester on a Mac in CrossOver): step 1 also takes a folder with roster saves
    (`savedata.SaveFolder`, `open_saves`; since 0.9.0 the window has the checkbox "Export only SYS-DATA roster" instead of the link:
    `pipeline.export_sysdata`, `cli export-roster`, docs/ARCHITECTURE.md "Without RPCS3"); photos and
    the game's own roster are not offered then.
  - Season mode crash: fixed for a roster updated from the community roster (ROADMAP "Season mode crash"); re-updating a roster made by 0.8.0 still to be played.

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
