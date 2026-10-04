# NHL Legacy Roster Updater

Keeps the rosters of **NHL Legacy Edition** (PS3, played on RPCS3) up to date. You show it where
RPCS3 is, switch on what you want updated, and it saves a **new** roster named with today's date
and time. Your existing rosters are never changed.

![The updater window after an update](docs/window.png)

## What it updates

| | What happens | Where the data comes from |
|---|---|---|
| NHL | Every player on his current team, jersey numbers, lines, captains, contracts | NHL.com, fetched when you press the button |
| Ratings | Player attributes for NHL players | EA NHL 27 ratings |
| National teams | Squads refreshed; the eight empty national teams filled | IIHF rosters and NHL players by nationality |
| Liiga | The 15 Finnish clubs with their real 2026-27 rosters, lines and captains | liiga.fi |
| Extraliga | The 14 Czech clubs likewise | hokej.cz |
| SHL (new) | The 14 Swedish clubs | shl.se |
| DEL (new) | The 14 German clubs | penny-del.org |
| National League (new) | 12 of the 14 Swiss clubs | nationalleague.ch |
| Norway (new) | Stavanger and Vålerenga, the two Norwegian clubs the game has | ehl.no |
| AHL (new) | All 32 AHL teams with their real rosters; players on NHL contracts belong to their NHL club | theahl.com (HockeyTech) |
| CHL (new) | The OHL, QMJHL and WHL clubs | the leagues' sites (HockeyTech) |
| Photos and logos (new) | Today's player photos and club logos in the game's menus | the leagues' sites, downloaded on your PC (see below) |

Switches marked **NEW** are off until you switch them on: they pass every check the program
makes, but have not been played in the game yet. Tell us how they work.

**About the club leagues.**

- **The game cannot hold more teams than it has slots.** These clubs are left out:
  - Liiga: Jokerit and Jukurit;
  - National League: Ajoie and Rapperswil-Jona;
  - WHL: Penticton;
  - Norway: every club except Stavanger and Vålerenga.
- **A club new to a league since 2015 takes the slot of one that left,** and keeps the old club's jersey,
  and its logo unless "Photos and logos" is on. For now the game's menus also still show the old club's
  name there (the game takes these names from its own text, not from the roster):
  - Kiekko-Espoo plays in the Espoo Blues slot;
  - Kladno in Chomutov's, České Budějovice in Zlín's;
  - Björklöven in Karlskrona's, Timrå in MODO's;
  - Frankfurt in Düsseldorf's, Bremerhaven in Hamburg's;
  - the AHL's Hamilton Hammers in Bridgeport's.
- **Prospect pools.** The community roster uses the European club slots for draft classes and NHL
  prospect pools. When a league gets its real clubs, pool players who are not on a real club move
  to spare custom teams named after their pool (under CUSTOM). There is room for 16 such teams of
  40. The best prospects keep their place; the rest become **free agents**, who keep their NHL
  rights and can be signed.
- **Players who leave a club** become free agents too. Nobody is deleted from the save.
- **Room for new players is limited.** The save has a fixed number of player records. New players take
  over blank records and those of long-retired, low-rated players (never legends, prospects or free
  agents). With every league switched on the records run out. Every club still gets the players it
  needs for a full line-up, but some junior depth players are skipped; the List of changes names them.
- **Ratings.** Club players are rated by estimate (league level, age, role), because EA publishes
  ratings for NHL teams and their farm players only.
- **What the leagues do not publish:**
  - The DEL lists each player's age, not his birthdate. A DEL player new to the game gets 1 July of the
    fitting year (the List of changes marks him).
  - The National League does not publish nationality, so its players new to the game are listed as Swiss.

**Photos and logos (new).** With this switch on, the program also gives the players their current
photo and the clubs their current logo in the game's menus:

- **RPCS3 must be closed** while it runs.
- **Two programs.** `NHLLegacyRosterUpdater-Photos.exe` has about 4,300 photos and logos inside, so
  nothing needs downloading except players new since it was made. `NHLLegacyRosterUpdater.exe` is
  the small one: it downloads the photos from the leagues' sites the first time (about 8 minutes),
  and later updates download only new or changed photos.
- **Made for your game.** The pictures are turned into the game's own picture files on your PC,
  using templates from your copy of the game. Writing them takes a few minutes and about 600 MB.
- **Where they go.** The pictures go into RPCS3's folder for the game (`dev_hdd0\game\BLES02153`),
  not into your roster saves.
- **Undo.** **Remove photos and logos** in the window puts every file back as it was. Your rosters
  stay as they are, and the game shows its own pictures again.
- **Not covered:** the National League and Extraliga publish no player photos, so their players
  keep the game's pictures. Their club logos are covered.

**Roster editor (new).** The second tab of the window shows what a roster holds: every league, team
and player with position, number, age, nationality and overall.

- **As is / To be.** "As is" is the roster you picked. **Preview update** shows what the update will
  make of it, without saving. Green players joined a team, red ones left, and gold ones changed
  (for example "OVR 83 → 86").
- **Edit any player.** Name, number, position, shooting side, birthdate, country, height, weight,
  team (or free agent) and every rating. Then **Apply**.
- **New player.** Give a name, birthdate, team and overall. The save has a fixed number of player
  records, so new players use spare ones.
- **Your edits are kept** on this PC and applied again after every later update ("My edits" on the
  Update tab). The next download therefore does not undo them. **My edits** lists them, and you can
  remove any one.
- **Save as new roster** writes what you see as a new roster, after the same safety checks as an
  update.

## What you need

- Windows and RPCS3 with NHL Legacy Edition (`BLES02153` or `BLUS31540`).
- A roster of the **2025-26 community roster family** saved in the game at least once (the one
  with 32 NHL teams including Utah, Seattle and Vegas). The stock EA roster cannot be used: it
  has no slots for those teams, and the program will tell you so.

## How to use it

1. Download `NHLLegacyRosterUpdater-Photos.exe` (with photos and logos) or `NHLLegacyRosterUpdater.exe`
   (smaller) from the Releases page and start it.
2. **Where is RPCS3?** Pick the file `rpcs3.exe` in your RPCS3 folder. The program finds your
   saves from there, also when RPCS3 keeps its hard disk somewhere else or has several users. If
   RPCS3 is running, or you have used the program before, this is already filled in.
3. **Which roster should be updated?** Pick the roster to start from. Rosters made by this
   program are marked *made here*; rosters it cannot use are greyed out with the reason.
4. **What should be updated?** Switch on what you want and press **Update roster**. It takes
   about a minute.
5. In the game: *Roster Management > Load Roster*, pick the roster with the new date, then save
   it once so the game keeps it as the active roster.

The program writes a new folder next to your existing roster saves (for example
`BLES021530205`). To remove an update, delete that roster in the game or delete the folder.

When it is done, the window offers **List of changes** (every move, call-up and new player, as a
spreadsheet), **Open save folder** and, when RPCS3 is not running, **Start RPCS3**.

## Good to know

- **Windows may warn about the exe.** It is not signed. Choose *More info > Run anyway*, or run it
  from source (below).
- **Safety check.** Before anything is saved, the new roster is tested against the rules the game
  enforces (checksums, line-ups, contracts, team limits). If a test fails, nothing is saved.
- **AHL teams** lose players to NHL call-ups. Switch on "AHL rosters" to fill them with their real
  players.
- **New players** who are not in the game's database get a generic face and no commentary name.
  Players EA does not rate keep the ratings they had, or get an estimate.
- **No internet?** Start it with `--offline` on the command line; it uses the data it shipped with.
- **Real PS3 console:** saves there are signed. Copy the new save over and re-sign it with a save
  tool such as Apollo. This is untested.

## Command line

`NHLLegacyRosterUpdater-cli.exe` does the same without a window:

```
NHLLegacyRosterUpdater-cli list   --rpcs3 "C:\RPCS3\rpcs3.exe"
NHLLegacyRosterUpdater-cli update --rpcs3 "C:\RPCS3\rpcs3.exe" --source BLES021530202 --leagues nhl,ratings,national,ahl
NHLLegacyRosterUpdater-cli export --rpcs3 "C:\RPCS3\rpcs3.exe" --source BLES021530202 --out tables
```

`--leagues` takes `nhl`, `ratings`, `national`, `liiga`, `extraliga`, `shl`, `del`, `nl`, `norway`,
`ahl`, `chl` or `all`; without it, everything not marked NEW is updated. `--photos` adds photos and
logos (RPCS3 closed); `NHLLegacyRosterUpdater-cli photos remove` takes them away. `--savedata <folder>` can be
given instead of `--rpcs3` to name a save folder directly. `export` writes every table of a roster as
CSV with readable column names, for roster editors.

## Running from source

Python 3.10 or newer. The command line needs nothing else; the window needs one package:

```
pip install customtkinter
python -m legacy_roster                      # the window
python -m legacy_roster update --rpcs3 ...   # the command line
```

Developers and AI agents: start with [AGENTS.md](AGENTS.md). It leads to how the program works
([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)), how to change and test it
([docs/DEVELOPING.md](docs/DEVELOPING.md)), how to refresh data and release
([docs/MAINTAINING.md](docs/MAINTAINING.md)), what is done and what is next
([docs/ROADMAP.md](docs/ROADMAP.md)) and the save format ([docs/FORMAT.md](docs/FORMAT.md)).

## Credits and legal

Built on the 2025-26 community roster for NHL Legacy and on its author's team layout. NHL team
and player names belong to their owners. The photo edition carries photos and logos published by
the NHL, ESPN, the leagues and Wikipedia; no game files are included. It is not affiliated with EA Sports, the
NHL or the IIHF. Code is under the MIT licence.

A [Puck Peak](https://www.puckpeak.com) project (NHL & hockey analytics like never before): the
window wears Puck Peak's look and logo, and the logo links to www.puckpeak.com. It uses
[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) (CC0) and the font
[Source Sans 3](https://github.com/adobe-fonts/source-sans) (SIL Open Font License, included in
`legacy_roster/data/fonts`).
