"""The Roster editor's "Jerseys and ice" window without a window toolkit: a team's jerseys and centre-ice logo.

    colours      the two colours (and a crest picture) the jerseys are made from
    versions     one row per jersey version the game has for the team (the ones Play Now cycles through with
                 "Change Jerseys"): keep the game's own, make it from the colours, or use the player's own picture
    ice          the centre-ice logo: the game's own, drawn from the team's logo and arena name, or the player's picture

What is chosen is kept in edits.json (`teams[slot]["uniforms"]` / `["ice"]`, see edits.py) and installed by every update that
has "Photos, logos and team names" on (art/looks.py); "Restore the game's own pictures" puts the game's own back. A player's own
jersey picture is a flat 1024 x 1024 colour map in the game's shirt layout: the window saves the game's own as a template to
paint on. Reading the game's disc takes a moment, so it runs in worker threads (editor/pictures.py `work`); the small
pictures are a slice of their own (`thumbs`), so typing a colour does not send them all again.
"""
import threading

from .. import edits
from .. import layout as L
from ..art import looks
from . import dataurl

SLICE, THUMBS = 'uniforms', 'thumbs'
GAME, COLOURS, FILE = 'game', 'colours', 'file'
THUMB = 156                     # pixels of a small picture (shown at 78 on the page, sharp at 200 %)
ICE = 'ice'


def _hex(colour):
    return '#%02x%02x%02x' % tuple(colour)


class UniformsController:
    def __init__(self, host, editor):
        self.host, self.editor = host, editor
        editor.uniforms = self
        self.lock = threading.RLock()
        self.slot = None                # the team shown (None: the window is closed)
        self.thumbs = {}                # variant (str) or 'ice' -> data: link (None: no picture)
        self._tokens = {}               # variant -> the latest request (an older picture is dropped)

    def changed(self):
        self.host.changed(SLICE)

    # --- open and close ------------------------------------------------------------------------------
    def open(self, slot):
        ed = self.editor
        with ed.lock:
            snap = ed.snap
            if snap is None:
                return
            R = snap.R
            mine = ed.teams.get(str(slot)) or {}
            name = snap.team_name(slot)
            pictures = ed._pictures()
        with self.lock:
            self.slot, self.name, self.R = slot, name, R
            self.default_team = slot in looks.NEW_TEAMS
            self.uniforms = {'colours': dict((mine.get('uniforms') or {}).get('colours') or {}),
                             'versions': dict((mine.get('uniforms') or {}).get('versions') or {})}
            self.ice = dict(mine.get('ice') or {})
            if self.default_team:
                from .. import builder
                arena, _city, primary, secondary = builder.NHL_LOOK[slot]
            else:
                primary, secondary = looks.team_colours(R, slot)
                arena = looks.team_arena(R, slot)
            self.base = {'primary': tuple(primary), 'secondary': tuple(secondary), 'arena': arena}
            self.typed = {part: self.uniforms['colours'].get(part) or _hex(self.base[part])
                          for part in ('primary', 'secondary')}
            self.arena = self.ice.get('arena') or arena
            self.pictures = pictures
            self.versions = looks.roster_versions(R, slot) or [(v, light, False) for v, light
                                                               in looks.DEFAULT_VERSIONS.get(slot, ())]
            self.standard = {}          # variant -> uses the shared shirt layout (None: not known yet)
            self.loaded = False
            self.note = ("RPCS3 does not say where your game is, so the pictures are not shown here. You can still "
                         "choose; nothing is made until an update with pictures on.") if pictures is None else ''
            self.thumbs, self._tokens = {}, {}
            self.host.changed(THUMBS)
            self.changed()
        self._read_game()

    def close(self):
        with self.lock:
            self.slot = None
            self.thumbs, self._tokens = {}, {}
            self.host.changed(THUMBS)
            self.changed()

    def _alive(self, slot):
        return self.slot == slot

    # --- what is chosen --------------------------------------------------------------------------------
    def _light(self, variant):
        return next((light for v, light, _d in self.versions if v == variant), False)

    def _default_mode(self, variant, light):
        return COLOURS if self.default_team and (variant, light) in looks.DEFAULT_VERSIONS.get(self.slot, ()) else GAME

    def _use(self, variant):
        return self.uniforms['versions'].get(str(variant)) or self._default_mode(variant, self._light(variant))

    def _mode(self, variant):
        use = self._use(variant)
        return FILE if use.startswith('file:') else use

    def _ice_mode(self):
        use = self.ice.get('use') or ('logo' if self.default_team else GAME)
        return FILE if use.startswith('file:') else COLOURS if use == 'logo' else GAME

    def _colour(self, part):
        return looks.parse_colour(self.typed.get(part), self.base[part])

    def _variant(self, variant):
        try:
            variant = int(variant)
        except (TypeError, ValueError):
            return None
        return variant if any(v == variant for v, _l, _d in self.versions) else None

    def set_colour(self, part, text):
        with self.lock:
            if self.slot is None or part not in ('primary', 'secondary'):
                return
            before = self._colour(part)
            self.typed[part] = str(text or '')
            self.changed()
            if self._colour(part) != before:
                self._refresh_colour_rows()

    def choose_crest(self):
        with self.lock:
            if self.slot is None:
                return
            slot = self.slot
        link = self.editor.pick_picture("A crest for this team's jerseys")
        with self.lock:
            if link and self._alive(slot):
                self.uniforms['colours']['crest'] = link
                self.changed()
                self._refresh_colour_rows()

    def clear_crest(self):
        with self.lock:
            if self.slot is None:
                return
            self.uniforms['colours'].pop('crest', None)
            self.changed()
            self._refresh_colour_rows()

    def pick(self, variant, value):
        with self.lock:
            variant = self._variant(variant) if self.slot is not None else None
            if variant is None or value not in (GAME, COLOURS, FILE):
                return
            slot = self.slot
        if value == FILE:
            link = self.editor.pick_picture("Your colour map for this jersey (a flat 1024 x 1024 picture)")
            if not link:
                self.changed()          # the page shows the earlier choice again
                return
            value = link
        with self.lock:
            if not self._alive(slot):
                return
            self.uniforms['versions'][str(variant)] = value
            self.changed()
            self._thumb(variant)

    def pick_ice(self, value):
        with self.lock:
            if self.slot is None or value not in (GAME, COLOURS, FILE):
                return
            slot = self.slot
        if value == FILE:
            link = self.editor.pick_picture("Your centre-ice logo (1024 x 1024, clear background)")
            if not link:
                self.changed()
                return
            use = link
        else:
            use = 'logo' if value == COLOURS else GAME
        with self.lock:
            if not self._alive(slot):
                return
            self.ice['use'] = use
            self.changed()
            self._ice_thumb()

    def set_arena(self, text):
        with self.lock:
            if self.slot is None:
                return
            self.arena = str(text or '')
            self.changed()
            if self._ice_mode() == COLOURS:
                self._ice_thumb()

    # --- pictures, made in worker threads ------------------------------------------------------------------
    def _read_game(self):
        """Which versions use the shared shirt layout, then the pictures."""
        with self.lock:
            slot, pictures, versions = self.slot, self.pictures, list(self.versions)
        if pictures is None:
            with self.lock:
                self.loaded = True
                self.changed()
            return

        def job():
            try:
                found = pictures.work(lambda m: {v: m.standard(slot, v) for v, _l, _d in versions})
            except Exception:
                found = {}
            with self.lock:
                if not self._alive(slot):
                    return
                self.standard.update(found)
                self.loaded = True
                self.changed()
                for variant, _light, _d in self.versions:
                    self._thumb(variant)
                self._ice_thumb()
        threading.Thread(target=job, daemon=True).start()

    def _logo(self, plain=False):
        """The team's logo for the previews (a Pillow picture or None)."""
        link = self.uniforms['colours'].get('crest') or (self.editor.teams.get(str(self.slot)) or {}).get('logo')
        if not link:
            code = next((a for a, s in L.API_TO_SLOT.items() if s == self.slot), None)
            link = ((self.editor.update.pack or {}).get('nhl_logos') or {}).get(code)
        if not link:
            return None
        from ..art import install
        from ..art.photopack import PhotoPack, PictureCache
        return looks.team_logo(install.plain_logo_url(link) if plain else link, PhotoPack.open(), PictureCache())

    def _request(self, key):
        token = self._tokens.get(key, 0) + 1
        self._tokens[key] = token
        return token

    def _deliver(self, slot, key, token, img):
        url = dataurl.picture(img, (THUMB, THUMB)) if img is not None else None
        with self.lock:
            if not self._alive(slot) or self._tokens.get(key) != token:
                return
            self.thumbs[key] = url
            self.host.changed(THUMBS)

    def _thumb(self, variant):
        if self.pictures is None or self.slot is None:
            return
        slot, pictures, key = self.slot, self.pictures, str(variant)
        token = self._request(key)
        light = self._light(variant)
        use = self._use(variant)
        kind = FILE if use.startswith('file:') else use
        colours = (self._colour('primary'), self._colour('secondary'))
        logo_wanted = kind == COLOURS

        def job():
            try:
                from PIL import Image
                picture = None
                if kind == FILE:
                    picture = Image.open(use[5:])
                    picture.load()
                    picture = picture.convert('RGB').resize((1024, 1024))
                logo = self._logo(light) if logo_wanted else None
                img = pictures.work(lambda m: m.thumbnail(slot, variant, light, kind, logo, colours, picture))
            except Exception:
                img = None
            self._deliver(slot, key, token, img)
        threading.Thread(target=job, daemon=True).start()

    def _refresh_colour_rows(self):
        for variant, _light, _d in self.versions:
            if self._use(variant) == COLOURS:
                self._thumb(variant)
        if self._ice_mode() == COLOURS:
            self._ice_thumb()

    def _ice_thumb(self):
        if self.pictures is None or self.slot is None:
            return
        slot, pictures = self.slot, self.pictures
        token = self._request(ICE)
        mode, use = self._ice_mode(), self.ice.get('use') or ''
        arena, ink = self.arena.strip() or self.base['arena'], looks._ink(self._colour('secondary'))

        def job():
            try:
                from PIL import Image
                if mode == FILE:
                    img = Image.open(use[5:])
                    img.load()
                    img = looks.finish_centre(img.convert('RGBA').resize((1024, 1024)))
                elif mode == COLOURS:
                    img = looks.centre_logo(self._logo(True), arena, ink)
                else:
                    img = pictures.work(lambda m: m.own_centre(slot))
                if img is not None:
                    back = Image.new('RGBA', img.size, (190, 215, 240, 255))
                    back.alpha_composite(img.convert('RGBA'))
                    img = back
            except Exception:
                img = None
            self._deliver(slot, ICE, token, img)
        threading.Thread(target=job, daemon=True).start()

    def template(self, variant=None):
        """Save the game's own colour map of a jersey version (or, with no version, the centre-ice logo) as a
        picture to paint on."""
        with self.lock:
            if self.slot is None:
                return
            slot, pictures = self.slot, self.pictures
            ice = variant is None or variant == ICE
            if not ice:
                variant = self._variant(variant)
                if variant is None:
                    return
        filename = f"centre_ice_{slot}.png" if ice else f"jersey_{slot}_{variant}.png"
        path = self.editor.host.ask_save("Save the template", filename, ['PNG (*.png)'])
        if not path or pictures is None:
            return
        if not path.lower().endswith('.png'):
            path += '.png'

        def job():
            try:
                if ice:
                    pictures.work(lambda m: m.own_centre(slot)).save(path)
                    text = "Saved. Paint over it, keep it 1024 x 1024 with a clear background, then use \"My picture...\"."
                else:
                    pictures.work(lambda m: m.own_colour_map(slot, variant)).convert('RGB').save(path)
                    text = "Saved. Paint over it in any picture program and keep it 1024 x 1024, then use \"My picture...\"."
            except Exception as err:
                text = f"The template could not be saved: {err}"
            with self.lock:
                if self._alive(slot):
                    self.note = text
                    self.changed()
        threading.Thread(target=job, daemon=True).start()

    # --- keeping it --------------------------------------------------------------------------------------
    def _collect(self):
        """The team edit's 'uniforms' and 'ice' parts: only what differs from what the update does anyway."""
        colours = {}
        for part in ('primary', 'secondary'):
            if self._colour(part) != self.base[part]:
                colours[part] = _hex(self._colour(part))
        if self.uniforms['colours'].get('crest'):
            colours['crest'] = self.uniforms['colours']['crest']
        versions = {}
        for variant, light, _d in self.versions:
            use = self.uniforms['versions'].get(str(variant))
            if use and use != self._default_mode(variant, light):
                versions[str(variant)] = use
        uniforms = {}
        if colours:
            uniforms['colours'] = colours
        if versions:
            uniforms['versions'] = versions
        ice = {}
        default = 'logo' if self.default_team else GAME
        if self.ice.get('use') and self.ice['use'] != default:
            ice['use'] = self.ice['use']
        arena = self.arena.strip()
        if arena and arena != self.base['arena']:
            ice['arena'] = arena
        return uniforms, ice

    def _save(self, uniforms, ice):
        ed = self.editor
        with ed.lock:
            team = dict(ed.teams.get(str(self.slot)) or {})
            for key, value in (('uniforms', uniforms), ('ice', ice)):
                if value:
                    team[key] = value
                else:
                    team.pop(key, None)
            if team:
                ed.teams[str(self.slot)] = team
            else:
                ed.teams.pop(str(self.slot), None)
            ed._edits_saved(players=False)
            ed.changed()

    def apply(self):
        with self.lock:
            if self.slot is None:
                return
            self._save(*self._collect())
        self.editor.set_status("Jerseys and ice kept. They are made in the next update with \"Photos, logos and team "
                               "names\" on (and My edits on).", 'warn')
        self.close()

    def undo(self):
        with self.lock:
            if self.slot is None:
                return
            self._save({}, {})
        self.editor.set_status("This team's jerseys and ice are back to what the update makes (a changed game keeps "
                               "them until the next update).", 'warn')
        self.close()

    # --- what the page shows ------------------------------------------------------------------------------
    def _label(self, variant, light, default):
        kind = "Away (light)" if light else "Home (dark)"
        return f"{kind}, the one the game picks first" if default else f"{kind}, another version ({variant})"

    def snapshot(self):
        with self.lock:
            if self.slot is None:
                return None
            rows = []
            for variant, light, default in self.versions:
                options = [[GAME, "The game's own"]]
                if self.standard.get(variant) is not False:
                    options.append([COLOURS, "From the colours"])
                options.append([FILE, "My picture..."])
                rows.append({'variant': variant, 'label': self._label(variant, light, default), 'light': light,
                             'mode': self._mode(variant), 'options': options})
            return {'slot': self.slot, 'title': f"{self.name}: jerseys and ice", 'note': self.note,
                    'loaded': self.loaded, 'pictures': self.pictures is not None,
                    'colours': {part: {'text': self.typed[part], 'hex': _hex(self._colour(part))}
                                for part in ('primary', 'secondary')},
                    'crest': "Crest: your picture" if self.uniforms['colours'].get('crest') else "Crest: the team's logo",
                    'crest_mine': bool(self.uniforms['colours'].get('crest')),
                    'rows': rows if self.loaded else [],
                    'ice': {'mode': self._ice_mode(), 'arena': self.arena,
                            'options': [[GAME, "The game's own"], [COLOURS, "From the logo"], [FILE, "My picture..."]]}}

    def thumbs_view(self):
        with self.lock:
            return dict(self.thumbs) if self.slot is not None else {}
