"""The window's remembered choices (settings.json in the program's own folder)."""
import json

from .. import datasource

FILE = 'settings.json'
PHOTOS = 'photos'           # the "Photos and logos" switch in settings['steps'] (before 0.76.0 also names and jerseys)
NAMES, LOOKS, ARENAS, BRIGHT_ICE, TEAM_MASKS = 'names', 'looks', 'arenas', 'bright_ice', 'team_masks'    # 0.76.0: switches of their own
PICTURE_KEYS = (PHOTOS, NAMES, LOOKS, ARENAS, BRIGHT_ICE, TEAM_MASKS)     # the rows of art/parts.py (same words)
PICTURES = 'pictures'    # the Update tab's group row "Photos and logos": switches GROUP together, never stored
GROUP = (PHOTOS, LOOKS, ARENAS, TEAM_MASKS)     # what the group holds; team names are a row of their own
TOGETHER = {LOOKS: (LOOKS, BRIGHT_ICE)}     # 0.80.0 (owner): the new centre ice comes with this season's, no row of its own
EDITS = 'edits'             # the "My edits" switch
GAME_PATCH = 'game_patch'   # "32 teams and the year 2026 (game patch)"
SKIP_INTRO, NO_LOGIN = 'skip_intro', 'no_login'     # its two small switches (on / off at first)
PHOTOS_DEFAULT = 'photos_default'   # 0.65: "Photos, logos and team names" starts off (it takes long); set once the saved choice was reset
PATCH_ASKED ='game_patch_asked'    # the question before the first patch was answered
SAVE_BOTH = 'save_both'     # "Save for: EU + NA" (a single version follows the roster picked)
EXPORT_ONLY, EXPORT_FILE = 'export_only', 'export_file'     # "Export files to a folder" and the roster file picked for it
EXPORT_PATCH = 'export_patch'   # the export also holds the game patch (32 teams, the year 2026)
EXPORT_FROM_FILE = 'export_from_file'   # the export starts from the roster file, not from a roster of RPCS3
SAVE_MODE = 'save_mode'     # IN_PLACE or AS_NEW
IN_PLACE, AS_NEW = 'update', 'new'
BOTH = "EU + NA"


def row_parts(keys):
    """The picture parts the rows `keys` switch (TOGETHER): "This season's jerseys and centre ice" also the new centre ice."""
    return tuple(p for k in keys for p in TOGETHER.get(k, (k,)))


def load():
    try:
        with open(datasource.app_dir(FILE), encoding='utf-8') as f:
            values = json.load(f)
            return values if isinstance(values, dict) else {}
    except (OSError, ValueError):
        return {}


def save(values):
    try:
        with open(datasource.app_dir(FILE), 'w', encoding='utf-8') as f:
            json.dump(values, f)
    except OSError:
        pass
