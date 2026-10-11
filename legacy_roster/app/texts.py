"""What the window says to players, and the small helpers that word it."""
import datetime

from .. import savedata

SITE = "https://www.puckpeak.com"
SITE_LABEL = "www.puckpeak.com"
TAGLINE = "NHL & hockey analytics like never before"
HOW_TO_LOAD = "In the game: Roster Management > Load Roster, pick it, then save the roster once so it stays active."
HOW_TO_LOAD_IN_PLACE = ("In the game: start it. If this is not the roster in use, Roster Management > Load Roster, pick it, "
                        "then save the roster once.")
HOW_TO_USE_EXPORT = ("Copy SYS-DATA into one of your roster save folders in place of the file with that name (keep a copy of "
                     "the old one), then in the game: Roster Management > Load Roster, pick it, and save the roster once.")
NO_NAME = "(a roster file has no name)"
BIN_NAME = "Recycle Bin" if savedata.WINDOWS else "Trash"
DISC_NOTE = "From your game disc: the 2014-15 players, brought up to today"
SAVE_NOTE = ("Updating this roster makes a backup first. Saving as a new roster leaves existing saves untouched. "
             "RPCS3 must be closed for in-place updates.")
EXPORT_SAVE_NOTE = ("The new SYS-DATA is written into a new folder next to this program, named by the date and time. "
                    "It has no name of its own and no pictures.")
EXPORT_PICK = ("Pick the roster's SYS-DATA file (the community roster you downloaded). The new SYS-DATA is written next "
               "to this program.")
EXPORT_RPCS3 = "Not needed in this mode: the program only makes a roster file."
PHOTOS_HINT = "RPCS3 must be closed. The game's own pictures are kept and can be put back."
EDITS_HINT = "Kept on this PC, so the next download does not undo them."
SCHEDULE_NOTE = "The real games and dates for Season mode (30 teams; the game still calls the year 2015)"
NHL_NOTE = "Today's rosters from NHL.com"
MISSING_FILES = ("Some of this program's files are missing from the system's temporary folder. An antivirus "
                 "or a cleaning program may have removed them.\n\n"
                 "Close this message and start the program again. If it keeps happening, "
                 "allow NHLLegacyRosterUpdater in your antivirus.")


def friendly_date(when, now=None):
    now = now or datetime.datetime.now()
    days = (now.date() - when.date()).days
    if days == 0:
        return f"today {when:%H:%M}"
    if days == 1:
        return f"yesterday {when:%H:%M}"
    return f"{when.day} {when:%b %Y}"


def short_reason(problem):
    if 'custom copies' in problem:
        return "Cannot be used: its teams are laid out differently from the community roster."
    return "Cannot be used: " + problem.split('. ')[0].rstrip('.') + "."


def dated(source):
    return f"{source['label']}, data from {source['date']}" if source else "No data available"


def rpcs3_note(rpcs3, slots):
    """What step 1 says under the path once RPCS3 is found: only what the player needs to act on.
    (The count of rosters found is gone: the list shows them.) None when there is nothing to say."""
    saves = [s for s in slots if not getattr(s, 'disc', False)]
    if rpcs3 is not None and rpcs3.plain:
        n = len(saves)
        return (f"Found {n} roster{'s' if n != 1 else ''} of NHL Legacy in this folder. Without RPCS3 the new roster "
                "is saved next to them; photos and the game's own roster need RPCS3.")
    if not saves and not slots:
        return ("No roster is saved in RPCS3 yet, and RPCS3 does not say where your game is. Pick the game "
                "(its .iso file or its folder): the program then starts from the game's own roster, made from "
                "your game disc and brought up to today.")
    if not saves:
        return ("No roster is saved in RPCS3 yet. Start from the game's own roster (listed below): it is "
                "made from your game disc and brought up to today.")
    return None
