# Changelog

What changed in each version, for players. Developers: details in [AGENTS.md](AGENTS.md)
("Current state") and [docs/ROADMAP.md](docs/ROADMAP.md).

## 0.10.2 (2026-10-12)

Fixes from testers of 0.10.1.

- **Saving a roster no longer fails with "Green / Red has 0 captain(s) and 0 alternate(s)".** It happened after a goalie or
  skater was moved off a team that then could not dress 2 goalies and 18 skaters: the team lost its captain and alternates and the
  safety check refused to save. The Roster editor now says so when you press Apply ("Seattle Kraken would have only 1 goalie. A team
  needs 2 goalies and 18 skaters.") and the player stays where he is. The safety messages also call those two teams Seattle
  Kraken and Vegas Golden Knights instead of "Green / Red" and "Black / Blue".
- **The game's own roster works with more kinds of game folders.** "The game's icon was not found" came up when the game
  folder had a different layout; the program now takes the icon from wherever it lies, and uses its own picture when there is none,
  so the roster is still made. (If the game still says "no disc": make sure you start from the version listed in RPCS3, and use
  this version; older ones had other problems with it.)
- **Equipment: only gear the game can draw.** The game's table holds the sticks, gloves, skates and helmets of NHL 10 to 14 too,
  and NHL Legacy draws those plain blue. The Equipment window now lists only the models Legacy has pictures for (what a player
  wears now always stays listed). Goalie pads, blockers, trappers, sticks and masks too.
- **Equipment and "Jerseys and ice..." fill the whole window**, with bigger pictures.
- **The editor shows the player type** (GRN, PLY, SNP, PWF, TWF) next to the overall. The game works out its own overall from the
  ratings and that type, so the number can differ from the one the editor shows (your edited ratings are in the game as you set
  them). Making the editor's overall match the game's exactly is planned.

## 0.10.1 (2026-10-11)

- **Easier short names for European clubs** on the scoreboard and in Select Teams: three letters, the way each club is best
  known: Frölunda **FRO**, Färjestad **FAR**, Davos **DAV**, Servette **SER**, Nürnberg **NUR**, Sparta **SPA** and so on for
  the SHL, Liiga, Extraliga, DEL, National League and Norway. (The old ones were the leagues' own codes: FHC, FBK, HCD, GSHC ...)
  AHL and junior clubs keep theirs. Run the update once more with "Photos, logos and team names" on to get them.

## 0.10.0 (2026-10-11)

- **The program looks for a newer version** when it starts (at most twice a day, silently when you are offline). If one is out
  it asks: **Update now** downloads it, checks the file, and restarts into the new version; **Later**; or **Skip this version**.
  Your settings and rosters stay. It can be switched off in step 1. Ratings and league data are also downloaded from the
  newest release, so they stay fresh between versions. (Windows only; Mac and Linux are shown the download page.)
- **"Start RPCS3" from the program** no longer ends in RPCS3's error "vcruntime140.dll was incorrectly installed": RPCS3 was
  given the program's own temporary folder in its search path and loaded our copy of that file. (A first fix only cleaned the
  path; the program also told Windows to look in its own folder first. Both are cleared now.)
- **Goalies' equipment and a picture of your own on the mask.** On a goalie's card, **Equipment...** has the mask, pads, blocker,
  trapper, stick, tape, jersey tuck and neck guard (the game's own choices, with its pictures). **My picture...** puts a picture
  of your own on his mask (512 x 512; **Save the mask layout to paint on** gives you the game's own to paint over). The goalie gets
  a mask number nobody else wears, so no other goalie changes; it shows in the game after "Photos, logos and team names" is run.
  A goalie's jersey is his team's jersey: use **Jerseys and ice...** (My picture) for it. Not played in the game yet.
- **Equipment in the Roster editor.** On a skater's card, **Equipment...** opens the game's own choices: stick (with the game's
  menu pictures), tape (black / white), helmet, visor, gloves, skates, jersey tuck and sock tuck. **Apply to this player**, or
  **Apply to the whole team** for tape, helmet, visor and the tucks. Kept in My edits and applied after every update. The game has
  2014 models only: pick the nearest to what the player uses. Which tuck number is which (front /
  back, none / short / long / full) is a guess from the game's words until someone checks it in the game.
- **Short team names on the scoreboard.** Clubs whose name the game already knows kept their old short code (Frölunda
  showed "VF" instead of "FHC"). The short codes are now written for every club. Run the update once more with
  "Photos, logos and team names" on.
- **Utah's jersey** no longer shows a faint Arizona coyote under the new logo (the shine map still carried it).
- **Helmets:** Utah, Seattle and Vegas now have their own logo on the helmet, and their helmets, gloves and gear are in
  their own colours instead of Arizona's red and the All-Star colours.
- **Centre ice (Utah):** the rink picture under the centre-ice logo no longer shows the coyote.
- **Team logos** on the team screens (top left) were drawn a little up and to the left of their frame; they are now centred.
- Not done yet: the home ice of Seattle and Vegas still uses Nashville's centre logo (they share its arena in the game's files).

- **A new window in the look of the game's menus.** Stadium blue, the white and red arc, the Help bar at the bottom
  with the keys (Enter updates, D shows the details, L1 / R1 or Ctrl+Page Up / Page Down switch tabs). The window no longer flickers or tears when
  you move it or change its size, and buttons, tabs and lists move smoothly.
- **A real progress bar** in the Help bar, with the percentage and what is being done right now.
- The result of an update opens in its own panel next to step 2 and stays (dimmed) while the next update runs.
- Questions (delete a roster, restore default, close while working) and the Roster editor's windows (Team, My edits,
  Jerseys and ice) now open inside the window.
- Roster editor: click a column title to sort the players, arrow keys move through the list, Ctrl+S saves.
- Roster editor: a rating below 40 that the game's own roster gives a player (for example a defenceman's Faceoffs)
  no longer stops Apply.
- Windows: the window needs Microsoft Edge WebView2 Runtime (part of Windows 11 and an updated Windows 10). Without it
  the old window opens, as before.

## 0.9.3 (2026-10-11)

- **Game crash in Select Teams** (switching league, for example to the Czech one). The team names the program wrote were
  longer than the game has room for. Names are now cut to fit the game's own limits (long names split over two lines,
  for example "Motor České" / "Budějovice"), and a text file that would still be too long is not installed.
  Run the update once more with "Photos, logos and team names" on to rewrite the names.
- **Likely real cause of that crash:** the program wrote some team name lines as an empty text (for example the small line
  above "Timrå IK"); the game's own files never do that and Select Teams crashed on those teams. Empty lines are now written
  as the game writes them. Run the update once more with "Photos, logos and team names" on.
- **Restore default** put back the pictures but left the roster as it was: it took the roster you were restoring (made
  by this program from the game's own roster) for the game's own roster. It now starts from your game disc.
- **"Something went wrong: 273 does not fit in 8 bits"** (a tester with the American game and rosters of the game's own
  layout). A placeholder player record with an impossible birth year made the draft step fail; such records are now left alone.
- **Roster editor ratings.** Changes you typed but had not pressed Apply on are now taken when you save or click another
  player, and a player who is also on a national team gets the new ratings on both cards.
- **First start without any saved roster.** If RPCS3 does not list your game, the window asks you to pick the game
  (.iso file or its folder) and starts from the game's own roster. Command line: `--game`. A new save never takes the
  game's own slot (...00) any more; the first one is ...01.

## 0.9.2 (2026-10-07)

- **Linux fix** (from a tester's own fixes, who ran it on Linux). The Linux window now starts (it stopped at start before).
  Teams without an IIHF roster, such as Russia, no longer end up with too few defencemen and left empty: places are kept for
  every position.

## 0.9.1 (2026-10-07)

- **Restore buttons.** Every row in "What should be updated?" has a **Restore** button: press it and, in the next save, that part
  comes back as the game had it (press again to undo). Rosters (NHL, ratings, national teams, leagues) start from the game's own
  roster, with the rows you left on applied on top; the calendar is the game's own calendar (Season mode and Be a GM have their
  complete 82-game season back); "Photos, logos and team names" puts the game's own pictures, team names and jerseys back.
  The game's own roster is read from the game's clean roster save (`...0200`) when it still is EA's own, otherwise from your game disc.
  It is only read, never changed.
- **Restore default.** One big button puts everything back: rosters, calendar, pictures, team names and jerseys. It asks first, then saves
  as a new roster or replaces the picked roster (after a backup copy), as you chose in step 4.
- Not changed in this version: the calendar still has the 30 original teams, so teams play 76-80 games; use **Restore** on the
  calendar row if that bothers you in Season mode.

## 0.9.0 (2026-10-07)

- **New jerseys and centre-ice logos for Utah, Seattle and Vegas.** With "Photos, logos and team names" on, the update
  also installs home and away jerseys, pants, socks, number sheets and Select Jerseys pictures in each club's colours with
  its logo, and a centre-ice logo with the arena's name (Delta Center, Climate Pledge Arena, T-Mobile Arena). They are made
  on your PC from your own game disc, and "Restore the game's own pictures" puts the old ones back. Not yet checked in the
  game (`looks-test` writes only these files). The older Arizona versions, the Jets throwbacks and the old All-Star versions
  are left as the game has them.
- **Export only SYS-DATA roster (no RPCS3 needed).** Tick it in step 1, pick the community roster's SYS-DATA file in step 2, press
  **Make new roster**: the updated SYS-DATA is written into a new folder next to the program. For a Mac or Linux PC that cannot run
  RPCS3. No pictures, logos or jerseys are in it. (Replaces the link "No RPCS3 on this computer?"; the command line has `export-roster`.)
- **Roster editor: "Jerseys and ice...".** Pick an NHL team, press the button: change its two colours and crest, and for each jersey version
  the game has (the ones "Change Jerseys" shows) choose the game's own, a jersey made from your colours, or your own picture
  (a flat 1024 x 1024 colour map; the window saves the game's own as a template to paint on). The centre-ice logo can be the game's
  own, drawn from the team's logo and arena name, or your own picture. Kept on your PC and made in every update with "Photos, logos
  and team names" on (and My edits on); a version set back to "the game's own" is put back as it was.

- **Calendar 2026-27 is a normal step now (on by default).** The owner played all four test calendars: every game and
  date matched NHL.com. The game still calls the year 2015, and Seattle and Vegas cannot be in Season mode or Be a GM
  (those modes are built for 30 teams), so the calendar has the 30 original teams (they play 76-80 games).

## 0.8.1 (2026-10-06)

From the owner's tests of 0.8.0. Confirmed in the game: the Tampa Bay and Toronto logos, the team names on
the Select Teams screen, Delete / Open folder, and Season mode with a full update.

- **Update the roster itself:** step 4 now has **Update this roster** (the default: the roster you picked
  gets the newest data, so you do not collect new folders and load them) and **Save as a new roster**. Before a
  roster is changed, its old version is copied to the program's backups folder (the last 10 of each are
  kept). RPCS3 must be closed. The game's own roster is always saved as a new roster.
- **Roster editor:** no more As is / To be. It shows the roster you picked as it is, and **Save** updates that
  roster or makes a new one, like the Update tab.
- **Calendar 2026-27 (a test, switched off):** the real 2026-27 games and dates for Season mode (30 teams;
  `calendar-test` also makes a 32-team version). Switch it on in step 3 ("Calendar 2026-27 (test)") to try it.
  Not played in the game yet, so the game may still show its old dates.
- **Utah, Seattle and Vegas on the game's own roster:** the arena names, cities and team colours of the
  community roster (it has them already). `rendering-test` checks whether the game takes 3D textures
  (jerseys, the ice) from loose files, the first step towards new jerseys and a Utah centre-ice logo.
- **Manage your saves in the window:** each roster in step 2 has **Open folder** and **Delete**
  (to the Recycle Bin, with a question first; not while RPCS3 is running).
- **Logos:** the Toronto calendar and wide logos are blue now, like the game's own (Tampa Bay's stay white,
  as the game's own are). The Tampa Bay, Toronto, Washington, Boston and Vancouver logos on the favourite-team
  screen (and the plain and Dynasty logos) are no longer washed out white: they have their own
  colours again.
- **Team names on the team-select screens:** Play Now's "Select Teams" showed "Black All-Stars"
  for Vegas, "Green All-Stars" for Seattle and "Arizona Coyotes" for Utah, and old names for the
  rebuilt clubs. The names are now written to the lines that screen reads.
- **Season mode crash:** the game crashed when it started a season with a roster made by 0.8.0 (the
  community roster and the game's own roster play it fine). It was not an Arizona or Utah problem:
  the community roster carries a player the game had already removed (Jonathan Drouin), and the
  update made him a free agent. He is taken off first now; checked in the game (the full update plays
  Season mode). A roster made by 0.8.0 gets its free agents on new links when updated again (not yet
  played). The command `season-test` makes a set of test rosters if it ever happens again.

Not yet checked in the game: the calendar, which roster the game loads at start after "Update this roster",
the arena names and colours of the game's own roster, and the loose 3D textures test (`rendering-test`).

## 0.8.0 (2026-10-05)

From the testers' feedback on 0.7.0.

**Players and rosters**
- **Free agents:** retired players leave the free-agent list (Datsyuk, Price, Rask...); NHL players
  without a contract today are on it (Reimer, Toews, Quick), and are added to the game if it did
  not have them.
- **Draft:** every player has his real draft: year, round, pick and team (NHL drafts since 2005).
  Will Smith and Stenberg are right now.
- **Draft prospects** play for a real club of their country (the CHL for North Americans) instead of
  custom "Prospects" teams, where the game's draft did not see them. A junior missing from his
  league's list stays with his club (Landon DuPont stays in Everett).
- **NHL.com's height, weight and hand** for every NHL player; players with the same name are no
  longer mixed up.
- **Goalie equipment** in the new team's colours after a trade.
- **Your own team for a missing club:** name a custom team after a club the game has no place for
  (Jokerit, Ajoie, Penticton, Coachella Valley...) and the update fills it with that club's players.

**Pictures**
- Logos have the game's own size (they no longer cover the record or spill out of the calendar);
  the Lightning logo is white, the Capitals logo has white edges.
- Extraliga players have photos now, and so do juniors their league's list leaves out (last
  season's photo). Studio photos on a grey backdrop are cut out like the rest. About 6,100 photos
  come with the program.
- Pictures that could not be installed are named in the List of changes.

**The program**
- Runs on **macOS and Linux** too (it finds RPCS3's folder there by itself).
- **Works without RPCS3:** pick a folder with roster saves instead (CrossOver, Wine, saves from
  elsewhere).
- The window keeps every step and your rosters in view after an update, and the steps stand out
  more.

Not yet checked in the game: free agents, draft data, prospects in the draft, logo sizes, goalie
gear, your own team. Known: Season mode crashed once when picking Arizona/Utah; it is being looked
into (tell us if it happens to you).

## 0.7.0 (2026-10-04)

- Fixed: updates stopping with "CERTIFICATE_VERIFY_FAILED" while checking NHL players.
- Fixed: the program closing at start with "couldn't open ... logo_100.png" (an antivirus or a
  cleaning program had removed its files).

## 0.6.0 (2026-10-04)

- No roster needed: start from the game's own roster on your disc.
- Positions from NHL.com, wingers on their own side of the lines.
- Today's logos on the favourite-team screen.
- One program with every picture inside; your own pictures are always kept.
- A clearer result and a List of changes grouped by team; EU / NA flags.
