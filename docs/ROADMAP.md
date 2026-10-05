# Status and roadmap

State on 2026-10-05, version 0.8.0 (released 2026-10-05). Update this file when something here changes.

0.8.0 answers the testers' feedback on 0.7.0 (owner's decisions below):
- **Free agents:** retired players go, last season's unsigned NHL players come (Reimer, Toews,
  Quick), created if the save lacks them. Rule: `builder.would_retire` (data pack `nhl_last`).
- **Real player data:** every player's real draft (`draft.py`, data pack `drafts`), NHL.com's
  height, weight, hand and birthplace for every NHL player, stricter name matching (Will Smith,
  the two Sebastian Ahos).
- **Logos:** the game's own sizes (they covered the record and spilled out of the calendar), and
  ESPN's dark-background logos (a white Tampa Bay bolt, Washington with white edges).
- **Goalie gear** in the new club's colours.
- **Your own team:** a custom team the player made, named after a club the game has no slot for
  (Jokerit, Ajoie, Penticton, Coachella Valley ...), gets that club's players.
- **Pictures not installed** are named in the List of changes; the Roster editor no longer calls
  every player of the game's own roster "new to the game".
- After the owner's own test: **prospects on real clubs** (`clubs._place_prospects`), juniors the
  list leaves out stay (`STAY_AGE`), **more photos** (Extraliga, last season's CHL/AHL, shaded
  backdrops cut out), **a window that keeps every step in view**, **macOS and Linux**, and **roster
  saves without RPCS3** (`savedata.SaveFolder`).

0.7.0 fixes two problems a tester had with 0.6.0: downloads from the NHL player search failed with
a certificate error (the exe now carries its own list of trusted certificates), and the window
crashed when files it unpacks at start had been removed (it now says so). Nothing new goes into
the save, so the in-game checks below are unchanged.

0.6.0 in one breath:
- **No roster needed:** the game's own roster, read from the player's disc, can be updated
  (`stock.py`).
- **NHL.com positions** for every NHL player, and wingers on their own side of the lines (Cole
  Smith is Chicago's third right wing).
- **Favourite-team logos:** the logos of the "Choose Your Favorite Team" screen are written too
  (`teamlogosreflection`).
- **One program with every picture inside.** Downloaded pictures are kept on the PC, and pictures
  that were there before are always kept.
- **Readable results:** one line per part in the window, and the list of changes as a page grouped
  by team.
- **The window:** flags for EU / NA, and smoother redraws (rosters read in the background, rows
  kept, fewer redraws).
- **Links given back:** player links of removed roster places are reused, so repeated updates no
  longer fill the link table.

0.5.0: EU and NA, the community's 2026-27 roster, every empty national team filled, custom team
names fixed.

## League checklist

Every league the game has, what the updater does with it, and where its data comes from. Slot
numbers and the base roster's contents are in ARCHITECTURE.md ("Team layout"); the club-to-slot
map is `tools/club_slots.json`.

| League | Slots | Status | Data source | Notes |
|---|---|---|---|---|
| NHL | 0–31 | **Done**, live on every update | NHL.com API | – |
| Player ratings | – | **Done** | EA ratings via nhlratings.net | EA rates NHL players (and some farm players) only; everyone else is estimated (`estimate.py`) |
| National teams | 133–153 | **Done**: squads kept current, every empty one filled (0.5.0: also squads a community roster emptied) | IIHF roster PDFs (20 countries) + NHL.com | A country that cannot dress 2 G + 18 skaters stays empty and is named in the summary |
| Liiga | 76–90 | **Done** (played in the game 2026-10-03) | liiga.fi feed | 17 clubs, 15 slots: Jokerit and Jukurit left out. Kiekko-Espoo in the Espoo Blues slot (77) |
| Extraliga | 105–118 | **Done** (played in the game 2026-10-03) | hokej.cz roster pages | Kladno in Chomutov's slot (107), České Budějovice in Zlín's (118) |
| SHL | 62–75 | **Experimental** | shl.se site API (Sportality) | 14 clubs, 14 slots. Björklöven in Karlskrona's slot (67), Timrå in MODO's (71) |
| DEL | 91–104 | **Experimental** | penny-del.org roster pages | 14 clubs, 14 slots. Frankfurt in Düsseldorf's (93), Bremerhaven in Hamburg's (94). Age only: new players get an approximate birthdate |
| National League | 119–130 | **Experimental** | nationalleague.ch app API | 14 clubs, 12 slots: Ajoie and Rapperswil-Jona left out. No nationality, height, weight or hand in the feed |
| Norway | 131–132 | **Experimental** | ehl.no site API (Sportality) | 9 clubs, 2 slots: Stavanger (131, was the USNTDP pool) and Vålerenga (132) |
| AHL | 32–61, 234, 235 | **Experimental** | HockeyTech (league site feed) | 32 clubs, 32 slots. Hamilton Hammers in Bridgeport's slot (35). NHL-contracted players get their parent club's rights (`ahlaffiliate`; Vegas cannot hold rights) |
| OHL / QMJHL / WHL | 154–213 | **Experimental** | HockeyTech | 20 / 18 / 23 clubs for 20 / 18 / 22 slots: Penticton left out. Last in line for player records (see capacity) |
| Top Prospects, Winter Classic, EASHL | 214–221 | Leave alone | – | Event teams |
| Custom | 222–251 | Managed | – | 222–233 mirror NHL teams (kept identical), 234/235 are AHL teams, 236–251 receive relocated pools |

HockeyTech public client keys, taken from the league websites and verified on 2026-10-03 (they can
change): AHL `50c2cd9b5e18e390`, OHL `2976319eb44abe94`, WHL `41b145a848f4bd67`, QMJHL (`lhjmq`)
`f322673b6bcae299`. They live in `tools/providers/hockeytech.py`.

## Waiting for the game

Only the project owner can run these. They decide when a part leaves `pipeline.EXPERIMENTAL`
(the window shows no mark any more; everything is on by default).

| Check | Status |
|---|---|
| NHL rebuild, exe end to end, Liiga + Extraliga, custom pool teams | **Passed** 2026-10-03 (rosters `2026-10-02 22:07`, `22:14 Europe`) |
| Renamed clubs through the text file (Utah, Seattle, Vegas, Timrå, Björklöven) | **Passed** 2026-10-04; custom team names did **not** show → fixed in 0.5.0, check again (below) |
| SHL, DEL, National League, Norway, AHL, CHL | Waiting: build a roster with every switch on and follow the check list below |
| 0.5.0: custom team names, photos and logos | **Passed** 2026-10-04 ("photos, logos and team names work across") |
| 0.5.0: Save for NA | **Passed** 2026-10-04: the roster loads and plays in the NA game, photos show |
| 0.5.0: the community's 2026-27 roster updated | **Passed** 2026-10-04: the refilled national teams are there |
| 0.6.0: favourite-team logos | Waiting: with "Photos, logos and team names" on, "Choose Your Favorite Team" (a new game profile) and the favourite team in the settings show Utah's logo, not the Coyotes' |
| 0.6.0: NHL.com positions | Waiting: Chicago has three right wings (Kane, Kantserov, Cole Smith); on the lines, left wings play left and right wings right |
| 0.6.0: the game's own roster | Waiting: `NHLLegacyRosterUpdater-cli stock-test --rpcs3 "<rpcs3.exe>"` (writes two LAB rosters into RPCS3: "LAB game roster as is" and "LAB game roster updated"). Load each: the roster loads; Team Management opens an NHL club, Seattle (in the Green / Red slot) and a Liiga club; one Play Now game; the free agents list opens. If possible, first save the game's own roster once in the game (a new profile, Roster Management > Save Roster) and send it: it can be compared byte for byte with what `stock.from_disc` makes |
| 0.8.0: free agents | Waiting: Be a GM > Free agents on a roster made from the game's own roster: no Datsyuk, Price or Rask; Reimer, Toews, Quick there; a new unsigned player opens and can be signed |
| 0.8.0: draft data | Waiting: a player card of Will Smith (2023, round 1, 4th, San Jose) and of a junior (his draft year, undrafted); Be a GM's draft still runs |
| 0.8.0: logo sizes | Waiting: Be a GM calendar (logos inside their cells), the team panel of "Next game" (the record readable under the logo), Tampa Bay and Washington visible |
| 0.8.0: goalie gear | Waiting: a goalie who changed club (Play Now) wears the new club's colours on pads, blocker and glove |
| 0.8.0: your own team | Waiting: make a custom team "Jokerit" in the game, save the roster, update it: the team has Jokerit's players and still opens |
| Season mode crash (owner, 2026-10-04) | Open: Season Mode > Select Team > Arizona (Utah) crashed with roster "2026-10-04 21:24" (0.8.0 from ROSTER2526): the game looked up a player it could not find (offset 0x79, the position, compared with 4: a goalie), at 0x00381c24. Season mode was never tested before (SEASON_PLAN C1). Asked: does ROSTER2526 itself crash with Arizona, does the new roster crash with another team; after a crash leave RPCS3 open so its log can be read |
| Draft test (`cli draft-test`) | Optional now: since 0.8.0 the update puts undrafted prospects on real clubs anyway (owner asked for the fix, 2026-10-05); the test still tells whether the draft also sees pools or free agents |
| 0.8.0: pictures | Waiting: Extraliga players and juniors no list has any more (Landon DuPont, Everett) show photos; studio photos on a shaded backdrop are cut out like the rest |
| 0.8.0: window | Waiting: after an update in a maximised window the rosters and every step stay visible (the logo folds away, the result scrolls) |
| 0.8.0: without RPCS3 | Waiting: the tester in CrossOver picks the Mac RPCS3's savedata folder (via Z:) and loads the new roster in the Mac RPCS3 |
| 0.8.0: macOS and Linux | Not tried on a real Mac or Linux PC: the GitHub workflow builds and tests there; a tester with a Mac or Linux should try the program |
| 0.8.0: prospects in the draft | Waiting: Be a GM's draft list (or scouting) shows undrafted prospects of the next draft, from junior and European clubs |
| Kaprizov's photo (tester, 0.7.0) | Open: shows on the owner's PC (EU and NA). Asked the tester which roster, the "Photos and logos" line and any "Skipped" lines; 0.8.0's List of changes names skipped pictures |
| League test (LAB, `cli league-test`) | Waiting. The owner chose (2026-10-04) to wait for it rather than put Coachella and Henderson into the Norway slots |

Check list for each new league (Roster Management > Load Roster > the new roster, then):

1. Team Management: open two clubs of the league. Real names, about 25 players, full lines, a
   captain and two alternates, numbers.
2. Play Now: one game between two clubs of the league.
3. AHL only: open an AHL player's card. His NHL organisation shows.
4. CUSTOM teams 236–251 (prospect pools) still open.
5. Free agents: the list opens. It is longer now: released club and pool players are there.

## Capacity (measured 2026-10-03 on ROSTER2526, `python tools/capacity.py`)

- **Player records.** The table cannot grow (the updater does not try; growing it would need an
  in-game test). New players take over records. Base: 1,253 blank "ZZ" records (C 278, LW 236,
  RW 235, D 378, G 126). On top of that come 1,555 reusable records of teamless players. Never
  reusable:
  - legends rated 84+;
  - NHL rights holders;
  - anyone estimated younger than 26 (`donors.real_birth_year` reads EA-era records' draft year);
  - free agents;
  - second records of a person (national-team goalies).

  Skater records switch position when one position runs out (goalies cannot).
- **A full build** (every league) creates **2,678 players** and uses **every** record. Every club
  still dresses 20, for three reasons:
  - each league's core line-up is created before any depth;
  - records are held back for later leagues' line-ups;
  - short clubs are topped up from former players, the prospect pools and junior-age free agents.

  Skipped for lack of records: CHL 238 depth players, DEL 5, National League 3, AHL 2. They are listed in the report.
- **Prospect pools.** 952 pool players in 46 pools in the base. With every league on, real clubs
  absorb many of them. The 16 spare custom slots hold 640 (all used) and 73 become free agents
  (`pools.settle`, best prospects kept).
- **40 players per team** at most (roster entry ids are team × 40 + slot).

## Decisions taken (2026-10-03)

1. Liiga and Extraliga confirmed in the game: no longer experimental.
2. Pools: real clubs first; leftovers fill the 16 spare slots best first; overflow becomes free
   agents keeping NHL rights. Event slots stay untouched.
3. Junior leagues: full rosters reusing retired records; when records run out, every club still
   gets a legal 20 and depth players are skipped. The player table is not grown.
4. Photos and logos: built on the player's own PC with an undo button; later the same day the owner
   decided to ship a second exe with every picture inside (photo pack). EA files are never shipped.

## Decisions taken (2026-10-04)

1. **EU and NA.** Rosters are tagged EU / NA; with both versions in RPCS3, "Save for" saves for EU,
   NA or both, and photos go into both games.
2. **Empty national teams are filled**, also those a community roster emptied (IIHF + NHL + the
   country's players in the save).
3. **No NEW tags; every league on by default.** `pipeline.EXPERIMENTAL` only lists what waits for
   the in-game check.
4. **Coachella Valley and Henderson** stay in custom slots 234/235 until the LAB league test has been
   played. Putting them into the Norway slots was considered and set aside: they would be listed
   under Norway, and their NHL link still could not be set.

## Decisions taken (2026-10-04, after the 0.5.0 checks)

1. **One program** with every picture inside (the plain exe without them is gone). New players'
   pictures are downloaded and kept on the PC.
2. **Positions follow NHL.com** for every NHL player (67 differed from the community roster, among
   them Cole Smith: RW, not LW).
3. **The game's own roster** can be started from, for players with no community roster. It gets
   **no custom copies** of NHL teams.
4. The window should not flicker or repaint slowly. The flags of the versions are pictures:
   Windows has no flag emoji.

## Decisions taken (2026-10-04, testers' feedback on 0.7.0)

1. **Retiring** follows NHL.com's last season: whoever played in the NHL last season stays, old free
   agents who did not and whom no league lists retire. Also for community rosters.
2. **Every unsigned NHL player** of last season is a free agent, created if the save lacks him (not
   only regulars), although records are scarce.
3. **A player's own custom team** named after a left-out club gets its players (it stays in the
   Custom group until the league test is played).
4. **Goalie gear** is painted in the new club's colours (not plain white).
5. **Real data for every player** (draft first), fetched into the data pack, never by the players'
   PCs.

## Open decisions for the owner

1. **Base roster credits and bundling.** Who made ROSTER2526 (for the README credits), and
   whether they allow bundling it. The bundling switch stays off until they agree.
2. **Data pack hosting.** Published on GitHub (MatusRiedl/puckpeak-nhl-legacy-rosters, release
   v0.6.0, 2026-10-04). Still open: where data packs are hosted (`PACK_URL`), so new data can reach
   players without a new exe.
3. **More room for players** (later): growing the player table by up to ~1,240 records would let the
   junior leagues keep their depth, but needs an in-game test first.

## Suggested order

1. In-game checks (above): the 0.6.0 checks (favourite-team logos, positions, the game's own
   roster), then the new leagues; then remove them from `pipeline.EXPERIMENTAL`.
2. The owner's check of photos and logos (below), the Roster editor and the league test.
3. Season study, experiment C1 ([SEASON_PLAN.md](SEASON_PLAN.md)). Then, with the owner's go-ahead,
   the `lab` command for C2–C4 and the schedule step.
4. Set `PACK_URL` (the pack `format` check is in place; the project is on GitHub since 0.6.0).
5. Decide whether ages move to − 1911 for 2026-27 (SEASON_PLAN.md: today every player is one year
   too young in the game).

### Phase B (photos, logos, names): state

- **Done.**
  - The art format is decoded and can be written: `legacy_roster/art/` reads the player's own disc
    and builds new art files from it with only the picture swapped (FORMAT.md section 7). Tests in
    `tests/test_art.py`.
  - `tools/names_report.py`: after a full update, only NHL slots 22/30/31 keep old names.
  - **Art test passed in the game (2026-10-03):** all four pictures showed (results in FORMAT.md
    section 7).
  - **Photos and logos (experimental):** a switch in the window (`--photos` on the command line)
    and "Restore the game's own pictures" (`photos remove`). Built on the player's PC, or taken from
    the photo pack inside the exe. Since 0.5.0 written into the EU and the NA game when the roster is
    saved for both. Details in ARCHITECTURE.md ("Photos and logos").
- **Passed in the game (2026-10-04):** photos, logos and team names, in the EU and the NA game.
- **0.6.0:** the reflection logos of the favourite-team screens (`r<artid>.big`, 256 x 512, NHL
  slots 0-31 only) are written too; waiting for the check above.
- **Names (built 2026-10-03).** With "Photos, logos and team names" on, the game's text files
  (`art/loc.py`, FORMAT.md section 7: Huffman-compressed strings, decoded and rebuilt byte for byte)
  get every rebuilt club's name, city, nickname and abbreviation:
  - Utah, Seattle and Vegas instead of Arizona, Green and Black: **shown in the game** (2026-10-04),
    as were Timrå and Björklöven;
  - the custom teams (Coachella Valley, Henderson, the prospect pools): **not shown** in 0.4.0. Fixed
    in 0.5.0 (keys in the game's style, added keys keep their case); waiting for the check above.

  The prospect pools also get logos of their own: their NHL team's for a "System" pool, a badge with
  the year for a draft class.
- **Not covered:** National League (its feed has no photos) and Extraliga players (hokej.cz has none
  in the roster pages); their club logos are covered.
- **Photo quality (trial on 255 real pictures, 2026-10-03):** NHL, SHL, Liiga and DEL photos are
  cut-outs and look like the game's own. AHL/CHL studio photos on plain backdrops are cut out. Those
  on mottled backdrops are shown in a soft oval instead (`images.prepare`). Norway's photos are
  waist-up shots on a spotlit backdrop and come out smaller. About 0.4 % fail to download and are
  skipped.

### League test (the owner runs this once)

Can a custom team play in a real league? The NHL's Seattle and Vegas use the NHL's own All-Star
slots, but no other league has spare slots, so the only way is to change a custom slot's league
fields. That is untested, and `verify` forbids it everywhere except in this test.

1. With RPCS3 closed or open (only a new roster save is written):
   `NHLLegacyRosterUpdater-cli league-test --rpcs3 "<rpcs3.exe>" --source <a 0.4 roster>`
2. In the game, load "LAB custom teams in leagues":

   | Team | Slot | Should now be in |
   |---|---|---|
   | Coachella Valley, Henderson | 234, 235 | AHL |
   | Jokerit | 250 | Liiga |
   | HC Ajoie | 249 | National League |
   | Penticton Vees | 248 | WHL |

   Each one should be listed there, its roster should open, and one Play Now game against a club of
   that league should work. Also note whether they still show under the custom teams.
3. Report: shown / not shown / crash. Names may be blank in this test (the text file is not written).
4. If everything passes, the league steps can put Jokerit, Jukurit, Ajoie, Rapperswil-Jona,
   Penticton, Coachella and Henderson into custom slots moved into their leagues. Those slots come
   from the 16 spare ones that hold prospect pools today.

### Draft test (the owner runs this once)

Where must an undrafted prospect be for Be a GM's draft to see him? EA's own roster keeps its future
draft classes on junior and European clubs with their draft year and round 0; the community roster
keeps them in "Prospects" pools, which the update moves to custom teams, and the owner saw them
missing from the draft.

1. With a roster made by 0.8.0 or newer:
   `NHLLegacyRosterUpdater-cli draft-test --rpcs3 "<rpcs3.exe>" [--source <that roster>]`
   It saves "LAB draft test" and prints twelve names, two per place (also in
   `%LOCALAPPDATA%\NHLLegacyRosterUpdater\reports\draft_test.txt`): left on the custom pool team,
   free agent, on a Top Prospects team, on a WHL club, on a WHL club without a draft year, on a Liiga
   club.
2. In the game load it, start Be a GM and open the list of draft prospects (scouting or the draft;
   if there is none before the draft, simulate to it).
3. Report which names are in the list. The update then puts every undrafted prospect where the draft
   sees him.

### Art test (done 2026-10-03; kept for reference)

1. Close RPCS3. Make a 0.3.0 roster first (it has Kladno in Extraliga slot 107).
2. In a command window in the folder with the exe:
   `NHLLegacyRosterUpdater-cli art-test install --rpcs3 "<path to rpcs3.exe>"`
   This writes 13 test pictures into RPCS3's game folder (`dev_hdd0\game\BLES02153\USRDIR\fe\...`),
   backs up anything it replaces, and saves a roster "LAB art test".
3. Start the game, *Roster Management > Load Roster > "LAB art test"*, then look:

   | Test | Where to look | Picture |
   |---|---|---|
   | 1 | Edmonton Oilers, Connor McDavid's player card | red square with "1" instead of his photo |
   | 2 | San Jose Sharks, Macklin Celebrini's card | green "2" (a new portrait id the disc does not use) |
   | 3 | Montreal Canadiens, Ivan Demidov's card | yellow "3" (a new id above the disc's range) |
   | 4 | Extraliga, Kladno (team select, Team Management) | blue "4" instead of the logo |
   | names | NHL team select: Utah, Seattle, Vegas | do the names show (not "Arizona Coyotes", "Green / Red", "Black / Blue")? |

   For each test, report: shown, not shown (the old picture or a silhouette), or crash.
4. Close the game, then: `NHLLegacyRosterUpdater-cli art-test remove`. Every file goes back as it
   was. Delete the "LAB art test" roster in the game if you like.

What each answer means:
- **1 and 4 show:** loose files override the disc, and the file format is right.
- **2 shows:** new portraits can use unused ids.
- **3 shows:** ids above the disc's range work too; the file was written to two candidate folders.
- **Names show:** the save's names are used for NHL slots too.
- **Something does not show:** the next step is to ask the modder (sportshacker) how the community's
  portrait pack is laid out (its players use ids 12,402–13,826).

## Known limitations

- New players get a generic 3D face and no commentary name (no audio can be added). With "Photos and
  logos" on they get a menu photo when their league publishes one.
- Team names in the menus come from the game's own text, not the save: they show only with
  "Photos, logos and team names" on (see Phase B), and the text file is the same for every roster
  of that game version.
- The game's own roster (0.6.0): records for new players are limited to what the community roster
  shows the game can read (6,745 players). 2014's players of 30 and older who are on no team any
  more retire to make room. Their records are reused: they leave the game.
- A player whose edit (Roster editor) was made before 0.6.0 and whose birthdate the NHL step now
  corrects to NHL.com's (players the save had with another birthdate) is no longer found by that
  edit: edit him once more.
- Club ratings are estimates; DEL newcomers have approximate birthdates; National League newcomers
  are listed as Swiss.
- Some junior depth players are skipped when player records run out (all leagues on).
- The NHL has 32 slots: an expansion team cannot be added (hard limit).
- The team in slot 31 (Vegas) cannot hold player rights: `proteam` is 5 bits. Henderson's NHL
  contracts therefore carry no rights.
- The exe is unsigned (SmartScreen warns) and Windows-only.
- New data reaches players only with a new exe until `PACK_URL` is set.

## Ideas (not planned yet)

- Grow the player table (needs an in-game test) so junior depth is not skipped.
- Real nationality for National League players (the federation's site may have it).
- Tell the player in the window when a newer version is released.
- Build the data pack on a schedule (GitHub Actions) and publish it to `PACK_URL`.
- Finer choices: one league only, ratings only, a single team.
- Show the list of changes inside the window (today it opens as a page in the browser).
- Community corrections: a small JSON of manual fixes (preferred number, position, a feed's typo
  like a wrong birth year) applied after the feeds.
- Linux and Steam Deck: RPCS3's folders there (`~/.config/rpcs3`), a build per system.
- The window in other languages (French, German, Swedish, Finnish, Czech).
