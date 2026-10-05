# Changelog

What changed in each version, for players. Developers: details in [AGENTS.md](AGENTS.md)
("Current state") and [docs/ROADMAP.md](docs/ROADMAP.md).

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
