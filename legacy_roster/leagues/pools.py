"""Prospect pools displaced by real clubs.

The community roster keeps draft classes and NHL prospect pools in European club slots. When a
league gets its real clubs back, a pool player who is not on one of those clubs moves to a spare
custom team slot (236-251) that takes over the pool's name. No team is added and no slot
changes league: the custom slots already exist, switched off.

The spare slots hold 16 x 40 players. While the leagues are built a pool slot may hold more
(later leagues -- AHL, CHL -- take their players out of the pools again); settle() then keeps
the best prospects, 40 a slot, and makes the others free agents: they stay in the game (with the
NHL rights they had) and can be signed.
"""
import re

from .. import layout as L
from .. import lines

POOL_NAME = re.compile(r'Prospects|System|USNTDP')
SPARE_SLOTS = L.SPARE


def is_pool(R, team):
    """A prospect pool of the community roster: in a European club slot or a spare custom slot,
    named like one (the event teams "Top Prospects Red/White" are not pools)."""
    return (team in L.EUROPE or team in SPARE_SLOTS) and bool(POOL_NAME.search(R.T.get(team, 'JkmY')))


def relocate(b, groups):
    """Move displaced pool entries to spare custom slots: the slot that already carries the
    pool's name, else a slot still switched off, else the pool slot with the fewest players.

    `groups`: {(pool name, pool abbreviation): [roster entries]}. Returns the slots used."""
    T = b.R.T
    used = set()
    for (name, abbr), ents in groups.items():
        target = next((t for t in SPARE_SLOTS if T.get(t, 'NYKk') and T.get(t, 'JkmY') == name), None)
        if target is None:
            target = next((t for t in SPARE_SLOTS if not T.get(t, 'NYKk') and not b.entries_on(t)), None)
            if target is not None:
                T.set(target, 'NYKk', 1)         # active
                T.set(target, 'JkmY', name)      # fullname
                T.set(target, 'ITNQ', name)      # shortname
                T.set(target, 'nnsx', abbr)      # abbrname
                T.set(target, 'RPbr', abbr)      # artabbr, as the base's own custom teams have it
                b.log.append([abbr, 'prospect pool moved', name, f"now custom team {target}", ''])
        if target is None:                       # every spare slot is taken: share another pool's
            target = min((t for t in SPARE_SLOTS if T.get(t, 'NYKk') and is_pool(b.R, t)),
                         key=lambda t: (len(b.entries_on(t)), t))
            b.log.append([abbr, 'prospect pool merged', name, f"into {T.get(target, 'JkmY')} (custom team {target})", ''])
        for e in sorted(ents, key=lambda e: (-b.q(e), e)):
            b.move_entry(e, target)
        used.add(target)
    return used


def settle(b, say):
    """After every league: at most 40 players per pool slot. Players over the limit move to a
    pool slot with room, best first; whoever finds none becomes a free agent. Then numbers,
    lines and letters for every pool slot that changed. Returns how many became free agents."""
    T, U = b.R.T, b.U
    slots = [t for t in SPARE_SLOTS if T.get(t, 'NYKk') and is_pool(b.R, t)]
    extra = []
    for t in slots:
        ents = sorted(b.entries_on(t), key=lambda e: (-b.q(e), e))
        extra += ents[L.MAX_PER_TEAM:]
    live = b.live_entries() if extra else {}
    released = 0
    for e in sorted(extra, key=lambda e: (-b.q(e), e)):
        room = [t for t in slots if len(b.entries_on(t)) < L.MAX_PER_TEAM]
        if room:
            target = min(room, key=lambda t: (len(b.entries_on(t)), t))
            b.log.append([T.get(target, 'nnsx'), 'prospect pool: moved for room', b.R.name(b.prow_of_entry(e)),
                          f"from {T.get(U.get(e, 'BSXd'), 'JkmY')} to {T.get(target, 'JkmY')}", ''])
            b.move_entry(e, target)
            continue
        name, pool = b.R.name(b.prow_of_entry(e)), T.get(U.get(e, 'BSXd'), 'nnsx')
        became_fa = b.release(e, live)
        b.log.append([pool, 'prospect pool: no room', name, 'now a free agent' if became_fa else 'left the pool', ''])
        released += 1
    if released:
        say(f"Prospect pools: no room left for {released} players; they are free agents now")
    for t in slots:
        if t not in b.arrivals and t not in b.departures:
            continue
        taken = set()
        for e in sorted(b.entries_on(t), key=lambda e: (-b.q(e), e)):       # one number each
            n = U.get(e, 'tRVs')
            if not n or n in taken:
                n = next(x for x in range(2, 99) if x not in taken)
                U.set(e, 'tRVs', n)
            taken.add(n)
        for e in b.entries_on(t):
            b.clear_lines(e)
        try:
            lines.build_lines(b, t)
            b.set_letters(t)
        except lines.NotEnoughPlayers:
            pass                                     # a pool that cannot dress 20 keeps no lines, as in the base
    return released
