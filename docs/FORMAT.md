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

**Teams** (`ttOk.league`): 0 NHL, 1 AHL, 2 SHL, 3 Liiga, 4 DEL, 5 Extraliga, 6 National League,
7 Norway, 8 national teams, 9 OHL, 10 QMJHL, 11 WHL, 12 Top Prospects, 13 custom, 14 Winter
Classic, 15 EASHL.

**Players.** `position` 0 C, 1 LW, 2 RW, 3 D, 4 G. `handedness` 0 left. `height` inches - 54,
`weight` pounds - 120. `intlcountry` is a country code; `state` is a province/state code for
North Americans and the country code for everyone else. `headid` is the 3D head model (60000
and up are generic heads), `artid` + `hasportrait` the menu photo, `audioid` the commentary
name. `team` is the contract team + 1 (0 = none), `contractlength`, `contractdollars`.
`proteam` and `draftteam` are NHL team + 1 in five bits. `draftyear` is the year - 1900, 255
for undrafted.

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

## 6. The 2025-26 community roster

The updater works on this roster family; its conventions differ from the stock EA roster.

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

**Table capacities** (current / maximum records in a roster save):

| Table | Current | Max | Notes |
|---|---|---|---|
| `cPbu` players | 6,745 | 7,988 | could grow; untested in the game |
| `yvSd` / `yuHm` skater / goalie attributes | 6,056 / 689 | 7,331 / 957 | one row per player, by `game_id` |
| `ulGe` roster entries | 3,600 | 10,879 | |
| `caBZ` links | 3,611 | 9,955 | |
| `QEoV` free agents | 17 | 1,767 | |
| `ttOk` teams | 252 | 252 | full |
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
  - Logos are drawn over the whole canvas with transparency. `t` has a white edge and a soft
    shadow; `d` is a small `t`; `c` is the logo enlarged and cut off on the right; `w` is a big
    zoomed piece faded to a circle; `s` is a banner in the team's colours with part of the logo.
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
  game still showed "Chomutov". Custom teams show their `shortname` as a key into a city list
  (`LAS_VEGAS` shows "Las Vegas"). The game looks for `fe/loc/nhl_eng_us.db` on `dev_hdd0` before
  the disc's (RPCS3 log), so names can be fixed there: a later step.
- **Code.** Reading and writing: `legacy_roster/art/` (`disc.py` reads the player's own disc image or
  folder, `bigf.py`, `refpack.py`, `dds.py`). Photos and logos: `portraits.py` (ids in the roster),
  `images.py` (Pillow: cut-out, head finding, logo styles), `install.py` (download, write, back up,
  remove). The one-off in-game experiment is `lab.py` (`cli art-test`).

## 8. Schedules

Each league has a schedule table in the roster save except Norway:
`nhlschedule`, `nhlfutureschedule`, `favoriteteamschedule`, `ahlschedule`, `ohl…`, `qmjhl…`,
`whl…`, `swedish…`, `finnish…`, `german…`, `czech…`, `swissschedule`.

- **Fields.** Every record has `round` (3 bits), `status` (2), `day` (5, 0-based), `month` (4, 0-based:
  9 = October), `index` (= row number) and `home` / `away` team ids. The team ids are 5 bits in the NHL
  and AHL tables and 4 bits in the European ones. There is **no year**.
- **What the NHL table holds.** `nhlschedule` is the 2015-16 NHL calendar (7 Oct to 9 Apr, with a 29 Feb).
  Only slots 0–29 play, 82 games each (41 home). Slots 30/31 meet once (the All-Star game).
  `nhlfutureschedule` is a second 82-game calendar.
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
