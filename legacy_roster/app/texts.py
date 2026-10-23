"""What the window says to players, and the small helpers that word it."""
import datetime

from .. import savedata

SITE = "https://www.puckpeak.com"
SITE_LABEL = "www.puckpeak.com"
DISCORD = "https://gg.puckpeak.com"        # the Puck Peak Discord (a redirect)
TAGLINE = "NHL & hockey analytics like never before"
HOW_TO_LOAD = "In the game: Customize > Save/Load/Delete > Load > Rosters, pick it, then save the roster once so it stays active."
HOW_TO_LOAD_IN_PLACE = ("In the game: start it. If this is not the roster in use, Customize > Save/Load/Delete > Load > Rosters, pick it, "
                        "then save the roster once.")
HOW_TO_USE_EXPORT = ("Copy SYS-DATA into one of your roster save folders in place of the file with that name (keep a copy of "
                     "the old one), then in the game: Customize > Save/Load/Delete > Load > Rosters, pick it, and save the roster once.")
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
ROOM_NOTE = "The game shows at most 10 rosters per version. Keep 10 or fewer."
ROOM_FULL_SHORT = "Full: the game shows only 10. Delete a roster you no longer play, or pick \"Update this roster\"."
ROOM_FULL = savedata.FULL_TEXT
HIDDEN_IN_GAME = ("The game does not show this roster: it lists only 10. Delete a roster you no longer play, "
                  "and this one shows again.")
PHOTOS_HINT ="RPCS3 must be closed. The game's own pictures are kept and can be put back."
PHOTOS_TITLE = "Photos, logos and team names"
PHOTOS_SIZE = 160 * 1000 * 1000        # what the row says before the program knows the real size
PHOTOS_RUNNING = "Downloading automatically... {pct} %"
PHOTOS_READY = "Downloaded automatically. Ready."
PHOTOS_RETRY = "Not downloaded yet. It tries again automatically."
PHOTOS_OFF = "Off: nothing is downloaded."
PHOTOS_NEEDS_RPCS3 = "Needs RPCS3: pick rpcs3.exe in step 1."
PHOTOS_EXPORT = "Not in this mode: pictures need RPCS3."
PHOTOS_WAITING = "Waiting for the download... {pct} %"
PHOTOS_SHORT = "Some pictures could not be downloaded; the next update tries again."
LOOKS_MISSING = "This season's jerseys come with Photos, logos and team names (Update tab)."
EDITS_HINT = "Kept on this PC, so the next download does not undo them."
PATCH_TITLE = "32 teams and the year 2026 (game patch)"
PATCH_SUB = "Seattle and Vegas in Season and Be a GM: 32 NHL and 32 AHL teams, 84 games. New."
NOT_PATCHED = "Not patched: updates make rosters for the game as it is."
PATCHED_NOTE = "every update makes a roster for it"
PATCH_NEEDS_RPCS3 = "The game patch needs RPCS3: pick rpcs3.exe in step 1."
PATCH_NEEDS_GAME = "RPCS3 does not list the game yet: start it once from RPCS3's game list."
PATCH_ASK = ["This patches the game in RPCS3 (every version you have) for 32 teams and the year 2026.",
             "While it is patched, every update makes a roster for the patched game. The patched game shows other "
             "rosters as damaged: update one of them first.",
             "Season and Be a GM saves you start with the patch need it to go on.",
             "Unpatch (in step 2) puts the game back as it was. RPCS3 must be closed for both."]
UNPATCH_ASK = ["This takes the game patch out of RPCS3: the game is as it was.",
               "Rosters made for the patch, and Season and Be a GM saves started with it, do not open without it. "
               "Update a roster made for the patch, and it is made for the game as it is again. "
               "Your rosters and saves are not changed now. RPCS3 must be closed."]
MISFIT_PATCHED = "The patched game cannot load this roster (it says \"damaged\"). Update it to make it a 32-team roster."
MISFIT_UNPATCHED = "Made for the game patch: the game without it cannot load this roster. Update it to turn it back."
MISFIT_VERSION = ("Made for another version of the game patch: the patched game cannot load this roster (it says "
                  "\"damaged\"). Update it to make it fit.")
MISFIT_STALE = ("Your game has update 1.01, and the game patch in RPCS3 is from before this program knew it. Press "
                "Patch again in Game patch.")
FIT_NO_STEP = "Switch on at least one thing to update, then press Update roster."
UNPATCHED = "Done: the game patch is out. Rosters marked \"32 teams\" do not open now: update one, and it is made for the game as it is."
NO_LOGIN_TIP = "No sign-in boxes when the game starts. Online modes still sign in when you open them."
PATCH_INFO_TITLE = "What the game patch does"
PATCH_INFO = [
    ("In the game", [
        "The year is 2026: the calendar, the seasons and the dates start in 2026-27, not 2015.",
        "Season, Be a GM and Be a Pro have all 32 NHL teams: Seattle and Vegas can be picked, played and simulated. "
        "Utah plays in the Central, Seattle and Vegas in the Pacific.",
        "The real 2026-27 calendar: 84 games per team. The seasons after it get a 32-team calendar too.",
        "The farm league has 32 AHL clubs in their 2026-27 divisions, with Coachella Valley (Seattle) and Henderson "
        "(Vegas). Call-ups and send-downs work for every team. Both clubs are also in Play Now's AHL list (their names "
        "come with Photos, logos and team names).",
        "The playoffs, the trade deadline, the off-season, the All-Star game and the draft with the lottery work "
        "with 32 teams (7 rounds, 224 picks a year).",
        "Salary cap in real money: $104.0M in 2026-27 (floor $76.9M), $113.5M in 2027-28, $127.5M in 2028-29, "
        "then held. Contracts show the seasons as 26-27, 27-28 ...",
        "The computer runs Seattle and Vegas like every other team (call-ups, line-ups, re-signing), so a Season or "
        "Be a GM plays on season after season.",
        "The news panel of the main menu shows Puck Peak's news, also when you play online (they come with Photos, "
        "logos and team names).",
    ]),
    ("The two switches", [
        "Skip the intro: the game goes straight to the main menu. No language pick, intro videos, legal screen, "
        "autosave notice or Press Start. Autosave stays on.",
        "No pop ups at start: no online sign-in boxes when the game starts. Online modes still sign in when you "
        "open them.",
    ]),
    ("What it changes on your PC", [
        "A patch file in RPCS3's patches folder, and the patch's ticks in RPCS3's patch settings. RPCS3 applies it each "
        "time the game starts. The game's own files and your disc are never changed.",
        "Two small database files in the game's folder in RPCS3, made from your own game disc.",
        "Every version of the game you have (EU and NA). A file that was there before is kept and put back by Unpatch.",
        "Your rosters and saves are not changed when you patch.",
    ]),
    ("Rosters and saves", [
        "While the game is patched, every update makes a roster for it (marked \"32 teams\"). The patched game shows "
        "other rosters as damaged: update one of them first.",
        "Start a new Season, Be a GM or Be a Pro after patching. Saves started with the patch need it to go on.",
        "Online play still works.",
    ]),
    ("Unpatch", [
        "Unpatch takes it all out: the game is as it was. Rosters marked \"32 teams\" and saves started with the patch "
        "do not open without it. Update such a roster, and it is made for the game as it is again.",
        "RPCS3 must be closed to patch or unpatch.",
    ]),
]


def patched_status(where):
    return f"Done: the {where} game is patched. Now update a roster (Update tab) and start a new Season or Be a GM."


def fit_ask(name, why):
    """The question after Patch / Unpatch when the roster picked no longer fits the game (`why`: a MISFIT_ text)."""
    if why == MISFIT_VERSION:
        return [f"\"{name}\" was made for another version of the game patch. The patched game cannot load it and says "
                "it is damaged.", "Update it now and it fits the patch you have. A backup is made first."]
    if why == MISFIT_PATCHED:
        return [f"\"{name}\" was made for the game without the patch. The patched game cannot load it and says it is "
                "damaged.", "Update it now and it becomes a 32-team roster for the patched game. A backup is made first."]
    return [f"\"{name}\" was made for the patched game. The game without the patch cannot load it.",
            "Update it now and it is made for the game as it is again. A backup is made first."]


def patch_state(state, old=(), missing=()):
    """'Patched: EU and NA (intro skipped)' from patchinstall.state, or None when nothing is patched. `old`: patched
    versions with an older patch; `missing`: versions RPCS3 has that are not patched."""
    on = [t for t, st in state.items() if st.get('patched') or st.get('stale')]
    if not on:
        return None
    from .. import savedata
    extra = [what for what, key in (("intro skipped", 'intro'), ("no pop-ups at start", 'login'))
             if any(state[t].get(key) for t in on)]
    text = f"Patched: {' and '.join(savedata.region(t) for t in on)}" + (f" ({', '.join(extra)})" if extra else "")
    if not old and not missing:
        return f"{text}: {PATCHED_NOTE}."
    if old:
        text += ". A newer patch is in this program: press Patch again."
    elif missing:
        text += f". Your {' and '.join(savedata.region(t) for t in missing)} game is not patched."
    return text


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


def photos_will(size=None):
    """The Photos row before its pictures are on this PC: 'Downloaded automatically (about 160 MB)'."""
    mb = max(10, round((size or PHOTOS_SIZE) / 1e7) * 10)
    return f"Downloaded automatically (about {mb} MB)"
