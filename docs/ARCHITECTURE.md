# How the updater works

This is the map of the program: what the exe is, what happens between "Update roster" and the
new save, where each decision lives in the code, and where new features plug in. The save
format itself is in [FORMAT.md](FORMAT.md); how to build, test and change things is in
[DEVELOPING.md](DEVELOPING.md); data refreshes and releases are in [MAINTAINING.md](MAINTAINING.md).

## In one paragraph

The user's RPCS3 holds roster saves of NHL Legacy Edition. The program reads one of them,
fetches today's NHL rosters from NHL.com, takes everything else (EA ratings, national teams,
European club rosters) from a bundled "data pack", rewrites the roster database in memory,
checks the result against every rule the game is known to enforce, and writes it as a **new**
save folder next to the old ones. It changes an existing save only when the player chooses "Update this roster" (a backup copy first,
`savedata.update_in_place`), and never deletes one by itself (the player's own **Delete** button in the window moves one to the
Recycle Bin, `savedata.trash_save`), never adds a
team and never moves a team to another league (hard limits of the game).

```
 NHLLegacyRosterUpdater.exe ──► gui.py (window)  ─┐
 NHLLegacyRosterUpdater-cli.exe ► cli.py ─────────┤
                                                  ▼
                                    pipeline.update()
          ┌──────────────┬──────────────┬─────────┴────────┬───────────────┐
          ▼              ▼              ▼                  ▼               ▼
     savedata.py    datasource.py   pipeline.build()   verify.py      savedata.install()
     find RPCS3,    NHL.com live,   Builder steps:     every rule     new folder
     list rosters   data pack       NHL, ratings,      the game       <TITLEID>02NN
                                    leagues, national  enforces
                                          │
                     roster.py / tdb.py (read + write the save), layout.py (team slots)
```

## The two programs

| File | Built from | What it is |
|---|---|---|
| `NHLLegacyRosterUpdater.exe` | `packaging/launcher.py` | The window, with `legacy_roster/data/photopack.zip` inside: every photo and logo already drawn (see "Photos and logos"). `legacy_roster.__main__.main()` opens the window when started without arguments and runs the command line when given some (but as a windowed program it has no console to print to). Since 0.6.0 the only window program (owner, 2026-10-04): 0.4–0.5 also had a plain one without the pictures. |
| `NHLLegacyRosterUpdater-cli.exe` | `packaging/launcher_cli.py` | The command line (`list`, `update`, `export`, `photos`), with a console. Built without Tk. |

Both are PyInstaller **one-file** builds (`packaging/build.ps1`). On every start the exe unpacks
Python, the `legacy_roster` package and `legacy_roster/data/` into a temporary `_MEI…` folder, so
the window takes about 3 seconds to appear. Code finds its files through `__file__`
(`theme.DATA`, `datasource.BUNDLED_PACK`), which works the same from source and from the exe.
The exe is not signed, so Windows SmartScreen warns on first start.

Dependencies: the engine and the command line use only the Python standard library, except
"Photos and logos", which draws pictures with Pillow (`art/images.py`, imported only when the
switch is on; both exes carry it). The window adds
[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) on top of tkinter. PyInstaller is
used only to build.

## Without RPCS3

`savedata.SaveFolder` stands in for an RPCS3 when the player picks a folder with roster saves (or
one roster save) instead: the window's link under step 1, or a remembered path that is no RPCS3
(`App.set_rpcs3` falls back to `savedata.open_saves`). It has the save folder and the versions
found there, but no game folder and no game disc, so the photos switch is off, "The game's own
roster" is not listed and there is no "Start RPCS3". The new roster goes next to the others
(`savedata.install`). For a tester running the Windows exe in CrossOver with the Mac RPCS3 (0.8.0).

## What happens when the user presses "Update roster"

1. **Window** (`gui.App.start`): locks the controls, then runs `App.work` in a worker thread.
   The worker never touches Tk. Every message the engine reports goes into a `queue.Queue`;
   `App.poll` (every 100 ms on the Tk thread) writes it to the details log and the status line and
   turns it into a percentage with `progress.fraction()`.
2. **`pipeline.update(savedata, source_folder, steps, name, progress)`**:
   1. `savedata.find_savedata()` and `list_rosters()` → the source roster (`savedata.Slot`), or
      `disc=` a `savedata.DiscSlot`: the game's own roster (section "The game's own roster").
   2. Reads its `SYS-DATA` (`savedata.read_roster`; for a DiscSlot `stock.from_disc`).
   3. `datasource.load_pack()` → the newest data pack: a downloaded one (only if `PACK_URL` is
      set), the cached download, or the copy bundled in the exe. "Newest" = highest `generated`.
   4. `layout.check_base()` → the layout: `COMMUNITY` or `STOCK` (the game's own); refuses any
      other team layout with a message the player can act on. Community rosters whose custom
      copies of NHL teams are out of step (the community's 2026-27 roster) pass: a copy is
      recognised by its name (`MIRROR_NAMES`) or by sharing most players with its team.
   5. `datasource.gather()` → a `builder.Data`: NHL.com rosters (32 requests, cached 20 minutes),
      players those rosters leave out (injured, reassigned: player search + landing page,
      cached 6 hours), and the parts of the pack the chosen steps need.
   6. `pipeline.build()` → runs the steps (next section) and `verify()`.
   7. Any problem from `verify()` → writes `reports\failed_<time>.csv` and returns; **nothing is
      saved**.
   8. `savedata.install()` → the next free folder `<TITLEID>02NN`, once per version of the game
      in `targets` (EU `BLES02153`, NA `BLUS31540`; default: the source's version). `ICON0.PNG`
      and `PARAM.SFO` are copied from the source save with a new `SAVEDATA_DIRECTORY` and
      `SUB_TITLE` (the roster name); for the other version they come from that version's newest
      roster save, else from the source with that version's `TITLE` (`savedata._model_for`).
      Starting from the game's own roster with no save of that version at all: `PARAM.SFO` is
      made from scratch (`savedata.roster_sfo`, byte-identical to the game's own) and the icon
      is the disc's `PS3_GAME/ICON0.PNG` (`stock.disc_icon`).
      Then `SYS-DATA` is written and read back. The folder is assembled next to `savedata` and
      renamed in, so the game never sees half a save.
   9. Writes the list of changes (`write_report`): `reports\<folder>_<time>.html`, a page grouped
      by part and team with full team names and a search box (`report.py`), which "List of
      changes" opens, and the same rows as `.csv` next to it.
   10. With "Photos and logos" on: installs the pictures (section "Photos and logos").
3. **Result**: `App.report` shows the green banner: one line per part of the update
   (`BuildResult.lines()`, in two columns when there are many), the photos line, how to load it in
   the game, and the buttons. `App.failed` shows the red one.

The command line runs the same `pipeline.update()`; `--dry-run` stops before step 8.

## The engine: `pipeline.build()`

Steps run in this fixed order, whatever order they are given in:

| # | Step key | Code | What it does |
|---|---|---|---|
| 0 | – | `Roster(src)`, `check_base`, `stock.prepare` (game's own roster only), `draft.apply`, `Builder(R, data, layout=)`, `reserve_listed` | Parse, check the layout, write everyone's real draft (0.8.0, `draft.py`), index entries, links and ratings, detect maintain mode, prepare donors. The club leagues are worked out here (`usable_clubs`, `with_own_teams`: a player's own custom team named after a left-out club joins its league), and the players they and the IIHF squads list are reserved (`b.listed_rows`: never reused, never retired). Every change-log row is tagged with its part (`builder.ChangeLog`, `log.section`) |
| 1 | `nhl` | `Builder.nhl_rosters()` | (Game's own roster, first update: its 2014 national teams are emptied, `clear_national`.) Free agents who `would_retire` retire first (`settle_free_agents`, 0.8.0). Players on no official NHL roster leave their NHL entry (free agent unless still on another pro team; one who `would_retire` retires: `Builder.retires`). Every listed player goes onto his team: his entry there, his entry moved from another NHL team, an AHL/pool/junior entry promoted (`source_rank`), a new entry, or a new player record (`create_player`). A matched skater gets NHL.com's position (`nhl_position`, 0.6.0), and one matched without his birthdate gets NHL.com's (`nhl_birthdate`); every NHL player gets NHL.com's height, weight, hand and birthplace (`nhl_bio`, 0.8.0). Then last season's NHL players who are unsigned now become free agents, created if the save lacks them (`add_unsigned`, data pack `nhl_last`). Jersey numbers from NHL.com; a clash goes to the official number, then to whoever already wears it, then to the better player, and the loser keeps his old number so a re-run changes nothing |
| 2 | `ratings` | `Builder.apply_ea_ratings()` | EA attributes written exactly: stored = rating − 36, field per attribute in `schema.EA_SKATER` / `EA_GOALIE`. Players with only an overall are shifted until their level matches it. Fields EA does not publish (potential, growth, traits) are left alone. Rated players go into `b.ea_rated`. Then `donors.refresh()` chooses the spare records again with the new ratings (a retired player EA still rates can drop below the legend line; a second run must find the same spares) |
| 3 | `nhl` | `nhl_lines()`, `sync_mirrors()` | Departed players' line slots and letters go to newcomers, then lines are re-dealt by rating within each team's own structure (a team without one gets `lines_from_scratch`). A slot set's class comes from its even-strength slots (`lines.slot_role`), and a wing's set goes to a winger of its side first (`lines.wing_side`, unless the other side's winger is `lines.SIDE_MARGIN` better). Custom teams 222–233 are made identical copies of their NHL team (`Builder.mirrors`: none on the game's own roster); a player who was only on the copy becomes a free agent |
| 4 | `national` | `fill_empty_national()` | Fills every national team the source leaves empty (the base's 8, and squads a community roster emptied): the IIHF roster, NHL players by nationality, then the country's players elsewhere in the save where positions are short; at most 26. A country that cannot dress 2 G + 18 skaters stays empty (summary line). Runs before the club leagues because its new players need records, and the junior leagues, last in line, are the ones that run short |
| 5 | league keys | `stock.retire_leftovers()` (every roster since 0.8.0), `clubs.core_needs()`, then `leagues/clubs.update_league()` per league in `pipeline.LEAGUE_ORDER` | Club names on the slots (not on a player's own team, `own`); players matched (`match_club`) or created; old players the league no longer lists retire before any of this (`retire_leftovers`); former occupants become free agents; displaced prospect pools move to spare slots (`pools.relocate`); short clubs topped up to a dressable 20 (`_fill_lineup`); numbers, lines (`lines.build_lines`), letters. Records for later leagues' line-ups are held back from depth players (`b.core_reserve`) |
| 6 | (any league) | `leagues/pools.settle()` | Pool slots trimmed to 40, best prospects kept, overflow moved to pools with room or made free agents; lines for changed pools |
| 7 | `national` | `national_teams()`, `national_lines()` | Keeps national squads current: a member no longer active in the NHL makes room for the best eligible NHL player of his position (eligible = the save's nationality and NHL.com's birth country agree). Places of members who retired in this run are filled the same way (`national_gaps`). On a first build, up to 4 rising stars (24 or younger) per team replace the weakest member who would not retire; not in maintain mode and not for squads filled in step 4. Removed players with no club become free agents. A squad with players but no line slots (Czech Republic and Denmark in the 2026-27 community roster) gets lines dealt from scratch |
| 7b | always | `goalie_gear()` | A goalie whose club changed (or a new one) gets the coloured parts of his pads, blocker and glove (`lVMf`) in the club's colours; white, grey and black stay (0.8.0) |
| 8 | always | `contracts()` | Contract team (`cPbu.team` = team + 1) must be a team the player is on; free agents have no contract fields (their NHL rights in `proteam` stay) |
| 8b | always | `draft.apply()` again | The real draft for players made or renamed in this run |
| 9 | always | `finish()` | Drops deleted entries, renumbers `key = team × 40 + slot` without gaps, rewrites the free-agent list, and drops the player links (`caBZ`) of removed entries that nothing (entries, free agents, draft picks) uses any more. New links take the lowest free id below 16,000 (`LINK_LIMIT`). Without this every update used more of the 9,955 links |
| 10 | always | `RosterFile.build()` (`tdb.py`) | Packs the tables, recomputes the checksum chain, compresses, writes the wrapper CRCs |
| 11 | always | `verify()` | See "Safety net" |

### A club league in detail (`leagues/clubs.py`)

1. `listed()`: the league's players once each (a feed may list a player twice). `match_club()`
   finds their records. The DEL gives ages only (`birth_approx`): those players match by full name and a birth year
   that fits, and a match brings the save's exact birthdate.
2. `creation_order()`: matched players first, then each club's **core** (what it lacks for 2 G,
   6 D, 12 F, best estimated first), then **depth**. Depth players are created only while records
   remain beyond `b.core_reserve` (what later leagues need for their cores).
3. Per player:
   - **Skipped:**
     - on an NHL roster (NHL.com wins);
     - already placed by an earlier league in this run (`b.placed`: the first league keeps him).
   - **Matched:** his entry is moved or created on the club, and other club, pool and junior entries go.
     - The league's position is applied to club-only players (`_feed_position`; national-team members
       keep theirs).
     - A stale EA-era record gets its birth year fixed and is re-estimated, unless EA rated him.
     - AHL players coming down from the NHL get EA's rating if EA lists them.
   - **New:**
     - a record from `take_record()` (none left: skipped and logged);
     - EA's rating if EA has one (`b.ea_rating_for`), else an estimate.
   - **Contract:** contract team is the club. In the AHL, players the feed marks `nhl_contract` get
     the parent club's rights (`affiliates()`) and a two-way deal (`_nhl_contract`).
4. **Former occupants of the slots:**
   - club players become free agents (`b.release`), except players under 20 (`STAY_AGE`), who stay
     with their club when the league's list leaves them out (0.8.0: the WHL's 2026-27 list has no
     Landon DuPont; as a free agent the draft would not see him);
   - pool players go to `pools.relocate`.

   Before that, `_place_prospects()` brings in the undrafted prospects of this league's country
   (`HOME_LEAGUE`; the CHL takes everyone else) who are in a prospect pool, on the free-agent list or
   on no team: they join the club with the most room (fewer than `PROSPECT_ROOM`) as if they had been
   there, so the next run, which finds them as former players who stay, takes exactly the same path.
   Prospects a league lists are left to it (`b.league_rows`). EA's own roster keeps its draft classes
   on junior and European clubs; the community's pools end up on custom teams, which the draft does
   not see (owner, 0.8.0).
   Then `_fill_lineup()` keeps former players of a missing position. Then it signs from the
   prospect pools or free agents (junior-age only for the CHL). A second run therefore keeps the same
   fillers.
5. **Per slot:**
   - over 40: the weakest leave;
   - numbers;
   - lines, but only if the club can dress 20 (otherwise its lines are cleared and it leaves `rebuilt`,
     so `verify` does not hold it to a full line-up);
   - letters.

### Shared state in `Builder` (`builder.py`)

- `log`: rows `[team, change, player, detail, number]`. The report CSV and both summaries
  (`BuildResult.headline()` for the banner, `summary()` for the details) are made from it.
- `deleted`: roster entry indexes removed at `finish()`. Entries are never deleted mid-run, so
  indexes stay valid.
- `arrivals` and `departures`: which team gained or lost whom, so the line slots of departed
  players can be handed to newcomers.
- `fa_links`: the free-agent list, kept consistent with the roster entries. `release(e, live)`
  takes an entry off its team. A player left on no club team goes onto this list, unless he is a
  second record of someone (`records_of`). **Nobody is dropped without a team:** a record that
  became teamless and is not a free agent would be reused on the next run, and that run would no
  longer be byte-identical.
- **Retiring** (0.8.0). `would_retire(pid)`: `retire_age` or older (30 on the game's own roster, 35
  otherwise, `FA_RETIRE_AGE`), not in the NHL last season (`last_season`, from `nhl_last`), not on an
  NHL.com roster, not listed by a league or an IIHF squad (`listed_rows`). `retires()` then clears his
  contract and rights, frees his places on national teams (`national_gaps`) and NHL copies, and makes
  the record spare. **Every retirement happens before any player is created:** free agents
  (`settle_free_agents`), NHL leavers (step 1), club leftovers (`retire_leftovers`, before the leagues).
  A record freed later could only be used by the next update, which would then differ. For the same
  reason a national team is never filled with, and a rising-star swap never drops, a player who would
  retire.
- `donors` (`donors.py`): where a new player's record comes from. The player table cannot
  grow, so a new player takes over:
  1. a blanked "ZZ" record;
  2. else a teamless record of a former player, oldest first (`real_birth_year`: records from EA's
     2015 database read ten years young, and their draft year gives them away; a birth year that fits
     the draft year is the record's own, and the game's own roster has no such records:
     `b.stale_years`).

  Never taken:
  - legends (level ≥ 84);
  - NHL rights holders;
  - anyone younger than `MIN_AGE` (26);
  - free agents;
  - second records of a person;
  - anyone named in the data being applied.

  A skater record may switch position (`Builder.set_position`, which also moves the playing style
  between the defence range 1–4 and the forward range 5–10). `reset_identity()` wipes the previous
  owner: portrait, commentary name, draft and career data, and gives a generic head.
- `placed`, `core_reserve`, `ea_rated`, `filled_now`, `pool_released`: bookkeeping across the club
  leagues (see "A club league in detail").
- `maintain`: true when the source already has the 8 formerly empty national teams, meaning
  this tool made it. National teams are then kept, not rebuilt.
- **Idempotency.** Running the build on its own output with the same data produces a
  byte-identical save. Tests enforce it, and every new step must keep it (stable sorting,
  no randomness: `estimate._spread` derives its "random" spread from the player's name).

### Matching people (`matching.py`)

Feed players are matched to records by normalised name (accents and punctuation folded, letters
like ø, æ, ß, ł spelled out: `norm()`) plus birthdate. `match()` (NHL) tolerates nicknames and spelling variants; when several
records share last name and birthdate it requires the first names to agree, so twins do not
collapse into one record. A full-name match needs a birth year within 2 (or ten years late: an
EA-era record), and among namesakes the closest birth year wins (0.8.0: the game's own roster has a
Moncton junior Will Smith born 1996, and two Sebastian Ahos). `match_club()` (European clubs) requires the birthdate to agree and
marks EA-era records whose birth year is off by ten (`stale`); those get their year fixed and
are re-rated. The DEL gives ages only: full name and birth year, else a short or long form of the
first name (Nico / Nicolas). EA ratings without a birthdate are matched by name among NHL and AHL teams only.

### Ratings for players nobody rates (`estimate.py`)

EA publishes NHL ratings only. A club player's level is "NHL median for his position + league
gap + age + role + a small fixed spread". `LEAGUE_GAP` (per league and position group) and
`AGE_CURVE` were measured on EA's last official roster for the game, which rated every league
it shipped. In the junior leagues age counts relative to 18 (`YOUTH_AGE`), because their gap was
measured on teenagers. The attribute shape (a centre takes face-offs, a defenceman blocks shots)
is the median shape of NHL players at the same position.

### Pictures for players no list gives one

`Builder.former_photos()` (after the pools): a player on a team or the free-agent list without a
photo link gets last season's from the leagues' `former` lists (HockeyTech: last season's rosters of
players on no list now), matched by name and birthdate. Extraliga photos come from each player's
page on hokej.cz (the provider remembers them in `tools/cache/extraliga_photos.json`). A studio
photo on a shaded backdrop (the CHL's, the AHL's) is cut out by growing the backdrop from pixel to
neighbour (`images._shaded_background_mask`) when the plain flood fill fails; only what neither can
cut out is shown in a soft oval. `install.PORTRAIT_DRAWING` redraws installed portraits once when
that changes.

## Safety net: `verify.py`

The game gives no error for a bad roster: it crashes in a menu or silently keeps the previous
roster. `verify(built, source, nhl_players, rebuilt)` re-reads the built save and checks:

- the save reads back and the checksum chain is intact;
- **hard limits**: the team count is unchanged, no team changed league;
- every roster entry points at a player, entry ids are unique;
- with `nhl_players`: every listed player is on exactly his NHL team, nobody else is on one;
- structure (`structure()`): no line slot held twice, dressed exactly when holding a slot, NHL and
  national teams (and every rebuilt club) dress a legal 20 with all slots filled, mirrors equal
  their primary, three letters per NHL team, at most 40 per team, consecutive entry ids, free
  agents listed once and without contracts, draft year, round and pick that fit together;
- contracts point at a team the player is on, and nobody is on two club teams.

Checks are relative to the source: a flaw the source already had is not blamed on the update.
Teams the build rebuilt from scratch (`rebuilt`) are held to the full standard regardless.
`pipeline.update()` installs nothing if any problem is reported. Non-fatal facts go to `info`
(for example AHL teams left short-handed by call-ups).

## Data

### NHL.com, live on every update

- `GET https://api-web.nhle.com/v1/roster/{TEAM}/{season}` for the 32 teams (season like
  `20262027`, falling back to `/current`), cached for 20 minutes in `cache\nhl_<season>.json`.
- Players on the source's NHL teams that no roster lists: `search.d3.nhle.com/api/v1/search/player`
  and `/v1/player/{id}/landing`, cached for 6 hours in `cache\missing_<hash>.json`.
- Offline (`--offline`): the cached copy, else the snapshot in the data pack.

### The data pack (`legacy_roster/data/datapack.json.gz`)

Built by `tools/build_datapack.py`, bundled in the exe, and downloaded fresh from `PACK_URL` once
that is set (empty today; see MAINTAINING.md). Gzipped JSON:

```
{
  "format": 1, "season": 2026, "generated": "2026-10-03T14:20:00Z",
  "sources": {"<part>": {"label": "EA NHL 27 ratings", "date": "2026-10-01", "count": 1071}, ...},
  "ea_ratings": [{"name", "team", "position", "birth": [y, m, d], "ovr", "attrs": {"Passing": 86, ...}}],
  "iihf":      {"AUT": [{"first", "last", "birth", "pos", "num", "shoots", "height_cm", "weight_kg", "club"}], ...},
  "leagues":   {"liiga": {"label", "league_id", "country", "left_out": [...],
                          "teams": [{"slot", "league_id", "full", "short", "abbr", "art", "logo", "players": [
                              {"first", "last", "birth", "pos", "num", "shoots", "height_cm", "weight_kg",
                               "country", "letter", "rookie", "photo",
                               "nhl_contract" (AHL), "birth_approx" (DEL)}]}]},
                "extraliga": {...}, "shl": {...}, "del": {...}, "nl": {...}, "norway": {...},
                "ahl": {...}, "chl": {... "country": null, no league-wide league_id}},
  "nhl":       {"ANA": <NHL.com roster response>, ...},
  "nhl_logos": {"ANA": "<logo link>", ...},
  "nhl_last":  [{"first", "last", "birth", "pos", "team" (null: unsigned now), "gp", "nhl_id", "shoots",
                 "height_in", "weight_lb", "country", "city", "photo"}],
  "drafts":    [["first", "last", "position", year, round, overall pick, "team code"], ...]
}
```

Each league also has `extra`: the clubs its feed lists that have no slot (Jokerit, Ajoie, Penticton
...), with their players, for a player's own custom team of that name (`clubs.own_teams`).

```
```

- **Photos and logos.** `photo` and `logo` are links only (or null); the pictures are downloaded on
  the player's PC. Player photos come from each feed; logos from the feed (AHL, CHL, Liiga), else
  from the club's English Wikipedia article (`tools/providers/wiki_logo.py`, which renders SVG
  logos as PNG), else `logo` / `wiki` in `club_slots.json`. NHL logos are ESPN's PNG copies
  (NHL.com has SVG only). NHL photos come live with the NHL.com rosters (`headshot`).

- **League id.** Every team carries its own `league_id`, for two reasons:
  - the CHL spans the game's leagues 9–11;
  - the AHL's Coachella Valley and Henderson sit in custom slots (league 13).
- **Country.** A league's `country` is null where the clubs come from several countries (AHL, CHL). There, a
  player without a country gets none, and nobody counts as an import.
- **Format check.** `datasource.load_pack()` skips a pack whose `format` is newer than `PACK_FORMAT`.
- **In the window.** `sources` feeds the "data from …" line under each switch, and `left_out` the line below it
  (`pipeline.left_out_note`). A league appears as soon as the pack has it (`pipeline.steps_for(pack)`).
  Leagues the game has but the pack lacks are listed as "Coming later" (`pipeline.planned(pack)`).

## The game's own roster (`stock.py`, 0.6.0, experimental)

For players with no community roster (owner, 2026-10-04). The disc's `db/nhlng.db` (in
`cacheboot.big`) holds all 39 tables of a roster save with the same record layout (FORMAT.md
section 6).
- **The source.** `Rpcs3.disc_slots()` lists a `savedata.DiscSlot` per version RPCS3 has the disc
  of (`games.yml`). The window shows it last in the roster list, marked "start fresh". The command
  line takes it as `--source disc`. `find_rpcs3` accepts an RPCS3 with no roster save when the game
  is listed. A roster saved in the game without a community roster has the same layout and is
  accepted too.
- **`from_disc()`** builds the save: the roster tables in the save's order, the game's maxima
  (`ROSTER_MAX`), header flag 6, the `prCe` index on `caBZ`, trailer, wrapper (`tdb.RosterFile.from_db`).
- **`prepare()`** (start of `build()`, `check_base` → `STOCK`; a no-op on its own output, since 30/31
  then hold no All-Star copies):
  - empties the All-Star slots 30/31 (Seattle, Vegas);
  - moves birth years to year − 1910;
  - adds spare "ZZ" records cloned per position, up to the 6,745 players the community roster shows
    the game reads.
- **During the build.** Free agents of `RETIRE_AGE` (30) and older retire unless they played in the
  NHL last season (`settle_free_agents`; before 0.8.0 `prepare` retired them by age alone, and
  Reimer with them). On the first update its 2014 national teams are emptied and filled again
  (`clear_national`): their members were blocking retirements (Datsyuk, Price, Rask stayed free
  agents in 0.7.0).
  - No mirrors (`layout.mirrors(STOCK)` is empty: no custom copies, owner's decision).
  - `pipeline.usable_clubs` leaves out clubs whose slot is a switched-off custom team (Coachella
    Valley and Henderson).
  - Before the leagues, `retire_leftovers()` retires 2014's players of 30 and older whom no feed
    lists, except those a club needs to dress 20. The NHL step retires its leavers the same way.
    Retired players' links are handed out again in place (`Builder.dead_links`). All of this
    happens before any new player is made, so a second run finds no spare record the first did not
    have, and stays byte-identical.
- **In-game check:** `cli stock-test` (ROADMAP).

## Photos and logos (`legacy_roster/art/`, experimental)

A switch in the window ("Photos, logos and team names") and `update --photos` on the command line.
The pictures are made on the player's own PC from templates of his own disc; the exe carries
them already drawn (photo pack, below); no EA file is shipped.

**Both versions of the game.** The EU (`BLES02153`) and NA (`BLUS31540`) discs hold the same art and
text files, so one set of pictures serves both. `install.install(rpcs3, title_id, ..., also=[...])`
reads the templates from the disc of `title_id` and writes every file into the game folder of each
version (`_Writer` over several folders). The pipeline passes the versions in `targets`.

1. **Before anything is built** `install.check()` stops with a sentence when RPCS3 is running or
   RPCS3 does not know where the game is (`config/games.yml`).
2. **During the build** every placed player with a photo link is recorded (`Builder.photos`: the NHL
   step and `clubs.update_league`), and every club with a logo link (`Builder.logos`). After
   `finish()`, `portraits.plan()` writes the portrait ids into the roster: an EA id (1–12,401) or a
   community id (12,402–13,826) stays and its file gets today's photo; anyone else gets an id from
   20,000 up, remembered per person in `art\portrait_ids.json`, so a player keeps his id and a
   build on its own output stays byte-identical. `hasportrait` is set to 1.
3. **After the roster is saved** `install.install()`:
   - reads templates from the player's disc (`lab.Disc`: portrait p100, each club's own logo files);
   - takes each picture from this PC's cache (`photopack.PictureCache`, `art\pictures\`, keyed by
     the exact link), else from the photo pack, else downloads it (6 at a time), draws it and keeps
     it in the cache. Drawing with Pillow (`images.py`): background removed from studio photos
     (flood fill from the edges), head found (top, middle, width) and placed where the game's own
     portraits have it; logos in the five styles (`t`, `s`, `w`, `c`, `d`), each inside the area the
     disc's own logos of that kind fill (`images.LOGO_BOX`, 0.8.0: before, big logos covered the
     team's record and calendar logos spilled out of their cells), and for the 32 NHL slots the sixth,
     `r` (logo on its reflection, 256×512, the favourite-team screens; `install.logo_kinds`). NHL
     logos come from ESPN in two versions: the plain `500` one for the pictures with a white edge
     (`t`, `d`, `r`; `install.EDGED_KINDS`, `install.plain_logo_url`) and the `500-dark` one for the
     banner, watermark and calendar (`s`, `w`, `c`). The dark ones are white silhouettes for Tampa Bay,
     Washington and Toronto and in part Boston, Vancouver, Los Angeles and Detroit; with the edge they
     came out as white blobs on the favourite-team screen (owner, 2026-10-06; `LOGO_DRAWING` '#3');
   - encodes them (Pillow's DXT5 for portraits, plain 32-bit for logos) into a copy of the template
     (`bigf.ArtFile.with_image`) and writes them as loose files (portraits in `p0_4000`,
     `p4001_8000` or `p8001_12000`);
   - backs up any file it replaces and lists every file with its link in `art\installed.json`,
     per game folder (`{'games': {folder: {file: {'source', 'backup', 'stamp'}}}}`; version 0.4's
     single `{'game_dir', 'files'}` is read too). A file already made from the same link is skipped;
     a logo's source carries the drawing version too (`install.LOGO_DRAWING`), so a new way of
     drawing redraws every installed logo once.
     Rules for the copies (`_Writer.write`, `_keep`, `ours`):
     - a kept copy is never overwritten by one of the program's own files (after a lost
       `installed.json` the file there is ours, and the original stays);
     - `stamp` (size, time) tells our file from one put there later, for example another picture
       pack: that one is copied aside first and comes back with "Restore";
     - `remove()` leaves a file it did not write and has no copy of.
   A failed download leaves the player with his old picture or the silhouette; the List of changes
   names him under "Pictures not installed" (`pipeline.note_skipped`, 0.8.0).
4. **Team names** (`portraits.names()`, `install.install_names()`, `loc.py`).
   - For every rebuilt club, NHL slots 22/30/31 (Utah, Seattle, Vegas) and every team the player
     renamed, the art code's five name keys are written into each language's text file.
   - A custom team shows only the text under its `shortname`. The update writes custom shortnames
     as keys in the game's own style (`layout.city_key`: COACHELLA_VALLEY, 2026_PROSPECTS_2;
     `pools.relocate`, the club step, team edits, and `portraits.names()` for older rosters and
     the Kings copy's "NhlCityName_13" → LOS_ANGELES). Each gets the team's full name as its text,
     unless the game already has one (ANAHEIM). Keys added to the text file keep their case
     (`loc.LocFile.set`): texts added under capitalised keys did not show in the game.
   - The files are always made from the disc's originals, so nothing piles up across updates. They
     are listed in `installed.json` like the pictures.
   - The prospect pools in the spare custom slots get art ids of their own (21000 + slot) and logos:
     the NHL team's for a "System" pool, `images.badge()` with the year for a draft class.
5. **"Restore the game's own pictures"** (`install.remove()`, `cli photos remove`) restores every backup,
   deletes the files it added and the folders it made, in every game folder. Rosters are not
   changed: ids without a file show the silhouette.

Pillow is the only package outside the standard library the engine uses, and only here
(`images.py`, imported when the switch is on).

**The photo pack** (owner's decision, 2026-10-03: players should not each download everything).
- **Building it:** `tools/build_photopack.py` downloads every linked photo and logo once, draws them
  with `images.py` and stores the results as WebP in `legacy_roster/data/photopack.zip`:
  - portraits: the top 512×256 of the big picture and the 256×128 small one;
  - logos: trimmed, at most 512 px.
- **Keys and index:** `index.json` maps a key to its file. The key is the link itself, or `nhl:<id>`
  for NHL.com headshots, whose links change with the season.
- **Shipping:** `packaging/build.ps1` puts the zip into the window program (it refuses to build
  without it), not into the cli. Git ignores it.
- **At run time:** `art/photopack.py` opens it. `install.make_portrait` / `make_logo` take pictures
  from the cache first, then from the pack. Only links missing from both are downloaded.

## Roster editor and the player's edits (`editor/`, `edits.py`)

**Two tabs** (`gui.App.tabs`): **Update** (the cards above) and **Roster editor**
(`editor/view.EditorTab`).

**What the editor shows.**
- `editor/model.Snapshot` reads a roster save into teams (by league) and players: position,
  number, age, country, overall and ratings.
  - The overall is the mean of the EA attributes plus the EA offset (`ratings.overall_offset`), so
    it is close to the game's own figure, not identical.
  - Players are matched across rosters by person (`edits.who_of`: plain name + birthdate).
- `model.compare(before, after, team)` gives each team's joined, left and changed players. It
  colours the table against the roster as it was opened (so only this visit's edits show).
- `model.apply_edits(raw, edits, teams, season)` builds the roster with edits and no update step.

**The view.** One: the roster save picked on the Update tab as it is (`EditorTab.view`, with the file's size
and time in `source`, so a changed file is read again) plus the edits made in this visit (`session`,
`session_teams`; `apply_edits` with no update step, about 2 s). The edits kept in `edits.json` (`self.edits`)
are applied by every update (the Update tab's "My edits"), not shown over a roster that was saved with
them. (Until 0.8.0 there was an "As is" and a "To be" view: a dry run of the update, removed 2026-10-06.)
**Saving** follows the Update tab's choice (`App.save_mode`): `savedata.update_in_place` (expected = the
bytes read when the roster was opened) or a new save (`savedata.install`); the game's own roster is always
a new save.
- **The picture on the card** (`editor/pictures.py`, Pillow): the player's own picture if he has
  one; else what the game shows now for his
  `artid` (the loose file in RPCS3's game folder, else the disc's own file). Made in a thread; a
  token drops a late result for a player no longer shown.
- Worker threads hand results back through `App.queue` as `('ui', callable)`.

**Edits** (`edits.py`).
- **Storage.** Kept in `%LOCALAPPDATA%\NHLLegacyRosterUpdater\edits.json`, one entry per person:
  - `set` fields;
  - `ratings` by EA attribute name;
  - `team` (a slot or `FA`);
  - `new` for a created player (with `ovr`);
  - `was`, the original name and birthdate.
- **Where they run.** `pipeline.build(my_edits=...)` runs them in two places:
  1. `edits.restore()` right after parsing: renamed players get their original names back, so the
     update still recognises them;
  2. `edits.apply()` as the last step before `contracts()`.
- **What `apply()` does.** It finds each person, sets fields and ratings, and moves or releases
  him:
  - at most 40 a team;
  - an edited number wins a clash;
  - goalies stay goalies;
  - a new player takes a spare record through `donors`.

  It then deals the lines of changed teams afresh (`lines.build_lines`; letters kept where the
  holders stay, `clubs._letters`) and syncs the mirrors.
- **The safety check.** `verify(edited=...)` lets the edited players differ from NHL.com's rosters,
  and only them.
- **Determinism.** A build on its own output with the same edits is byte-identical
  (`tests/test_edits.py`).
- **Who applies them.** The Update tab's "My edits" switch and `cli update --edits` apply them to
  every update.
- **Team edits and pictures of the player's own.**
  - `edits.json` also holds `teams`: `{slot: {full, city, abbr, logo}}`, applied by
    `edits.apply_teams` (team table names, `Builder.team_names`, `Builder.logos`).
  - A player edit may carry `photo`.
  - Chosen pictures are copied to `art\mine\` (`edits.keep_picture`) and used as `file:` links by
    `install._download`.

## Team layout of the supported roster

The game has 252 team slots in 16 leagues, all fixed (`layout.py`, FORMAT.md section 6). The
updater supports the community roster family: the 2025-26 roster ("ROSTER2526"), the community's
2026-27 roster (the same layout; its custom copies out of step, six national teams emptied, 25 more
player records) and the rosters made from them. Since 0.6.0 it also supports the game's own layout
(section "The game's own roster": real 2014 clubs everywhere, All-Star teams in 30/31, custom
slots off). `check_base()` refuses anything else.

| League (id) | Slots | What the base roster has there | Updater |
|---|---|---|---|
| NHL (0) | 0–31 | 32 teams; slot 22 holds Utah, the All-Star slots 30/31 hold Seattle and Vegas | `nhl` step, live |
| AHL (1) | 32–61 (+ custom 234, 235) | 32 teams, incomplete lines | `ahl` (experimental) |
| SHL (2) | 62–75 | 62–67 prospect pools "2026–2031 Prospects 1", 68–75 eight empty club slots | `shl` (experimental) |
| Liiga (3) | 76–90 | 76–79 prospect pools, 80–90 empty club slots | `liiga` |
| DEL (4) | 91–104 | 91–93 prospect pools, 94–100 empty club slots, 101–104 NHL "System" pools | `del` (experimental) |
| Extraliga (5) | 105–118 | 14 NHL "System" pools | `extraliga` |
| National League (6) | 119–130 | 12 NHL "System" pools | `nl` (experimental) |
| Norway (7) | 131–132 | 131 USNTDP Juniors, 132 Vålerenga (empty) | `norway` (experimental) |
| National (8) | 133–153 | 13 squads, 8 empty (AUT, BLR, GBR, JPN, KAZ, NOR, POL, UKR) | `national` |
| OHL / QMJHL / WHL (9–11) | 154–173 / 174–191 / 192–213 | 6–14 players a team | `chl` (experimental) |
| Top Prospects (12) | 214–215 | empty | leave alone |
| Winter Classic (14) | 216–219 | (nearly) empty | leave alone |
| EASHL (15) | 220–221 | empty | leave alone |
| Custom (13) | 222–251 | 222–233 mirrors of 12 NHL teams; 234/235 AHL Coachella Valley and Henderson; 236–251 sixteen spare slots, switched off | mirrors synced; spare slots receive relocated pools |

The slot sets are constants in `layout.py`:
- league slots: `SHL`, `LIIGA`, `DEL`, `EXTRALIGA`, `NL`, `NORWAY`, `EUROPE`, `OHL`, `QMJHL`, `WHL`, `CHL`;
- other slots: `EVENTS`, `SPARE`, `SYSTEM_POOL_SLOTS`;
- `AHL_PARENT_EXTRA`: the NHL parents of the two AHL teams in custom slots.

Every pool slot keeps its original art abbreviation (for example `VF` for Frölunda, `HCAP` for
Ambri). Those come from the stock team table on the game disc (`db/nhlng.db` in `cacheboot.big`).

**Prospect pools.**
1. When a league gets its real clubs, displaced pool players move to a spare custom slot named
   after their pool (`pools.relocate`).
2. While the leagues are built, a pool slot may hold more than 40: the AHL and CHL steps still take
   their players out of the pools.
3. Then `pools.settle()` keeps the best 40 per slot, moves the overflow to pools with room, and
   makes the rest free agents.

With every league on, all 16 spare slots are used.

## Finding RPCS3 and the saves (`savedata.py`)

- `find_rpcs3(path)` accepts `rpcs3.exe`, its folder, or any folder inside it (version 0.1
  remembered the save folder). `dev_hdd0` comes from `config\vfs.yml` (or `vfs.yml`) with
  `$(EmulatorDir)` resolved, else `<rpcs3>\dev_hdd0`. The user is `[Users] active_user` from
  `GuiConfigs\persistent_settings.dat` (or `CurrentSettings.ini`), else the user with the newest
  roster. Failures raise `Rpcs3Error` with a sentence for the player.
- `running_rpcs3()` finds a running `rpcs3.exe` through the process list (Windows API, no extra
  package); the window uses it to fill in step 1 and to hide "Start RPCS3".
- `find_savedata(path)` (command line `--savedata`) accepts a roster folder, the savedata folder or
  anything above it.
- A roster save is a folder `<TITLEID>02NN` whose `SYS-DATA` starts with `PS3RosterFile`.
  `Slot.tool_made` recognises this tool's saves by their name (`YYYY-MM-DD HH:MM`).
- **Versions.** `GAMES` = {`BLES02153`: EU, `BLUS31540`: NA}; `Slot.region`; `Rpcs3.games()` lists
  the versions RPCS3 has (in `games.yml` or with saves). Both read the same `SYS-DATA`; their
  `PARAM.SFO` differs only in `TITLE` (`TITLES`) and the folder name, so `install(title_id=...)`
  saves a roster for the other version.
  `next_free()` takes the number after the highest in use (wrapping to a free one after 99).
  `clean_name()` keeps names to characters the game's font has, at most 40.

## What the program writes on the user's PC

| Where | What |
|---|---|
| `…\savedata\<TITLEID>02NN\` | A new roster save per update and version saved for, or (the default since 2026-10-06) the picked roster's `SYS-DATA` replaced in place (`savedata.update_in_place`: backup first, written next to the save folder and moved over the old file, never while RPCS3 runs, only a roster save directly in `savedata`, not the game's own roster). Nothing else in `savedata` is ever written or changed. The only removal is the window's **Delete** button on a roster save: a move to the Recycle Bin / Trash (`savedata.trash_save`; never while RPCS3 runs, never a folder that is not a roster save in that folder, never permanent) |
| `%LOCALAPPDATA%\NHLLegacyRosterUpdater\backups\<TITLEID>02NN_<time>\` | The old `ICON0.PNG`, `PARAM.SFO`, `SYS-DATA` of a roster before it was updated in place (the newest 10 per roster are kept; never inside `savedata`: the game lists every folder that starts like a roster save) |
| `%LOCALAPPDATA%\NHLLegacyRosterUpdater\settings.json` | Path of `rpcs3.exe` (`rpcs3`), switch positions (`steps`) |
| `…\cache\` | `nhl_<season>.json`, `missing_<hash>.json`, a downloaded `datapack.json.gz` |
| `…\reports\` | The list of changes per update, as a page and a CSV (`<folder>_<time>.html` / `.csv`, `failed_…`, `dryrun_…`) |
| `…\logs\error.log` | Tracebacks of unexpected errors, for bug reports |
| `…\edits.json` | The player's own edits from the Roster editor |
| `…\art\portrait_ids.json` | Photos and logos: the portrait id given to each person on this PC |
| `…\art\installed.json`, `…\art\backup\` | Photos and logos: every picture file written (with the link it was made from) and a copy of any file it replaced |
| `…\art\pictures\` | Photos and logos: every picture this PC downloaded, drawn (the photo pack's layout), so none is downloaded twice |
| `<dev_hdd0>\game\<TITLEID>\USRDIR\fe\ion\artassets\…` | Photos and logos only (switch on, RPCS3 closed): loose picture files the game reads before its disc. "Restore the game's own pictures" puts back every file as it was |

## The window (`gui.py`, `widgets.py`, `theme.py`, `progress.py`)

- **Layout**: header (Puck Peak logo, title line, glow line); cards 1 RPCS3 (rosters found per
  version), 2 roster list (each row with the flag of its version; the game's own roster last),
  3 switches, 4 name + "Save for" (EU · NA · EU + NA with flags, only when RPCS3 has both versions;
  `App.save_targets`) + "Update roster"; result banner; footer with progress bar, status line and
  "Details" (the log, cleared at each start). Built from the components in `widgets.py` (`Card`,
  `Chip`, `Choice`, `PrimaryButton`, `GhostButton`, `RosterRow`, `SwitchRow`, `Banner`).
- **Flags**: `widgets.flag_image()` draws the EU and US flags with Pillow (at 4×, shown through
  `CTkImage`): Windows has no flag emoji and Tk draws no colour emoji. Without Pillow the chips show
  text only.
- **Few redraws** (the owner saw flicker and slow repaints):
  - `set_rpcs3` reads and checks the saves in a thread, and caches the checks by (path, size,
    time);
  - `list_rosters` keeps rows that did not change (`RosterRow.shows`);
  - `refresh_state` changes only what changed (`widgets.configure_if_changed`, `App.set_status`;
    options set through that helper must not be set with `configure()` elsewhere);
  - `poll` shows everything the engine said since the last look in one go;
  - at the start of an update the last result stays, dimmed (`Banner.dim`), so the window does not
    shrink and grow again;
  - the editor builds its rating fields once per kind.
- **Look**: `theme.py` holds Puck Peak's colours as tokens (page `#0b1318`, accent `#2596be`;
  Tk has no transparency, so translucent colours are written out blended), loads the bundled
  Source Sans 3 (Segoe UI if that fails) and picks the logo size for the screen scaling.
- **State**: `App.refresh_state()` is the one place that enables or disables controls and sets the
  idle status text; call it after anything that changes what is possible.
- **Settings**: the RPCS3 path is saved when found; switch positions when an update starts.
  Version 0.1's `folder` setting is still read.
- **Size**: 1000 wide, 640–730 tall depending on the screen (`theme.screen_height()` uses
  `GetSystemMetrics` because the program is DPI-aware). The banner and the details panel make the
  window taller (`App.resize()`, by the difference when the banner changes) as far as the screen
  allows; on small screens the two lists scroll instead.
- **Progress**: `progress.py` maps engine messages to a fraction with a table of regular
  expressions. **The wording of engine messages is an interface**: rename a message and the bar
  stalls. `tests/test_progress.py` replays the messages of a real update.
- **CustomTkinter details**: `bind()` on a CTk widget binds its inner canvas and label, so the
  outer widget's own `<Configure>` needs `tk.Frame.bind(widget, …)`. Font sizes are scaled by
  the screen scaling; `theme.text_width()` measures text the same way (used to shorten the
  RPCS3 path in the middle). Scrolling the roster list to the selection uses
  `CTkScrollableFrame._parent_canvas` (private; re-check after upgrading CustomTkinter).

## Where new things plug in

| You want to | Touch |
|---|---|
| Add an update step | `pipeline.py` (key, `STEP_LABELS`, order in `build()`), the step's code (a `Builder` method or a module), `progress.STAGES` for its message, tests. The window lists it by itself through `steps_for()` |
| Add a club league | A provider in `tools/providers/`, `tools/club_slots.json`, `FEEDS` in `tools/build_datapack.py`, `estimate.LEAGUE_GAP`, the league's key in `pipeline.LEAGUE_ORDER`; mark it in `pipeline.EXPERIMENTAL` until played in the game (step by step in DEVELOPING.md) |
| Add a data source to the pack | `tools/build_datapack.py` (+ provider), a `sources` entry for the window's date line, `datasource.gather()` to pass it into `builder.Data` |
| Change a rule the game enforces | `verify.py` first (so a build that breaks it cannot be installed), then the builder; document it in FORMAT.md section 5 |
| Change the window | `widgets.py` for a new component, `gui.py` to place it, `theme.py` for colours and fonts; keep Tk out of the engine. Look at the result with `tools/window_shot.py` |
| Add a command-line command | `cli.py` (`main()` registers sub-commands) |
