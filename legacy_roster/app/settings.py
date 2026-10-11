"""The window's remembered choices (settings.json in the program's own folder)."""
import json

from .. import datasource

FILE = 'settings.json'
PHOTOS = 'photos'           # the "Photos, logos and team names" switch in settings['steps']
EDITS = 'edits'             # the "My edits" switch
SAVE_BOTH = 'save_both'     # "Save for: EU + NA" (a single version follows the roster picked)
EXPORT_ONLY, EXPORT_FILE = 'export_only', 'export_file'
SAVE_MODE = 'save_mode'     # IN_PLACE or AS_NEW
IN_PLACE, AS_NEW = 'update', 'new'
BOTH = "EU + NA"


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
