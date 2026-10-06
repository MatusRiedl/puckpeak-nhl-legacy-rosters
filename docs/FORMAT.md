# NHL Legacy roster save format

What is known about the roster save of NHL Legacy Edition (PS3, `BLES02153` / `BLUS31540`),
and the rules the game enforces on it. Everything here is implemented in `legacy_roster/`.

The game gives no error for a bad roster: it crashes in a menu, or silently keeps the previous
roster. `legacy_roster/verify.py` checks every rule in section 5 before a save is written.

## 1. Save folder

A roster save is a folder `<TITLEID>02NN` in `dev_hdd0\home\<user>\savedata` holding `ICON0.PNG`,
`PARAM.SFO` and `SYS-DATA`. Other saves of the game use other numbers (`0000` profile, `08xx`
hockey card, `13xx` Build Your AI).

`PARAM.SFO`: `SAVEDATA_DIRECTORY` must equal the folder name; `SUB_TITLE` (up to 127 bytes) is
the roster name shown in the load list; `DETAIL` is `Rosters`. RPCS3 saves are not signed.

**EU and NA.** The European version is `BLES02153`, the North American `BLUS31540`. Their saves'
`PARAM.SFO` differ only in `TITLE` ("NHL™ Legacy Edition" / "NHL® Legacy Edition") and the folder
name (`PARAMS` is empty in RPCS3 saves). Both read the same `SYS-DATA`: the community shares one
roster file for both, dropped into `BLES021530200` or `BLUS315400200`. Both discs hold the same
`cache.big`, `nocache.big` and `cacheboot.big` contents (same entry counts, same 8 text files).

## 2. SYS-DATA wrapper

Big-endian unless noted. File length = `0x2C` + section size (2,456,120 bytes for rosters).

| Offset | Content |
|---|---|
| 0x00 | 16-byte magic `PS3RosterFile` |
| 0x10 | CRC-32 (zlib) over `[0x1C, end of file)` |
| 0x14 | version 4; 0x18 zero; 0x1C compressed flag; 0x20 a small counter |
| 0x24 | section size |
| 0x28 | CRC-32/BZIP2 (poly 04C11DB7, init and xorout FFFFFFFF, not reflected) over the section |
| 0x2C | zlib length (little-endian), zlib stream at 0x30, zero padding to the section end |

zlib level 6, memLevel 9, wbits 15 reproduces the game's own output byte for byte. Saves written
by other tools may be compressed differently; only the content has to match.

## 3. The database inside (EA "TDB")

- `DB` header (0x18 bytes): `44 42 00 08`, `01000000`, db size, 0, table count, CRC-32/MPEG-2
  (init FFFFFFFF, xorout 0) of bytes 0..0x14.
- Table index: 4-character tag + offset per table, then the tables, then a trailer.
- Table: 40-byte header, 16-byte field definitions, fixed-length bit-packed big-endian records
  (`max records x record length`), optional tail. Header +0x08 record length, +0x14/+0x16 max and
  current record count, +0x1C field count, +0x24 CRC-32/MPEG-2 of header bytes 4..0x24.
- Field definition: type (0 = UTF-8 string, 3 = unsigned integer), bit offset, tag, bit count.
- **Checksum chain.** Each table's first four bytes hold the CRC-32/MPEG-2 of what precedes it:
  the table index for the first table, the previous table's bytes from 0x28 on for the others.
  The last table ends with the CRC of its own bytes from 0x28. A broken chain makes the game
  ignore the file without a message.
- Records past the current count hold stale data. Table order has no meaning.
- **Header word at 0x18** is `0000ffff` in every table of the game's own roster, ROSTER2526 and what this
  program writes. The community's 2026-27 roster has `00010b81` in `caBZ` and `000100e1` in `ulGe`:
  flag 1 and a row, the last row the game removed (link row 2945 and entry row 225 are Jonathan Drouin's;
  he has no contract team and is on no free-agent list: a player removed in the game before the roster
  was saved). Our update did not know, treated him as a player of St. Louis, made him a free agent, and
  Season mode crashed on his link (`0x00381c24`, owner 2026-10-06). `builder.drop_removed_player` removes
  the two rows before anything else and clears the words; `verify.py` insists they are `0000ffff`.
  The meaning is inferred from this one roster; removing the player fixed Season mode (owner, 2026-10-06).
  A roster made by 0.8.0 from it keeps the words but the rows moved: `stale_markers`, free agents relinked.

## 4. Names and meanings

Table and field tags in the file are scrambled (`cPbu`, `RMbQ`...). The game disc carries the
real names: `db/nhlng-meta.xml` inside `PS3_GAME/USRDIR/cacheboot.big` lists every table and
field with tag and name. `tools/decode_schema.py` turns it into `legacy_roster/schema_names.py`,
and every table then answers to both (`P.get(i, 'lastname')` equals `P.get(i, 'RMbQ')`).

The tables that matter:

| Tag | Name | Notes |
|---|---|---|
| `ttOk` | exhibitionteams | 252 teams, table full. `league`, `fullname`, `shortname`, `artabbr`, `artid`, `ahlaffiliate` |
| `cPbu` | exhibitionplayerbiotable | one record per player; key `game_id` |
| `ulGe` | exhibitionrostertable | one entry per player per team; 71 one-bit line slots |
| `caBZ` | exhibitionplayers | link id (`index`) to `playerid`; roster entries point at links |
| `QEoV` | exhibitionfreeagents | link ids of unattached players |
| `yvSd` / `yuHm` | exhibitionskaterai / exhibitiongoalieai | attributes, keyed by `game_id` |
| `lVMf` | exhibitiongoalieequipment | a goalie's gear, keyed by `game_id`: `pads`, `blocker`, `trapper` models and nine zones of colour each (`padszone1color_r` ... `trapperzone9color_b`), `showcustomcolors` |

**Teams** (`ttOk.league`): 0 NHL, 1 AHL, 2 SHL, 3 Liiga, 4 DEL, 5 Extraliga, 6 National League,
7 Norway, 8 national teams, 9 OHL, 10 QMJHL, 11 WHL, 12 Top Prospects, 13 custom, 14 Winter
Classic, 15 EASHL.

**Players.** `position` 0 C, 1 LW, 2 RW, 3 D, 4 G. `handedness` 0 left. `height` inches - 54,
`weight` pounds - 120. `intlcountry` is a country code; `state` is a province/state code for
North Americans and the country code for everyone else. `headid` is the 3D head model (60000
and up are generic heads), `artid` + `hasportrait` the menu photo, `audioid` the commentary
name. `team` is the contract team + 1 (0 = none), `contractlength`, `contractdollars`.
`proteam` and `draftteam` are NHL team + 1 in five bits (Vegas, slot 31, cannot be stored).
`draftyear` is the year - 1900, 255 for undrafted; `draftround` (4 bits) and `draftposition` (9
bits) are the round and the **overall** pick (the disc: Gaudreau round 4, pick 104; Saad round 2,
pick 43). EA gives a junior who is not drafted yet his draft year with round 0 (2014-2017 on the
disc), and the disc's Legacy Edition already holds the 2015 draft. `draft.py` writes NHL.com's
picks (0.8.0).

**Goalie equipment.** EA painted every goalie's gear in his 2014 team's colours on white
(`showcustomcolors` 1 for all 62 NHL goalies on the disc; Hiller's pads Calgary red and gold).
The colours are free RGB values; `Builder.goalie_gear` repaints the coloured zones of a goalie who
changed club (0.8.0, waiting for the in-game check).

**Attributes.** Stored value = rating - 36 (six bits, ratings 36 to 99). The field for each
attribute is in `legacy_roster/schema.py` (`EA_SKATER`, `EA_GOALIE`); for example `c_speed` =
`bEdA`, `c_faceoffs` = `KrwV`, `c_gsh` = `DTrq`. `c_potential`, the growth fields and the
traits are not published by EA and are left alone.

**Roster entries.** `key` = team x 40 + slot. `playerindex` is the link id. `rosterstatus` = 1
when dressed. `captain` 1 = C, 2 = A. `playerstyle` equals the player's style in his attribute
record. The line slots are named: `l1lw l1c l1rw l1ld l1rd` ... `l4rw`, `pp1*`, `pp2*`,
`pp4_1*`, `pp4_2*`, `pk4_1*`, `pk4_2*`, `pk3_1*`, `pk3_2*`, `ot_1*`..`ot_3*`, `s1`..`s5`, `x1`,
`x2`, `g1`, `g2`.

## 5. Rules the game enforces

1. All five checksums (section 2 and 3).
2. Roster entry keys are team x 40 + slot, slots 0..n-1 without gaps, at most 40 per team.
   Breaking it crashes Roster and Team Management.
3. A player's contract team must be a team he is on. NHL players need a length and a salary;
   free agents have no contract fields set.
4. Each line slot has at most one holder per team; a player is dressed exactly when he holds a
   slot. NHL and national teams dress 20: 12 forwards, 6 defencemen, 2 goalies.
5. Every NHL team has three letters: one C and two A, or three A.
6. The free-agent list only holds links that no roster entry uses.
7. **Hard limits.** No team can be added (the team table is full and team ids are 8-bit) and no
   team can change league. Only existing slots can be refilled.

## 6. The community rosters

The updater works on this roster family (the 2025-26 roster "ROSTER2526" and its successors); its
conventions differ from the stock EA roster.

- 32 NHL teams: slot 22 (the old Arizona slot) holds Utah, the two All-Star slots 30 and 31
  hold Seattle and Vegas. Custom teams 222-233 are copies of twelve NHL teams with current
  branding and must mirror their primary team. Custom slots 234 and 235 are two AHL teams.
- Birth years are stored as year - 1910 (stock: year - 1900), so ages are right in a game whose
  calendar starts in 2015.
- About 1,250 blanked player records (last name starting `ZZ`) are spare records for new players.
  About 1,250 more teamless records still carry EA's − 1900 birth year (their draft year shows it).
- The European league slots hold draft-class pools and NHL prospect pools; 27 club slots are
  empty. Pool slots got pool names and pool art abbreviations (`P261` …); their original art
  (for example `BIF`, `VF`, `HCAP`, `STAV`) is in the stock database on the disc.
- Eight national teams are empty.
- AHL, CHL and pool teams do not have complete lines.
- **Names of the NHL slots in the save** are still the old ones: slot 22 "Arizona Coyotes" (art
  `PHX`), 30 "Green / Red", 31 "Black / Blue" (All-Star art `EAS` / `WES`). Utah, Seattle and Vegas
  carry their names and branding through custom slots 229, 228 and 226; in the game's menus they
  are listed under the custom teams, not the NHL (owner, 2026-10-03). AHL abbreviations
  (`abbrname`) were stale in the base (Utica `ALB`); the AHL step writes current ones.
- National-team goalies have second player records of their own (same name and birthdate).
- **The community's 2026-27 roster** (shared as one SYS-DATA, October 2026) keeps the same layout,
  with these differences:
  - slots 22/30/31 are named Utah Mammoth, Seattle Kraken, Vegas Golden Knights, with a few more
    team fields changed (colours, `Nzao`, `aDub`; the update leaves them as they are);
  - the custom copies 222–233 are out of step with their NHL teams (14–25 of ~25 players shared;
    Ben Hutton only on the Golden Knights copy);
  - France, Germany, Italy, Latvia, Slovakia and Switzerland are empty; Czech Republic and
    Denmark dress 20 but hold no line slot (the community ships it so; the update deals lines);
  - 6,770 player records (25 more), 52 free agents;
  - slot 67 is named "Karlskrona Hockey" with no players.

**The game's own roster** (`db/nhlng.db` on the disc; `stock.py`, 0.6.0). Facts measured on the NA
disc (the EU one has the same archives):
- **Tables.** The database has 134 tables. All 39 of a roster save are among them, with the same
  record lengths and field definitions. A roster save differs only in these points:
  - it holds those 39, in its own order (`stock.ROSTER_MAX`);
  - each table has room to grow: the save's maximum is the disc's count plus room (cPbu 5,632 →
    7,988, ulGe 5,532 → 10,879, caBZ 6,087 → 9,955);
  - every table header has byte 7 = 6 (disc 2);
  - the player-link table `caBZ` carries one index: header byte 0x1D = 1, then 16 bytes after its
    records, `prCe` 01 01 00 00 00 00 00 02 00 00 00 01;
  - the database ends with four `DB` bytes;
  - the wrapper is `PS3RosterFile`, version 4, compressed, counter 1, section 2,456,120 − 0x2C.
- **Layout.** Every club slot has its real 2014-15 club with players. Slots 30/31 hold the All-Star
  teams (49 players, all also on their own teams). Custom slots 222–251 are "Custom Team 00–29",
  switched off (`active` 0) and empty. The 21 national teams have squads; there are 340 free
  agents. Birth years are year − 1900; there are no blank records.
- **Player ids** (`game_id`) are 14 bits, and the disc already uses ids up to 16,343. New records
  take free ids in the gaps.
- **A PARAM.SFO** for a version that has no save to copy: `savedata.roster_sfo` makes one from
  scratch that is byte-identical to the game's own (14 keys, `*ICON0.PNG`/`*SYS-DATA` flags 0/1,
  `RPCS3_BLIST`, `DETAIL` "Rosters", …). The icon is the disc's `PS3_GAME/ICON0.PNG`.
- **Not proven yet:** that the game loads a roster made this way (`cli stock-test`, ROADMAP).

**Table capacities** (current / maximum records in a roster save):

| Table | Current | Max | Notes |
|---|---|---|---|
| `cPbu` players | 6,745 | 7,988 | could grow; untested in the game |
| `yvSd` / `yuHm` skater / goalie attributes | 6,056 / 689 | 7,331 / 957 | one row per player, by `game_id` |
| `ulGe` roster entries | 3,600 | 10,879 | |
| `caBZ` links | 3,611 | 9,955 | |
| `QEoV` free agents | 17 | 1,767 | |
| `ttOk` teams | 252 | 252 | full |
| `caBZ` / `vaHq` | | | `vaHq` (draft picks) points at player links too (`playerindex`); links nothing uses are dropped by `Builder.finish` |
| `vaHq` draft picks | 1,260 | 1,260 | full: 6 years × 30 teams × 7 rounds |
| `xieT` salary extras | 30 | 30 | one per NHL team 0–29 |
| `ihmS` / `byED` NHL schedule / future schedule | 1,231 | 1,291 | see section 8 |

## 7. Game files and overrides

The disc holds a few large EA "EB" v3 archives (`cache.big`, `nocache.big`, ...; layout in
`tools/isotools.py`). Before reading an archive the game looks for a loose file under
`dev_hdd0\game\<TITLEID>\USRDIR\`, so single files can be replaced without repacking:

| What | Path |
|---|---|
| Menu portrait | `fe/ion/artassets/playerheads/p8001_12000/p<artid>.big` (folders `p0_4000`, `p4001_8000`, `p8001_12000` for every id above 8,000, `silhouettes`; + `playerheadssmall`) |
| Team logo (menus) | `fe/ion/artassets/teamlogos/t<artid>.big`; variants `teamlogossmall/s`, `teamlogoswide/w`, `teamlogoscalendar/c`, `teamlogosdynasty/d`, `teamlogosreflection/r` (NHL only) |
| Text | `fe/loc/nhl_<lang>.db` (same TDB format) |
| Default database | `db/nhlng.db`, `db/nhlng-meta.xml` (in `cacheboot.big`, stored uncompressed) |
| 3D heads, jerseys, ice | `rendering/**/*.rpsgl` (`\x89RW4ps3`) |

**3D textures** (read 2026-10-06; `art/rpsgl.py`; archives `nocacherender.big` 1.7 GB and `cacherender.big` 1.4 GB, EU
and NA identical). A `.rpsgl` is a "chunkzip" (128 KB chunks of raw deflate) around a RenderWare PS3 file with
named DXT1/DXT5 rasters and a full mipmap chain; repacked with zlib level 9 it is byte-identical to the disc's.
Named by the team's numeric art id (22 Utah, 30 Seattle, 31 Vegas; the Arizona files are still the ones for 22):
`rendering/jersey/texlib_<style>_<art>_<variant>` (rasters `jersey_.._cm`, `_sm`, `_0_nm`, `font_..`; the same UV
layout for every team; Utah has variants 0, 1, 3, 4 in styles 0 and 1, 3 and 4 the home and away), `name_<style>_<art>_<variant>_cm`,
`pant/texlib_..`, `sock/sock_.._cm`, `icesurface/centerlogo_<art>_cm` (1024x1024 DXT5, the centre-ice logo;
`exhibitionarena.centericelogo` can name another team's), `icesurface_<arena art>_bm` (rink picture), `banner_`,
`crowd/prop_team_`. The menu previews of jerseys are `fe/ion/artassets/jerseys/jersey_<style>_<art>_<variant>.big` (BIGF,
readable as above). The game asks for `<game folder>/rendering/...` first (RPCS3 log), but **no loose rendering file
has been tried in the game yet** (`cli rendering-test`, ROADMAP "Jerseys and the ice"). The community roster already
has Utah, Seattle and Vegas arenas (`exhibitionarena` rows 181, 186, 162) and colours; the game's own roster has
Arizona's and the All-Star slots' (`builder.nhl_identity` sets them for that source).

**Which id.** A portrait file is named by the player's `artid` (`cPbu.rnOl`) and shows when `hasportrait`
is 1. A logo file is named by the team's `ttOk.artid` (NHL slots 0–31: the slot number; custom
teams 20000+).

**Art files.** Each `.big` above is a small `BIGF` archive:
- header: big-endian file count at +8, header size at +12;
- entries: u32 offset, u32 size, NUL-terminated name.

It holds an EA "Apt" UI movie:
- part `0` "Apt Data:1:5:4";
- part `1` "Apt constant file";
- a 288-byte part, and empty `sg1`/`sg2` markers;
- **one image**: RefPack-compressed (`10 FB` + 3-byte size), which unpacks to a DDS.

| File | DDS |
|---|---|
| portrait `p` | 512×512 DXT5, no mipmaps |
| small portrait | 256×128 DXT5 |
| silhouette | 512×256 DXT5 |
| logo `t` | 256×256 uncompressed 32-bit |
| logo `s` / `d` / `c` / `w` / `r` | 128×64 / 128×128 / 128×128 / 256×256 / 256×512 |

A community loose-file logo seen in the wild had the same layout with mipmaps in its DDS.

More details:
- **The Apt data part** (`0`) is itself RefPack-compressed in about 60 % of the files. The image is the
  RefPack part that unpacks to a DDS (`legacy_roster/art/bigf.py`).
- **Part names** (the movie's character ids: `7`/`6`, `3`/`2`, `157`/`156` …) differ from file to file.
  So a new art file is always made from an existing one of the same kind, with only the image swapped
  (`ArtFile.with_image`).
- **The 16-byte trailer** after the last part is no hash of the file, its parts or the image that we could
  find (MD5, SHA-1, SHA-256 tried). It is kept from the template, and the game does not mind (art test,
  2026-10-03).
- **Portrait geometry.**
  - 6,567 of 9,224 portraits are 512×512, the rest 512×256. The photo always sits in the top
    512×256: a cut-out (transparent background), the top of the hair at y 26, the middle of the head
    at x 235, the head 144 px wide at its widest, nothing below y 247 (medians of `images.head()` over
    the disc; the head width varies 8 % between players).
  - The small portrait (256×128) is the same picture at half size (top 13, middle 101, width 74).
  - Logos are drawn with transparency, inside an area that depends on the kind (medians of the
    disc's NHL logos, alpha above 40; `images.LOGO_BOX`): `t` 0.16-0.84 × 0.20-0.79 of the picture,
    `d` 0.14-0.86 × 0.19-0.83, `c` 0.05-0.70 × 0.05-0.62 (top left only), `w` 0.09-0.89 × 0.11-0.90,
    `s` 0.05-0.95 × 0.14-0.86. Drawn over the whole canvas (0.4-0.7) they covered the record on the
    team screens and spilled out of the calendar's cells. `t` has a white edge and a soft
    shadow; `d` is a small `t`; `c` is the logo enlarged and cut off on the right; `w` is a big
    zoomed piece faded to a circle; `s` is a banner in the team's colours with part of the logo.
  - `r` (256×512, `teamlogosreflection`, NHL art ids 0–29 on the disc) is the logo in the upper
    half (about 190×180 px around y 125) standing on a faint mirror image of itself that fades out
    within about 50 px; the rest is transparent. This is the picture of the favourite-team
    carousel ("Choose Your Favorite Team" on a new profile, owner's screenshot 2026-10-04: Utah's
    name with the disc's `r22`, the Coyotes). The carousel is sorted by city, so Utah sits where
    Arizona was. The updater writes `r` for the 32 NHL slots since 0.6.0 (Seattle and Vegas, 30/31,
    from `r0` as template).
- **Portrait ids.**
  - The disc's ids run 1–12,401 in three folders.
  - The community roster gives 134 players ids from 12,402 to 13,826, so a loose-file portrait pack of
    its own must exist; the owner's RPCS3 has none.
  - **Folder rule** (from the RPCS3 log): ids up to 4,000 are in `p0_4000`, up to 8,000 in
    `p4001_8000`, every higher id in `p8001_12000` (the game asked for `p8001_12000/p12402.big`).
  - `artid` is 16 bits; the updater gives new portraits ids from 20,000 (`art/portraits.py`).
- **Proven in the game (art test, 2026-10-03):** a loose portrait replaces the disc's (McDavid); a
  new id below 4,000 and one above the disc's range both show; a loose logo replaces the disc's (the
  Team Rosters screen shows the dynasty variant `d`). A missing loose file falls back to the
  silhouette. Nothing needs a mipmap.
- **Team names are not read from the save for most teams.** Slot 107 was "Kladno" in the save; the
  game still showed "Chomutov". The game takes them from its text file (below). Custom teams show
  the text whose key is their `shortname` (`LAS_VEGAS` shows "Las Vegas"; a shortname with no text,
  like "2026 Prospects 2", shows nothing). In the game (owner, 2026-10-04) texts the update added
  under "2026 PROSPECTS 2" and "Coachella Valley" for custom teams with those shortnames still
  showed nothing, while every changed text of an existing key showed (Utah, Timrå). The keys that
  work are all in the game's style (capitals, digits, underscores); since 0.5.0 custom shortnames
  are written that way (`2026_PROSPECTS_2`, `COACHELLA_VALLEY`) and added keys keep their case.
  Waiting for the in-game check.
- **Code.** Reading and writing: `legacy_roster/art/` (`disc.py` reads the player's own disc image or
  folder, `bigf.py`, `refpack.py`, `dds.py`). Photos and logos: `portraits.py` (ids in the roster),
  `images.py` (Pillow: cut-out, head finding, logo styles), `install.py` (download, write, back up,
  remove). The one-off in-game experiment is `lab.py` (`cli art-test`).

### The text file (`fe/loc/nhl_<language>.db`)

On the disc in `cacheboot.big`, one per language (`eng_us`, `fre_fr`, `ger_de`, `swe_se`, `fin_fi`,
`cze_cz`, `rus_ru`; `lng_lg` is the language list). The game reads a loose copy from
`dev_hdd0/game/<TITLEID>/USRDIR/fe/loc/` first (RPCS3 log). Code: `legacy_roster/art/loc.py`, which
rebuilds every language file of the disc byte for byte.

- **Layout.** A "DB" with one table `LanguageStrings` (`GJCv`): `hashid` (`jKhj`, 32 bits),
  `stringid` (`VhAs`, type 13) and `sourcetext` (`bYbZ`, type 14), 16-byte records sorted by hash.
  Types 13/14 are Huffman-compressed strings stored after the records.
- **Huffman tree.** Node *n* is the 2-byte entries 2*n* (bit 0) and 2*n*+1 (bit 1). An entry (k, 0)
  goes to node k, an entry (0, c) is byte c. Node 0 is the root; the English tree is 660 bytes.
- **Strings.** Each one sits at its record's offset (from the start of the tree), with a length
  prefix of 1 byte (key) or 2 bytes (text) in bytes, then the bits, most significant first, in
  bits // 8 + 1 bytes. Offset 0xFFFFFFFF means no string.
- **After the strings.** Zero bytes to a multiple of 8, then the CRC-32/MPEG-2 of the table from
  0x28 on (the same chain rule as the saves). Table header +0x10 = where the strings end.
- **Key hash.** `hashid` = `zlib.crc32(key.upper(), 0xFFFFFFFF) ^ 0xFFFFFFFF` for every key the game
  builds at run time (team and city keys). About 45 % of the fixed keys (11,717 in English) have
  other hashes that no rule tried explains (CRC-32 variants, FNV, djb2, sdbm, any case); those are
  looked up by their stored hash. The meta file declares `hashid` a signed 32-bit key with an index
  sorted on it; the records are sorted unsigned and the game copes. Stored keys keep their own case
  (`NHLTeamName_MOD`, `NHLTEAMNAME_CHOM`, `ChangeDay`); the Kings copy's shortname
  `NhlCityName_13` has no findable text (the disc's `NHLCityName_13` entry is one of the odd hashes).
- **Team keys.** For a team with art code X the game asks for `NHLTeamName_X` (full name),
  `NHLCityName_X` (city: the Team Rosters header), `TXT_NICKNAME_X`, `TXT_NICKNAME_ALT_X` and
  `X_XLA_TEAM_X` (abbreviation). NHL slot 22 has art `PHX`, slots 30/31 `EAS`/`WES`. The disc
  already has some clubs the base roster does not use (`KLA` Kladno).
- **Select Teams keys (found 2026-10-06).** Play Now's "Select Teams" and Season's team lists read
  other texts: `TEAMLINE1_X` (the small line above the name: the city, or the nickname for a name
  that ends in its city: `Piráti` / `Chomutov`; empty for `MODO Hockey`), `TEAMLINE2_X` (the big line;
  NHL clubs carry ® or ™), `NICKLINE2_X` (the big line again, NHL and some clubs only) and
  `NHLTeamName_Abbr3_X` (the short code). The NHL slots also have texts under their number:
  `NHLTeamName_22`, `NHLCityName_22`, `CITYLINE1_22`, `NICKLINE2_22`, `NHLTeamName_Abbr3_22` (22, 30,
  31 held Arizona, Eastern and Western All-Stars; `Logo46` still reads Arizona, not found on a screen).
  Their hashes are not the CRC of their key (0 of 174 `TEAMLINE1_` match), so `LocFile.set` would add a
  text nobody asks for: `LocFile.set_existing` finds them by their stored key (`set_select_lines`,
  `loc.select_lines` splits a name the game's way). Until 0.8.0 the update wrote only the five keys
  above, so Select Teams showed 'Black ALL-STARS' for Vegas, 'Green ALL-STARS' for Seattle and
  'Arizona COYOTES' for Utah, and the old names of every rebuilt club (owner's screenshots,
  2026-10-06). `loc.NAMES_VERSION` rewrites the installed files when the set of texts changes.

## 8. Schedules

Each league has a schedule table in the roster save except Norway:
`nhlschedule`, `nhlfutureschedule`, `favoriteteamschedule`, `ahlschedule`, `ohl…`, `qmjhl…`,
`whl…`, `swedish…`, `finnish…`, `german…`, `czech…`, `swissschedule`.

- **Fields.** Every record has `round` (3 bits), `status` (2), `day` (5, 0-based), `month` (4, 0-based:
  9 = October), `index` (= row number) and `home` / `away` team ids. The team ids are 5 bits in the NHL
  and AHL tables and 4 bits in the European ones. There is **no year**.
- **What the NHL tables hold** (read 2026-10-06, 81 of Anaheim's 82 games checked against NHL.com).
  `nhlschedule` is the real 2015-16 calendar before any revision (7 Oct to 9 Apr, with a 29 Feb); the
  owner's Season-mode calendar screenshot matches it row by row (Anaheim: 10 Oct at San Jose, 12 Oct home
  Vancouver ...). `favoriteteamschedule` is a byte copy with 200 spare rows (what the game uses it for is
  unknown). `nhlfutureschedule` is the real 2014-15 calendar. Only slots 0–29 play, 82 games each (41 home);
  slots 30/31 meet once (31 Jan: the All-Star game). Identical on the disc and in every community roster; the
  AHL and WHL tables differ in the community roster (2015-16 AHL, a WHL cut to 454 rows, not sorted).
  The year the calendar shows ("October 2015") is in no table; October-February 2015/16 and 2026/27 have
  the same weekdays (March-April: a day off if the game's February has 29 days).
- **The 2026-27 calendar** (`schedule.py`, step `schedule`, off by default, `cli calendar-test`): NHL.com's
  `club-schedule-season/<ABBR>/20262027` gives 1,344 regular-season games (84 per team), 29 Sep 2026 to 10 Apr
  2027, stored in the data pack part `schedule`. They do not fit (1,291 rows): the update writes only games
  between slots 0-29 (1,180; 76-80 per team) or, as a test, all 32 teams trimmed to 80 each (a flow over
  home/away pairs, `schedule.trim`). Written into `nhlschedule` and `favoriteteamschedule`; `verify.py` /
  `schedule.check` insist on the game's rules (rows in date order, valid dates Sep-Jun, nobody twice a day,
  `index` = row, both tables equal, no other schedule table changed). Not played in the game yet.
- **Room.** The maximum is the stock count + 60 (`maxinsert` in `nhlng-meta.xml`). That is 1,291 rows
  for the NHL. 32 teams × 82 games = 1,312 do not fit; 80 games (1,280) would.
- **Divisions.** These live in `ttOk.conferencegroup` / `divisiongroup` (6 bits):
  - NHL: conferences 1 West, 2 East; divisions 3 Pacific, 4 Central, 5 Atlantic, 6 Metropolitan;
  - slots 30/31: 2/2 and 1/1.
- **Be a GM / season tables** (`league…`, `dynasty`) are not in the roster save. The game builds them
  when a mode starts; `leaguegmdata` has 30 rows.

docs/SEASON_PLAN.md uses these facts.

## 9. Debugging with the RPCS3 log

RPCS3 keeps `log\RPCS3.log` open; read it with shared access. Useful searches:
`ShowSaveDataList` (which roster was loaded), `Access violation` (crashes),
`sys_fs_open(path=` (which screens and art files were opened).
