"""The Roster editor's "Equipment" window without a window toolkit: one player's stick, tape, helmet, visor, gloves,
skates and the two tucks.

The player picks from the game's own choices (equipment.py), with the game's own menu pictures from the player's disc
for the models (sticks, helmets, gloves, skates). "Apply to this player" keeps the choices he changed in edits.json
(`edit["equipment"]`); "Apply to the whole team" keeps the ones that make sense for a team (tape, helmet, visor, the
tucks) on the team (`team["equipment"]`), and every skater without a choice of his own gets them. Both are applied after
every update (edits.py). A goalie has his own list (equipment.GOALIE_CHOICES) and can wear a picture of his own on his
mask (`edit["mask_picture"]`, art/masks.py). The pictures are read in a worker thread and are a slice of
their own (`equip_pics`), so a click does not send them again.
"""
import io
import re
import threading

from .. import equipment as E
from ..editor import model
from . import dataurl

SLICE, PICS = 'equipment', 'equip_pics'
THUMB = (192, 96)               # pixels of a small picture (shown at 96 x 48, sharp at 200 %)
MODELS = ('stick', 'helmet', 'gloves', 'skates')       # the choices that are a list of pictures
GOALIE_MODELS = ('stick', 'mask', 'pads', 'blocker', 'trapper')
GOALIE_ORDER = ('mask', 'pads', 'blocker', 'trapper', 'stick', 'tape', 'jersey_tuck', 'neck')
ORDER = ('stick', 'tape', 'helmet', 'visor', 'visor_tint', 'gloves', 'skates', 'shoulder_pads', 'pant_length',
         'jersey_tuck', 'sock_tuck')


class EquipmentController:
    def __init__(self, host, editor):
        self.host, self.editor = host, editor
        editor.equipment = self
        self.lock = threading.RLock()
        self.who = None                 # the player shown (None: the window is closed)
        self.kind, self.mask_picture, self.mask_touched = 'skater', None, False
        self.typed, self.touched = {}, set()
        self.pics = {}                  # choice -> {number (str): data: link}
        self.numbers = {}               # choice -> the model numbers that can be picked
        self.loaded = False
        self.note = ''
        self._token = 0

    def changed(self):
        self.host.changed(SLICE)

    # --- open and close ------------------------------------------------------------------------------
    def open(self):
        ed = self.editor
        with ed.lock:
            p = ed.player if ed.card_open else None
            if ed.snap is None or p is None:
                ed.set_status("Pick a player first (equipment is for players that are in the roster).", 'warn')
                return
            if p.equipment is None:
                ed.set_status("This player has no equipment record in the roster.", 'warn')
                return
            snap, pictures = ed.snap, ed._pictures()
            who, have = p.who, dict(p.equipment)
            kind = 'goalie' if p.pos == 'G' else 'skater'
            table = snap.R.f[E.KINDS[kind][0]]
            seen = {c: sorted({table.get(i, E.tag(c, kind)) for i in range(table.cur_rec)}) for c in E.KINDS[kind][2]}
            picture = (ed.edits.get(ed.edit_key(p)) or {}).get('mask_picture')
        with self.lock:
            self._token += 1
            self.who, self.typed, self.touched = who, have, set()
            self.kind, self.mask_picture, self.mask_touched = kind, picture, False
            self.numbers = {c: list(seen[c]) for c in (GOALIE_MODELS if kind == 'goalie' else MODELS)}
            self.pics, self.loaded = {}, False
            self.note = ("" if pictures is not None else
                         "RPCS3 does not say where your game is, so the pictures are not shown here. You can still choose.")
            self.host.changed(PICS)
            self.changed()
            token = self._token
        self._read_game(pictures, token, kind)

    def close(self):
        with self.lock:
            self.who = None
            self._token += 1
            self.pics = {}
            self.host.changed(PICS)
            self.changed()

    # --- the game's pictures --------------------------------------------------------------------------
    def _read_game(self, pictures, token, kind='skater'):
        if pictures is None:
            with self.lock:
                self.loaded = True
                self.changed()
            return

        def job():
            try:
                found, usable = pictures.disc_work(lambda disc: (self._menu_pictures(disc, kind), self._usable(disc, kind)))
            except Exception:
                found, usable = {}, {}
            with self.lock:
                if token != self._token or self.who is None:
                    return
                for choice, items in found.items():
                    # the game's table also holds the models of older NHL games: NHL Legacy has no 3D picture
                    # for them and draws them blue, so only the models it can draw are offered (the numbers the
                    # roster already holds stay, they work)
                    ok = usable.get(choice)
                    if ok:
                        items = {n: url for n, url in items.items() if n in ok or n in self.numbers.get(choice, ())}
                    self.numbers[choice] = sorted(set(self.numbers.get(choice, ())) | set(items))
                    self.pics[choice] = {str(n): url for n, url in items.items()}
                self.loaded = True
                self.host.changed(PICS)
                self.changed()
        threading.Thread(target=job, daemon=True).start()

    @staticmethod
    def _usable(disc, kind='skater'):
        """{choice: model numbers with a 3D picture on the disc} (equipment.available)."""
        from ..art.disc import EbArchive
        names = []
        for name in ('nocacherender.big', 'cacherender.big'):
            if name not in disc.archives:
                disc.archives[name] = EbArchive.open(disc.source, name)
            names += disc.archives[name].entries
        return E.available(names, kind)

    @staticmethod
    def _menu_pictures(disc, kind='skater'):
        """{choice: {number: data: link}} of every model picture the disc has."""
        from PIL import Image
        from ..art.bigf import ArtFile
        arc = disc.archives['cache.big']
        out = {}
        menu = E.GOALIE_MENU if kind == 'goalie' else E.MENU
        for choice in (GOALIE_MODELS if kind == 'goalie' else MODELS + ('visor',)):
            folder, prefix, shift = menu[choice]
            pattern = re.compile(rf"^{E.MENU_ROOT}/{folder}/{prefix}(\d+)\.big$")
            items = {}
            for name in arc.entries:
                m = pattern.match(name)
                if m is None or int(m.group(1)) - shift < 0:
                    continue
                try:
                    img = Image.open(io.BytesIO(ArtFile(arc.read(name)).image()))
                    img.load()
                except Exception:
                    continue
                items[int(m.group(1)) - shift] = dataurl.picture(img, THUMB)
            out[choice] = items
        return out

    # --- the choices -----------------------------------------------------------------------------------
    def pick(self, choice, value):
        with self.lock:
            if self.who is None or choice not in E.KINDS[self.kind][2]:
                return
            try:
                n = int(value)
            except (TypeError, ValueError):
                return
            self.typed[choice] = n
            self.touched.add(choice)
            self.changed()

    def choose_mask_picture(self):
        with self.lock:
            if self.who is None or self.kind != 'goalie':
                return
            who = self.who
        link = self.editor.pick_picture("A picture for this goalie's mask")
        with self.lock:
            if link and self.who == who:
                self.mask_picture, self.mask_touched = link, True
                self.changed()

    def clear_mask_picture(self):
        with self.lock:
            if self.who is None or not self.mask_picture:
                return
            self.mask_picture, self.mask_touched = None, True
            self.changed()

    def mask_template(self):
        """Save the game's own colour map of this goalie's mask as a picture to paint on."""
        ed = self.editor
        with ed.lock, self.lock:
            if self._player() is None or self.kind != 'goalie':
                return
            n = self.typed.get('mask') or 0
            pictures = ed._pictures()
        from ..art import masks
        number = n if n and n not in E.MASK_FILES_MISSING and n <= E.MASK_LARGEST else 120
        path = ed.host.ask_save("Save the template", f"mask_{number}.png", ['PNG (*.png)'])
        if not path or pictures is None:
            return
        if not path.lower().endswith('.png'):
            path += '.png'

        def job():
            try:
                pictures.disc_work(lambda disc: masks.own_picture(disc, number)).save(path)
                text = "Saved. Paint over it in any picture program and keep it 512 x 512, then use My picture."
            except Exception as err:
                text = f"The template could not be saved: {err}"
            ed.set_status(text)
        threading.Thread(target=job, daemon=True).start()

    def _player(self):
        snap = self.editor.snap
        return snap.by_who.get(self.who) if snap is not None else None

    def apply_player(self):
        ed = self.editor
        with ed.lock, self.lock:
            p = self._player()
            if p is None or not (self.touched or self.mask_touched):
                ed.set_status("Nothing changed.")
                return
            key = ed.edit_key(p)
            e = dict(ed.edits.get(key) or {'label': p.name})
            if self.touched:
                e['equipment'] = dict(e.get('equipment') or {}, **{c: self.typed[c] for c in self.touched})
            if self.mask_touched:
                if self.mask_picture:
                    e['mask_picture'] = self.mask_picture
                else:
                    e.pop('mask_picture', None)
                self.mask_touched = False
            ed.edits[key] = e
            ed.session.add(key)
            ed._edits_saved()
            self.touched = set()
            ed.refresh()
            self.changed()

    def _team_slot(self):
        p = self._player()
        teams = model.club(p.teams) if p is not None else []
        return teams[0] if teams else None

    def apply_team(self):
        ed = self.editor
        with ed.lock, self.lock:
            slot = self._team_slot()
            wide = {c: self.typed[c] for c in self.touched if c in E.TEAM_WIDE}
            if slot is None or not wide:
                ed.set_status("Change the tape, helmet, visor or a tuck first: those can be set for a whole team.", 'warn')
                return
            mine = dict(ed.teams.get(str(slot)) or {})
            mine['equipment'] = dict(mine.get('equipment') or {}, **wide)
            ed.teams[str(slot)] = mine
            ed.session_teams.add(str(slot))
            ed._edits_saved(players=False)
            self.touched -= set(wide)
            ed.refresh()
            self.changed()

    def undo(self):
        """Take back this player's equipment edits and his team's."""
        ed = self.editor
        with ed.lock, self.lock:
            p = self._player()
            if p is None:
                return
            key = ed.edit_key(p)
            e = ed.edits.get(key)
            if e and ('equipment' in e or 'mask_picture' in e):
                e = {k: v for k, v in e.items() if k not in ('equipment', 'mask_picture')}
                if set(e) <= {'label'}:
                    ed.edits.pop(key, None)
                else:
                    ed.edits[key] = e
                ed.session.discard(key)
                ed._edits_saved()
            slot = self._team_slot()
            mine = ed.teams.get(str(slot)) if slot is not None else None
            if mine and 'equipment' in mine:
                mine = {k: v for k, v in mine.items() if k != 'equipment'}
                if mine:
                    ed.teams[str(slot)] = mine
                else:
                    ed.teams.pop(str(slot), None)
                ed.session_teams.discard(str(slot))
                ed._edits_saved(players=False)
            self.who = None
            self.pics = {}
            self.host.changed(PICS)
            ed.refresh()
            self.changed()
            ed.set_status("Equipment edits taken back. The roster is read again.")

    # --- what the page shows ---------------------------------------------------------------------------
    def _mine(self):
        ed = self.editor
        p = self._player()
        key = ed.edit_key(p) if p is not None else None
        slot = self._team_slot()
        return bool(((ed.edits.get(key) or {}).get('equipment')) or ((ed.edits.get(key) or {}).get('mask_picture')) or
                    ((ed.teams.get(str(slot)) or {}).get('equipment') if slot is not None else None))

    def snapshot(self):
        with self.editor.lock, self.lock:
            if self.who is None:
                return None
            p = self._player()
            if p is None:
                return None
            snap = self.editor.snap
            slot = self._team_slot()
            rows = []
            goalie = self.kind == 'goalie'
            options = E.GOALIE_OPTIONS if goalie else E.OPTIONS
            menu = E.GOALIE_MENU if goalie else E.MENU
            for choice in (GOALIE_ORDER if goalie else ORDER):
                value = self.typed.get(choice)
                if choice in options:
                    items = [{'value': n, 'label': label} for n, label in options[choice]]
                    if value not in {n for n, _ in options[choice]}:
                        items.append({'value': value, 'label': f"Number {value}"})
                    kind = 'buttons'
                else:
                    numbers = list(self.numbers.get(choice, []))
                    if value not in numbers:
                        numbers.append(value)
                    items = [{'value': n} for n in sorted(numbers)]
                    kind = 'pictures'
                rows.append({'choice': choice, 'label': E.KINDS[self.kind][2][choice][1], 'kind': kind, 'value': value,
                             'items': items, 'touched': choice in self.touched, 'team': choice in E.TEAM_WIDE and not goalie,
                             'picture': choice in menu})
            return {'who': self.who, 'title': f"{p.name}: equipment", 'note': self.note, 'loaded': self.loaded,
                    'rows': rows, 'team': snap.team_name(slot) if slot is not None else None,
                    'can_team': slot is not None and not goalie and any(c in E.TEAM_WIDE for c in self.touched),
                    'can_player': bool(self.touched or self.mask_touched), 'undo': self._mine(),
                    'goalie': goalie, 'mask_picture': (self.mask_picture or '').replace('file:', '') or None}

    def pics_view(self):
        with self.lock:
            return {c: dict(v) for c, v in self.pics.items()} if self.who is not None else {}
