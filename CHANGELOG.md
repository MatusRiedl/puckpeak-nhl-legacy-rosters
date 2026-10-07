# Changelog

What changed in each version, for players. Developers: details in [AGENTS.md](AGENTS.md)
("Current state") and [docs/ROADMAP.md](docs/ROADMAP.md).

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
