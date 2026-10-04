"""Starting without a community roster: the game's own roster, from the player's disc.

A player who has the game but no roster save to start from can still get an updated roster: the
disc carries the game's own database (`db/nhlng.db` in `PS3_GAME/USRDIR/cacheboot.big`, stored
uncompressed), which holds every table a roster save has, with the same record layout. Only the
wrapper differs (docs/FORMAT.md section 6, "The game's own roster"):
  * a roster save holds 39 of its 134 tables, in its own order, each with room to grow
    (`ROSTER_MAX`, the maxima the game writes);
  * every table header carries flag 6 at byte 7 (the disc has 2), and the player-link table has
    one index ('prCe', 16 bytes after its records);
  * the database ends with four 0xDB bytes, and sits in a PS3RosterFile wrapper (tdb.from_db).

from_disc() makes that save: no EA bytes are shipped, it is built on the player's PC from his own
disc. prepare() then makes the game's 2014-15 layout one the update can work on (layout.check_base
calls it the 'stock' layout):
  * the All-Star teams in slots 30 and 31 (copies of players of other teams) are emptied: Seattle
    and Vegas move in there, as in the community roster;
  * birth years move to the convention the rest of the program writes (year - 1910);
  * spare player records ("ZZ") for new players, as many as the community roster added
    (the game is known to read a roster of 6,745 players), and old free agents (30 and older)
    retire: their records become spare too. The update retires 2014's players of that age who
    lose their team as well (builder.retires).
No custom copies of NHL teams are made (owner, 2026-10-04): Utah, Seattle and Vegas show in the
NHL list with "Photos, logos and team names" on.

prepare() is a no-op on its own output: a prepared roster has no All-Star players left in 30/31.
Everything here is waiting for the owner's check in the game (pipeline.EXPERIMENTAL 'stock').
"""
import os
from collections import Counter

from . import layout as L
from . import tdb
from .art.disc import EbArchive, IsoImage

DATABASE = 'db/nhlng.db'
SAVE_SIZE = 2456120                  # every roster save the game writes is this long
# the tables of a roster save, in its order, with the room the game gives each (records)
ROSTER_MAX = {'ttOk': 252, 'caBZ': 9955, 'ulGe': 10879, 'Iwiq': 1431, 'FxFG': 1, 'OEtS': 192, 'ajmx': 7331,
              'yvSd': 7331, 'lVMf': 957, 'yuHm': 957, 'Vzjq': 180, 'cPbu': 7988, 'RBQQ': 510, 'sozv': 230,
              'DlJk': 11, 'Njxh': 424, 'ihmS': 1291, 'wgjx': 749, 'inlv': 360, 'RzQW': 424, 'FSzD': 2713,
              'byED': 1291, 'Jckz': 1879, 'QEoV': 1767, 'AJKN': 1180, 'nAUy': 876, 'LScw': 382, 'vuqu': 1684,
              'LmeT': 424, 'kTZD': 852, 'uiEj': 740, 'ySfc': 672, 'vbHh': 6000, 'oYeE': 252, 'vaHq': 1260,
              'xieT': 30, 'cTuP': 60, 'NDEo': 660, 'Roup': 20}
TABLE_FLAG = 6                       # header byte 7 of every table in a roster save
INDEXES = {'caBZ': bytes.fromhex('70724365010100000000000200000001')}   # 'prCe' on the player links
DB_TRAILER = b'\xdb' * 4
ALL_STAR = (30, 31)
# spare records added, by position (C, LW, RW, D, G): the community roster's mix of blank records,
# scaled so the roster holds no more players than the community's own (6,745, read by the game)
SPARE_RECORDS = {0: 247, 1: 210, 2: 209, 3: 336, 4: 111}
MOST_PLAYERS = 6745
# players of the game's 2014 roster this old today retire when they are off a team (and free agents
# this old retire at once): their records become spare. Younger ones become free agents; at 35 the
# free-agent list (1,767 at most) overflowed with 2014's juniors
RETIRE_AGE = 30
GAME_ID_BITS = 14


class StockError(RuntimeError):
    """The game's own roster cannot be read from this disc (the message says why)."""


def database(disc):
    """The game's own database (bytes) from a disc image or an extracted game folder."""
    try:
        source = IsoImage(disc) if os.path.isfile(disc) else disc
        return EbArchive.open(source, 'cacheboot.big').read(DATABASE)
    except (OSError, ValueError, KeyError, NotImplementedError) as err:
        raise StockError(f"the game's own roster could not be read from {disc}: {err}") from err


def save_from_database(db):
    """SYS-DATA bytes of a roster save holding the game's own roster (`db`: the disc's database)."""
    f = tdb.RosterFile.from_db(db, SAVE_SIZE - 0x2C)
    missing = [t for t in ROSTER_MAX if t not in f.tables]
    if missing:
        raise StockError(f"the game's database has no table {', '.join(missing)}")
    f.order = list(ROSTER_MAX)
    f.tables = {t: f.tables[t] for t in f.order}
    for name, room in ROSTER_MAX.items():
        t = f.tables[name]
        if t.cur_rec > room:
            raise StockError(f"table {name} holds {t.cur_rec} records, a roster save only {room}")
        t.records = t.records[:t.cur_rec * t.rec_len] + bytes((room - t.cur_rec) * t.rec_len)
        t.max_rec = room
        t.header[7] = TABLE_FLAG
        t.header[0x1D] = 1 if name in INDEXES else 0
        t.tail = INDEXES.get(name, b'')
    f.tables[f.order[-1]].tail = bytes(4)          # the closing checksum (build_db fills it in)
    f.db_trailer = DB_TRAILER
    return f.build()


def disc_icon(disc):
    """The game's icon (PS3_GAME/ICON0.PNG) from the player's disc: the icon of a roster save made for a
    version of the game that has no save to copy one from."""
    try:
        if os.path.isfile(disc):
            iso = IsoImage(disc)
            return iso.read(iso.find('/PS3_GAME/ICON0.PNG'))
        for root, _dirs, files in os.walk(disc):
            if 'ICON0.PNG' in files and os.path.basename(root).upper() == 'PS3_GAME':
                with open(os.path.join(root, 'ICON0.PNG'), 'rb') as f:
                    return f.read()
    except (OSError, ValueError, FileNotFoundError) as err:
        raise StockError(f"the game's icon could not be read from {disc}: {err}") from err
    raise StockError(f"the game's icon was not found in {disc}")


def from_disc(disc):
    """SYS-DATA bytes of the game's own roster, made from the player's disc image or game folder."""
    return save_from_database(database(disc))


# --- making the game's own roster updatable ---------------------------------------------------------
def is_stock(R):
    """The game's own layout (no community roster): the custom teams are switched off and empty."""
    U = R.U
    used = {U.get(i, 'BSXd') for i in range(U.cur_rec)}
    return not any(t in used for t in L.MIRROR_OF) and not R.T.get(222, 'NYKk')


def prepared(R):
    """Has prepare() run on this roster? Its All-Star slots hold no copies of other teams' players."""
    U = R.U
    teams = {}
    for i in range(U.cur_rec):
        teams.setdefault(R.link_to_pid.get(U.get(i, 'TWSX')), set()).add(U.get(i, 'BSXd'))
    return not any(set(ALL_STAR) & ts and ts & (L.NHL_PRIMARY - set(ALL_STAR)) for ts in teams.values())


def prepare(R, season_year):
    """Make the game's own roster (`R`, a roster.Roster) one the update can work on; see the
    module text. Returns a list of what was done (for the change log), empty when it was prepared
    already."""
    if prepared(R):
        return []
    done = []
    U, P, Q = R.U, R.P, R.Q
    # 1. the All-Star teams: their entries go (the players are on their own teams too)
    gone = [i for i in range(U.cur_rec) if U.get(i, 'BSXd') in ALL_STAR]
    for i in reversed(gone):
        U.delete_record(i)
    done.append(("All-Star teams emptied for Seattle and Vegas", f"{len(gone)} roster places"))
    # 2. birth years: the game's year - 1900 becomes year - 1910
    for i in range(P.cur_rec):
        P.set(i, 'dnFq', max(0, P.get(i, 'dnFq') - 10))
    done.append(("Birth years moved to the game's 2015 calendar", f"{P.cur_rec} players"))
    # 3. old free agents retire: off the free-agent list, their records become spare
    R.reindex()
    keep, retired = [], 0
    for k in range(Q.cur_rec):
        link = Q.get(k, 'TWSX')
        prow = R.p_by_id.get(R.link_to_pid.get(link))
        if prow is not None and P.get(prow, 'dnFq') + 1910 <= season_year - RETIRE_AGE:
            retired += 1
            for f in ('BSXd', 'GDhI', 'dhKk', 'IrlK', 'IzRv', 'WBbd'):
                P.set(prow, f, 0)
            continue
        keep.append(link)
    Q.cur_rec = 0
    for link in keep:
        Q.add_record({'TWSX': link})
    done.append(("Free agents of 2014 who retired", f"{retired} players"))
    # 4. spare records for new players
    done.append(("Spare player records added", f"{add_spares(R)} records"))
    R.reindex()
    return done


def add_spares(R):
    """Blank "ZZ" player records, each a copy of an existing player of that position (with his
    attribute and equipment rows) under a free player id. Returns how many were added."""
    P = R.P
    skaters, s_gear = R.f['yvSd'], R.f['ajmx']
    goalies, g_gear = R.f['yuHm'], R.f['lVMf']
    row_of = {t.name: {t.get(i, 'zIBw'): i for i in range(t.cur_rec)} for t in (skaters, s_gear, goalies, g_gear)}
    taken = {P.get(i, 'zIBw') for i in range(P.cur_rec)}
    free_ids = (g for g in range(1, 1 << GAME_ID_BITS) if g not in taken)
    room = min(MOST_PLAYERS - P.cur_rec, P.max_rec - P.cur_rec)
    by_pos = {}
    for i in range(P.cur_rec):
        pid = P.get(i, 'zIBw')
        pos = P.get(i, 'aljv')
        tables = (goalies, g_gear) if pos == 4 else (skaters, s_gear)
        if all(pid in row_of[t.name] for t in tables):
            by_pos.setdefault(pos, []).append(i)
    wanted = Counter()
    total = sum(SPARE_RECORDS.values())
    for pos, n in SPARE_RECORDS.items():
        wanted[pos] = n * max(0, room) // total
    added = 0
    for pos in sorted(wanted):
        models = by_pos.get(pos, [])
        attrs, gear = (goalies, g_gear) if pos == 4 else (skaters, s_gear)
        for k in range(wanted[pos]):
            if not models or attrs.cur_rec >= attrs.max_rec or gear.cur_rec >= gear.max_rec:
                break
            model = models[(k * 7919) % len(models)]       # spread over the position's players
            pid = next(free_ids)
            old = P.get(model, 'zIBw')
            i = P.add_record(template=model)
            P.set(i, 'zIBw', pid)
            P.set(i, 'RMbQ', 'ZZ')
            for f in ('BSXd', 'GDhI', 'dhKk', 'IrlK', 'IzRv', 'WBbd', 'LcvS', 'rnOl', 'Nzao'):
                P.set(i, f, 0)
            for t in (attrs, gear):
                j = t.add_record(template=row_of[t.name][old])
                t.set(j, 'zIBw', pid)
            added += 1
    return added


def retire_leftovers(b, leagues):
    """Before the club leagues are rebuilt (the game's own roster only): players of 2014 on the
    clubs about to be rebuilt whom no league and NHL.com list any more, and who are RETIRE_AGE or
    older, leave now and retire, so their records are spare for the leagues' new players. (Retired
    later, at the end of a league, they would only be used by the next update, which would then
    differ from the first.) Everyone the leagues list is reserved: his record is never reused.
    `leagues`: {step: league} as the leagues will be built. Returns how many retired."""
    from .leagues import clubs
    from .matching import match_club
    R, U = b.R, b.U
    people = [p for league in leagues.values() for p in clubs.listed(league['teams'])]
    b.donors.reserve(people)
    match_club(R, people)
    listed = {p['row'] for p in people if p['row'] is not None} | set(b.api_rows)
    slots = {t['slot'] for league in leagues.values() for t in league['teams']}
    leaving = {}
    for e in range(U.cur_rec):
        if e in b.deleted or U.get(e, 'BSXd') not in slots:
            continue
        prow = b.prow_of_entry(e)
        if prow is None or prow in listed:
            continue
        leaving.setdefault(b.P.get(prow, 'zIBw'), []).append(e)
    # a club its feed leaves short at a position keeps its best former players there (as the league
    # step would: clubs._fill_lineup), so they are not retired
    have = Counter((p['slot'], clubs.group(p['pos'])) for p in people if p['row'] not in b.api_rows)
    needed = set()
    for pid, ents in sorted(leaving.items(), key=lambda kv: (-b.quality.get(kv[0], 0), kv[0])):
        for e in ents:
            g = (U.get(e, 'BSXd'), clubs.group('CLRDG'[b.P.get(R.p_by_id[pid], 'aljv')]))
            if have[g] < clubs.CORE[g[1]]:
                have[g] += 1
                needed.add(pid)
    retired = 0
    from .donors import real_birth_year
    for pid, ents in sorted(leaving.items()):
        prow = R.p_by_id[pid]
        if pid in needed or real_birth_year(b.P, prow) > b.data.season_year - RETIRE_AGE:
            continue
        others = [x for x in R.entries_by_pid.get(pid, []) if x not in b.deleted and x not in ents]
        if others:                       # still on another team (a national team): he stays
            continue
        name = R.name(prow)
        for e in ents:
            b.log.append([R.T.get(U.get(e, 'BSXd'), 'nnsx'), 'left the club', name, 'retired', U.get(e, 'tRVs')])
            b.depart(e)
            b.deleted.add(e)
        if b.retires(pid):
            retired += 1
    return retired
