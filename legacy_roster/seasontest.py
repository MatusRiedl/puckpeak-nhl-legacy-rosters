"""The Season mode test (cli `season-test`): a ladder of LAB rosters, each with a few more update
steps than the one before, so the owner can find in the game which step makes Season mode crash.

Owner, 2026-10-06: the community roster and the game's own roster play Season mode; every roster
this program makes crashes it ("Loading Season Mode", game code at 0x00381c24: a player lookup that
finds nobody while the free agents are counted). The game builds its own league tables from the
roster when Season starts (the disc's league tables are empty; their sizes are in nhlng-meta.xml:
5,120 roster entries, 6,000 players, 1,200 goalies), so `counts()` measures what our rosters put into
them, and `limits()` names the sizes a roster passes. Nothing here writes a game file: the rosters go
into the save folder as new LAB saves, like `stock-test` does.
"""
import os

from . import datasource, layout as L, pipeline, savedata
from .builder import LINK_LIMIT, Builder, Data
from .roster import Roster
from .verify import verify

# what Season mode's league tables hold (the disc's nhlng-meta.xml): roster entries, players, goalies
MAX_ENTRIES, MAX_PLAYERS, MAX_GOALIES = 5120, 6000, 1200
EUROPE = ('liiga', 'extraliga', 'shl', 'del', 'nl', 'norway')


def rungs(available):
    """[(roster name, [steps])]: the ladder, each rung adding to the one before. Steps the data pack
    does not have are left out."""
    ladder = [("SEASON 1 core", list(pipeline.CORE_STEPS)),
              ("SEASON 2 europe", list(pipeline.CORE_STEPS) + list(EUROPE)),
              ("SEASON 3 ahl", list(pipeline.CORE_STEPS) + list(EUROPE) + ['ahl']),
              ("SEASON 4 everything", list(pipeline.CORE_STEPS) + list(EUROPE) + ['ahl', 'chl'])]
    return [(name, [s for s in steps if s in available]) for name, steps in ladder]


def trim(data, season_year, remove, activate=False):
    """`data` (SYS-DATA bytes) with `remove` of the weakest players of junior clubs (the CHL) taken
    off their teams: for the test only, to find which of Season's table sizes matters. They keep
    their records (no one else is given them) but are on no roster and on no free-agent list, so
    Season does not load them. With `activate` every player on a roster who is marked inactive
    (`active` 0: copies of the game's placeholder players, made by the game's own roster path) is
    switched on. Returns (new bytes, how many were taken)."""
    R = Roster(data)
    b = Builder(R, Data(season_year=season_year), layout=L.check_base(R))
    live = b.live_entries()
    weakest = sorted((b.q(e), e) for e in range(R.U.cur_rec)
                     if R.U.get(e, 'BSXd') in L.CHL and len(live.get(b.pid_of_entry(e), [])) == 1)
    taken = 0
    for _, e in weakest[:max(0, remove)]:
        b.depart(e)
        b.deleted.add(e)
        taken += 1
    if activate:
        for pid, entries in live.items():
            prow = R.p_by_id.get(pid)
            if prow is not None and any(e not in b.deleted for e in entries) and R.P.get(prow, 'NYKk') == 0:
                R.P.set(prow, 'NYKk', 1)
    b.contracts()
    b.finish()
    return R.f.build(), taken


def without_free_agent(data, season_year, first, last):
    """`data` with one free agent taken off the free-agent list (his record and link stay): to see
    whether the game's crash is about that one player (Season mode crashed on Jonathan Drouin's link
    in every roster our update made). Returns (new bytes, whether he was on the list)."""
    R = Roster(data)
    b = Builder(R, Data(season_year=season_year), layout=L.check_base(R))
    rows = R.find_player(first, last)
    pids = {R.P.get(r, 'zIBw') for r in rows}
    listed = any(R.link_to_pid.get(link) in pids for link in b.fa_links)
    for pid in pids:
        b.drop_fa(pid)
    b.finish()
    return R.f.build(), listed


def relinked(data, season_year):
    """`data` with every free agent on a new link number (the old link rows are removed): to see
    whether the crash is about the link a free agent has (Drouin's, 4504) or about the player."""
    R = Roster(data)
    b = Builder(R, Data(season_year=season_year), layout=L.check_base(R))
    n = b.relink_free_agents()
    b.finish()
    return R.f.build(), n


def counts(data):
    """What a roster (SYS-DATA bytes) puts into Season mode's league tables, as {name: number}."""
    R = Roster(data)
    P, U, C, Q = R.P, R.U, R.C, R.Q
    on_team, loaded, goalies = [], set(), set()
    for e in range(U.cur_rec):
        pid = R.link_to_pid.get(U.get(e, 'TWSX'))
        loaded.add(pid)
        if U.get(e, 'BSXd') not in L.NATIONAL:
            on_team.append(e)
    free = {R.link_to_pid.get(Q.get(i, 'TWSX')) for i in range(Q.cur_rec)}
    loaded |= free
    inactive = sum(1 for pid in loaded if pid in R.p_by_id and P.get(R.p_by_id[pid], 'NYKk') == 0)
    return {'players': P.cur_rec, 'players loaded': len(loaded), 'entries': U.cur_rec,
            'entries on clubs': len(on_team), 'links': sum(1 for i in range(C.cur_rec) if C.get(i, 'qEfv') < LINK_LIMIT),
            'free agents': Q.cur_rec, 'inactive players loaded': inactive}


def limits(c):
    """The sizes of Season mode's tables a roster with counts `c` passes (words, for the report)."""
    over = []
    if c['entries on clubs'] > MAX_ENTRIES:
        over.append(f"entries on clubs {c['entries on clubs']} > {MAX_ENTRIES}")
    if c['players loaded'] > MAX_PLAYERS:
        over.append(f"players on a roster or the free-agent list {c['players loaded']} > {MAX_PLAYERS}")
    if c['links'] > MAX_PLAYERS:
        over.append(f"links {c['links']} > {MAX_PLAYERS}")
    return over


def _line(name, c, problems=()):
    text = (f"{name}: {c['players loaded']} players on a roster or the free-agent list, {c['entries on clubs']} entries "
            f"on clubs ({c['entries']} with the national teams), {c['links']} links, {c['free agents']} free agents, "
            f"{c['players']} player records, {c['inactive players loaded']} inactive")
    over = limits(c)
    text += " | over Season's table sizes: " + ("; ".join(over) if over else "none")
    if problems:
        text += " | checks: " + "; ".join(problems[:2])
    return text


def pick_source(slots, source=None):
    """The roster to start from: the one asked for, else the newest that was not made by this
    program (the community roster), else the newest."""
    if source:
        return next((s for s in slots if source in (s.folder, s.name)), None)
    mine = lambda s: s.tool_made or s.name.startswith(('SEASON', 'LAB'))      # our own output is no clean start
    return next((s for s in slots if not mine(s)), slots[0] if slots else None)


def file_slot(model, path):
    """A starting point that is a plain roster file (a downloaded community SYS-DATA): a copy of the roster
    save `model` (its icon and PARAM.SFO make the new saves) whose roster is the file."""
    import copy
    slot = copy.copy(model)
    slot.__class__ = type('FileSlot', (type(model),), {'tool_made': False})     # a file we did not make
    slot.sys_data, slot.name = path, "the roster file " + os.path.basename(path)
    return slot


def season_test(folder, slot, say=print):
    """Save the ladder next to `slot` (a roster save or the game's own roster, savedata.DiscSlot) in
    the save folder `folder`; write season_test.txt into the program's reports folder. Returns the
    list of the new saves. With the game's own roster only the last rung is made."""
    raw = savedata.read_roster(slot)
    L.check_base(Roster(raw))
    if getattr(slot, 'tool_made', False):
        say(f"Note: \"{slot.name}\" was made by this program. For a clean test start from the community roster "
            "as downloaded: --source file:<path to its SYS-DATA>.")
    pack = datasource.load_pack(offline=True)
    ladder = rungs(pipeline.steps_for(pack))
    if getattr(slot, 'disc', False):
        ladder = ladder[-1:]
    season = pack.get('season', 2026)
    lines = [f"Season mode test, from \"{slot.name}\" ({slot.folder}).",
             "Load each SEASON roster in the game (Roster Management > Load Roster), start Season mode, pick a team "
             "and wait for it to load. Test them in number order and note the first one that crashes; 1b and 1c "
             "only if 1 crashes (1b is 1 without Jonathan Drouin on the free-agent list, 1c is 1 with every free "
             "agent on a new link number); 5 and 6 only if 4 crashes. 5 and 6 are 4 with junior players taken off: 5 below the player and link sizes; 6 "
             "below the roster-entry size as well (community roster), or the same as 5 with the inactive players "
             "switched on (the game's own roster).", "",
             _line("Start", counts(raw))]
    saved, full = [], None
    for name, steps in ladder:
        say(f"{name}: building ({', '.join(steps)})")
        data = datasource.gather(Roster(raw), set(steps), pack, say, offline=True)
        result = pipeline.build(raw, data, steps)
        new = savedata.install(folder, slot, result.data, name)
        saved.append(new)
        lines.append(_line(f"{new.name} ({new.folder})", counts(result.data), result.problems))
        full = result.data
        if name == "SEASON 1 core":      # variants of it, to tell what the crash is about (owner, 2026-10-06)
            data1b, listed = without_free_agent(result.data, season, 'Jonathan', 'Drouin')
            if listed:
                new = savedata.install(folder, slot, data1b, "SEASON 1b core no Drouin")
                saved.append(new)
                lines.append(_line(f"{new.name} ({new.folder}, Jonathan Drouin off the free-agent list)",
                                   counts(data1b), verify(data1b, Roster(raw))[0]))
            data1c, n = relinked(result.data, season)
            new = savedata.install(folder, slot, data1c, "SEASON 1c core new links")
            saved.append(new)
            lines.append(_line(f"{new.name} ({new.folder}, the {n} free agents on new link numbers)", counts(data1c),
                               verify(data1c, Roster(raw))[0]))
    # the full roster again with junior players taken off, to tell which size is the one that matters:
    # first below the player and link sizes only, then (community roster) below the roster-entry size
    # too, or (the game's own roster, which has inactive players) the same with them switched on
    if full is not None and len(ladder[-1][1]) > len(pipeline.CORE_STEPS):
        c = counts(full)
        disc = getattr(slot, 'disc', False)
        fewer = max(c['players loaded'] - MAX_PLAYERS, c['links'] - MAX_PLAYERS) + 10
        specs = [("SEASON 5 trimmed players", fewer, False),
                 ("SEASON 6 trimmed, players active", fewer, True) if disc else
                 ("SEASON 6 trimmed entries", c['entries on clubs'] - MAX_ENTRIES + 10, False)]
        for name, remove, activate in specs:
            if remove <= 10:
                continue
            say(f"{name}: building")
            data, taken = trim(full, season, remove, activate)
            problems, _ = verify(data, Roster(full))
            new = savedata.install(folder, slot, data, name)
            saved.append(new)
            lines.append(_line(f"{new.name} ({new.folder}, {taken} junior players off their teams)", counts(data), problems))
    with open(datasource.app_dir('reports', 'season_test.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    for line in lines:
        say(line)
    return saved
