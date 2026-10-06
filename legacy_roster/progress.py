"""How far along an update is, read from the messages the engine reports.

The engine tells its caller what it is doing in plain sentences; the window turns those into
a percentage. Downloading is most of the wait, so it gets most of the bar.
"""
import re

# (message pattern, where the bar stands at that message, where a counted message ends up)
STAGES = (
    (r'^Starting from', 0.02, None),
    (r'^Data pack', 0.04, None),
    (r'^NHL rosters: \w+ \((\d+)/(\d+)\)', 0.05, 0.30),
    (r'^NHL rosters: using', 0.30, None),
    (r'^Offline', 0.30, None),
    (r'^NHL: checking players .*\((\d+)/(\d+)\)', 0.30, 0.66),
    (r'^NHL: \d+ players not on the roster lists', 0.66, None),
    (r'^NHL: moving players', 0.70, None),
    (r'^Ratings', 0.75, None),
    (r'^NHL: lines', 0.79, None),
    (r'^Filling the empty national teams', 0.80, None),
    (r': building the clubs$', 0.82, None),
    (r'^National teams', 0.88, None),
    (r'^My edits', 0.90, None),
    (r'^Photos and logos: choosing', 0.91, None),
    (r'^Packing', 0.92, None),
    (r'^Checking', 0.95, None),
    (r'^(Saved as|Updated ".*" in place|Already up to date)', 1.0, None),
    (r'^The new roster did not pass', 1.0, None),
)
_STAGES = tuple((re.compile(p), a, b) for p, a, b in STAGES)
# with "Photos and logos" on, making the pictures comes after the save and takes most of the time
PHOTO_SHARE = 0.6
PHOTO_STAGES = (
    (r'^Jerseys and ice: ', 0.02, None),
    (r'^Photos and logos: reading', 0.01, None),
    (r'^Photos and logos: making', 0.03, None),
    (r'^Photos and logos: (\d+) of (\d+) pictures made', 0.03, 1.0),
    (r'^Photos and logos: (all )?\d+ pictures (are )?installed', 1.0, None),
)
_PHOTO_STAGES = tuple((re.compile(p), a, b) for p, a, b in PHOTO_STAGES)
# remarks the engine makes along the way; they say nothing about progress
REMARKS = (
    r'players skipped, no free player record left',
    r'-- cannot dress 20$',
    r'^Prospect pools: no room left',
    r"^The game's own roster: ",          # stock.py: before the steps
    r'^Retiring the old players',         # stock.retire_leftovers: before the leagues
)
_REMARKS = tuple(re.compile(p) for p in REMARKS)


def is_remark(message):
    return any(p.search(message) for p in _REMARKS)


def _stage(stages, message, previous):
    for pattern, start, end in stages:
        m = pattern.search(message)
        if not m:
            continue
        value = start
        if end is not None and int(m.group(2)):
            value = start + (end - start) * int(m.group(1)) / int(m.group(2))
        elif pattern.pattern.endswith('clubs$') and previous >= start:
            value = min(previous + 0.015, 0.87)        # one small step per further league
        return value
    return None


def fraction(message, previous=0.0, photos=False):
    """Progress (0..1) after `message`, never less than `previous`; None for a message that is
    only a remark and says nothing about progress. With `photos` the roster takes the first part
    of the bar and making the pictures the rest (PHOTO_SHARE)."""
    roster_part = 1.0 - PHOTO_SHARE if photos else 1.0
    value = _stage(_PHOTO_STAGES, message, previous) if photos else None
    if value is not None:
        return max(previous, roster_part + PHOTO_SHARE * value)
    value = _stage(_STAGES, message, previous / roster_part)
    return None if value is None else max(previous, value * roster_part)
