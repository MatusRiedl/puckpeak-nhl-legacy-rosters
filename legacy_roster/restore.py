"""Putting the game's own things back: its rosters, its calendar, its pictures.

The game's own roster ("the default") is the roster on the player's disc, else the game's own roster save
(`...0200`, which this program never writes) while it still has the game's own layout. It is only ever
read: nothing here writes into it."""
from . import layout as L
from . import savedata
from .roster import Roster

ROSTERS, CALENDAR, PICTURES = 'rosters', 'calendar', 'pictures'
ALL_PARTS = (ROSTERS, CALENDAR, PICTURES)


class _Raw:
    """Stands in for the builder when the game's own roster is written as it is (nothing was built)."""
    league_stats = {}
    R = None


def default_slot(rpcs3, title_id):
    """The slot that holds the game's own roster for `title_id`: the roster on the player's game disc (always
    EA's own data), else the game's own save `...0200` while it has the game's own layout.
    (A roster this program made from the game's own roster has the same layout; taking it would "restore" a
    roster to itself.)"""
    disc = next((d for d in rpcs3.disc_slots() if d.title_id == title_id), None)
    if disc is not None:
        return disc
    try:
        slots = savedata.list_rosters(rpcs3.savedata)
    except OSError:
        return None
    for slot in sorted((s for s in slots if s.title_id == title_id and s.number == 0 and not s.tool_made), key=lambda s: s.number):
        try:
            if L.check_base(Roster(savedata.read_roster(slot))) == L.STOCK:
                return slot
        except Exception:               # a roster this program cannot read is not a default
            continue
    return None


def describe(slot):
    """Where the defaults come from, in the player's words."""
    if slot is None:
        return "The game's own roster was not found (no game disc and no clean roster save)."
    if getattr(slot, 'disc', False):
        return f"The game's own roster from your {slot.region} game disc."
    return f"The game's own roster in {slot.folder}."


def copy_calendar(R, default_R):
    """The schedule tables of `R` become the game's own (`default_R`): rows and count."""
    from . import schedule
    for tag in (schedule.TABLE, schedule.FAVOURITE):
        T, D = R.f[tag], default_R.f[tag]
        for i in range(T.cur_rec):
            for field in schedule.ROW.values():
                T.set(i, field, 0)
        T.cur_rec = 0
        for i in range(D.cur_rec):
            T.add_record({field: D.get(i, field) for field in schedule.ROW.values()})
