"""The "Jerseys and ice" window of the Roster editor: a team's jerseys and centre-ice logo.

    colours      the two colours (and a crest picture) the jerseys are made from
    versions     one row per jersey version the game has for the team (the ones Play Now cycles through with
                 "Change Jerseys"): keep the game's own, make it from the colours, or use the player's own picture
    ice          the centre-ice logo: the game's own, drawn from the team's logo and arena name, or the player's picture

What is chosen is kept in edits.json (`teams[slot]["uniforms"]` / `["ice"]`, see edits.py) and installed by every update that
has "Photos, logos and team names" on (art/looks.py); "Restore the game's own pictures" puts the game's own back. A player's own
jersey picture is a flat 1024 x 1024 colour map in the game's shirt layout: the window saves the game's own as a template to
paint on. A photo of a real jersey cannot be wrapped onto that layout by a program.

Reading the game's disc takes a moment, so it runs in a worker thread (editor/pictures.py `work`); results come back through
the window's queue like everything else in the editor.
"""
import threading
import tkinter as tk

import customtkinter as ctk

from .. import edits
from .. import layout as L
from .. import theme as T
from ..art import looks
from ..widgets import Choice, GhostButton, PrimaryButton

GAME, COLOURS, FILE = 'game', 'colours', 'file'
THUMB = 78
WIDTH_TEXT = 640


def _hex(colour):
    return '#%02x%02x%02x' % tuple(colour)


class UniformsWindow(ctk.CTkToplevel):
    def __init__(self, tab, slot):
        super().__init__(tab, fg_color=T.BG)
        self.tab, self.slot = tab, slot
        self.title("Jerseys and ice")
        self.geometry(f"700x{max(480, min(780, int(self.winfo_screenheight() / T.scaling(self)) - 110))}")
        self.transient(tab.winfo_toplevel())
        snap = tab.snap
        self.R = snap.R
        self.default_team = slot in looks.NEW_TEAMS
        mine = (tab.teams.get(str(slot)) or {})
        self.uniforms = {'colours': dict((mine.get('uniforms') or {}).get('colours') or {}),
                         'versions': dict((mine.get('uniforms') or {}).get('versions') or {})}
        self.ice = dict(mine.get('ice') or {})
        if self.default_team:
            from .. import builder
            arena, _city, primary, secondary = builder.NHL_LOOK[slot]
        else:
            primary, secondary = looks.team_colours(self.R, slot)
            arena = looks.team_arena(self.R, slot)
        self.base = {'primary': tuple(primary), 'secondary': tuple(secondary), 'arena': arena}
        self.pictures = tab._pictures()
        self.versions = looks.roster_versions(self.R, slot) or [(v, light, False) for v, light
                                                                in looks.DEFAULT_VERSIONS.get(slot, ())]
        self.standard = {}              # variant -> uses the shared shirt layout (None: not known yet)
        self.rows = {}                  # variant -> dict of widgets
        self.token = 0
        self.alive = True
        self.bind('<Destroy>', lambda e: setattr(self, 'alive', False) if e.widget is self else None)
        self._build()
        self._read_game()

    # --- the window --------------------------------------------------------------------------------------------
    def _build(self):
        name = self.tab.snap.team_name(self.slot)
        ctk.CTkLabel(self, text=name + ": jerseys and ice", font=T.font(16, 'bold'), text_color=T.STRONG).pack(
            padx=16, pady=(14, 2), anchor='w')
        ctk.CTkLabel(self, text="Pick how each jersey version is made. The game shows the change after an update with "
                                "\"Photos, logos and team names\" on; \"Restore the game's own pictures\" puts the game's own "
                                "back. A jersey made from colours uses the team's logo as its crest.",
                     font=T.font(12), text_color=T.MUTED, wraplength=WIDTH_TEXT, justify='left').pack(padx=16, anchor='w')
        self.note = ctk.CTkLabel(self, text="", font=T.font(12), text_color=T.GOLD, wraplength=WIDTH_TEXT, justify='left')
        self.note.pack(padx=16, pady=(4, 0), anchor='w')

        box = ctk.CTkFrame(self, fg_color=T.CARD, corner_radius=T.RADIUS)
        box.pack(fill='x', padx=16, pady=(8, 6))
        ctk.CTkLabel(box, text="Colours", font=T.font(14, 'semibold'), text_color=T.STRONG).grid(
            row=0, column=0, padx=12, pady=(8, 2), sticky='w')
        self.entries, self.swatches = {}, {}
        shown = self.uniforms['colours']
        for k, (part, label) in enumerate((('primary', "Main colour"), ('secondary', "Second colour"))):
            ctk.CTkLabel(box, text=label, font=T.font(12), text_color=T.MUTED).grid(row=k + 1, column=0, padx=12, sticky='w')
            e = ctk.CTkEntry(box, width=100, height=28, fg_color=T.CELL, border_color=T.BORDER, text_color=T.TEXT,
                             font=T.font(13))
            e.insert(0, shown.get(part) or _hex(self.base[part]))
            e.grid(row=k + 1, column=1, padx=6, pady=3, sticky='w')
            e.bind('<KeyRelease>', lambda _e, p=part: self._colour_typed(p))
            sw = ctk.CTkLabel(box, text="", width=28, height=28, corner_radius=6, fg_color=_hex(self._colour(part)))
            sw.grid(row=k + 1, column=2, padx=4)
            GhostButton(box, "Choose...", lambda p=part: self._choose_colour(p), height=26).grid(row=k + 1, column=3, padx=4)
            self.entries[part], self.swatches[part] = e, sw
        self.crest_label = ctk.CTkLabel(box, text="", font=T.font(12), text_color=T.MUTED)
        self.crest_label.grid(row=3, column=0, columnspan=2, padx=12, pady=(3, 8), sticky='w')
        crest = ctk.CTkFrame(box, fg_color='transparent')
        crest.grid(row=3, column=2, columnspan=3, sticky='w', pady=(3, 8))
        GhostButton(crest, "Crest picture...", self._choose_crest, height=26).pack(side='left', padx=(0, 4))
        GhostButton(crest, "Team logo", self._clear_crest, height=26).pack(side='left')
        self._crest_text()

        self.list = ctk.CTkScrollableFrame(self, fg_color=T.CARD, corner_radius=T.RADIUS,
                                           scrollbar_button_color=T.BORDER_STRONG, scrollbar_button_hover_color=T.FAINT)
        self.list.pack(fill='both', expand=True, padx=16, pady=(0, 6))
        self.loading = ctk.CTkLabel(self.list, text="Reading the game's jerseys...", font=T.font(13), text_color=T.FAINT)
        self.loading.pack(pady=20)

        bar = ctk.CTkFrame(self, fg_color='transparent')
        bar.pack(fill='x', padx=16, pady=(2, 14))
        PrimaryButton(bar, "Apply", self._apply, width=110, height=34).pack(side='left')
        GhostButton(bar, "Undo all for this team", self._undo, height=30).pack(side='left', padx=(8, 0))
        GhostButton(bar, "Close", self.destroy, height=30).pack(side='right')

    def _fill_rows(self):
        self.loading.destroy()
        for variant, light, default in self.versions:
            self._row(variant, light, default)
        self._ice_row()
        for variant, light, _d in self.versions:
            self._thumb(variant)
        self._ice_thumb()
        self.after(150, lambda: self.list._parent_canvas.yview_moveto(0) if self.alive else None)

    def _label(self, variant, light, default):
        kind = "Away (light)" if light else "Home (dark)"
        return f"{kind}, the one the game picks first" if default else f"{kind}, another version ({variant})"

    def _row(self, variant, light, default):
        row = ctk.CTkFrame(self.list, fg_color=T.CELL, corner_radius=10)
        row.pack(fill='x', pady=3, padx=2)
        pic = ctk.CTkLabel(row, text="", width=THUMB, height=THUMB)
        pic.grid(row=0, column=0, rowspan=2, padx=8, pady=6)
        ctk.CTkLabel(row, text=self._label(variant, light, default), font=T.font(13, 'semibold'), text_color=T.STRONG,
                     anchor='w').grid(row=0, column=1, sticky='w', pady=(8, 0))
        standard = self.standard.get(variant)
        options = [(GAME, "The game's own", None)]
        if standard is not False:
            options.append((COLOURS, "From the colours", None))
        options.append((FILE, "My picture...", None))
        choice = Choice(row, options, lambda v, k=variant: self._pick(k, v), height=32)
        choice.grid(row=1, column=1, sticky='w', pady=(0, 8))
        choice.set(self._mode(variant))
        template = GhostButton(row, "Save a template...", lambda k=variant: self._template(k), height=26)
        template.grid(row=0, column=2, rowspan=2, padx=8)
        row.columnconfigure(1, weight=1)
        self.rows[variant] = {'pic': pic, 'choice': choice, 'light': light}

    def _ice_row(self):
        ctk.CTkLabel(self.list, text="Centre-ice logo", font=T.font(14, 'semibold'), text_color=T.STRONG).pack(
            padx=8, pady=(10, 2), anchor='w')
        row = ctk.CTkFrame(self.list, fg_color=T.CELL, corner_radius=10)
        row.pack(fill='x', pady=3, padx=2)
        self.ice_pic = ctk.CTkLabel(row, text="", width=THUMB, height=THUMB)
        self.ice_pic.grid(row=0, column=0, rowspan=3, padx=8, pady=6)
        options = [(GAME, "The game's own", None), (COLOURS, "From the logo", None), (FILE, "My picture...", None)]
        self.ice_choice = Choice(row, options, self._pick_ice, height=32)
        self.ice_choice.grid(row=0, column=1, sticky='w', pady=(8, 2))
        self.ice_choice.set(self._ice_mode())
        line = ctk.CTkFrame(row, fg_color='transparent')
        line.grid(row=1, column=1, sticky='w')
        ctk.CTkLabel(line, text="Arena name on the ice", font=T.font(12), text_color=T.MUTED).pack(side='left', padx=(0, 6))
        self.arena = ctk.CTkEntry(line, width=220, height=28, fg_color=T.CELL, border_color=T.BORDER, text_color=T.TEXT,
                                  font=T.font(13))
        self.arena.insert(0, self.ice.get('arena') or self.base['arena'])
        self.arena.pack(side='left')
        ctk.CTkLabel(row, text="A picture of your own: 1024 x 1024 with a clear background; the strip in the middle, where "
                               "the red line crosses, is made clear by the program.", font=T.font(11), text_color=T.FAINT,
                     wraplength=330, justify='left', anchor='w').grid(row=2, column=1, sticky='w', pady=(2, 8))
        GhostButton(row, "Save a template...", self._ice_template, height=26).grid(row=0, column=2, rowspan=3, padx=8)
        row.columnconfigure(1, weight=1)

    # --- what is chosen ----------------------------------------------------------------------------------------
    def _default_mode(self, variant, light):
        return COLOURS if self.default_team and (variant, light) in looks.DEFAULT_VERSIONS.get(self.slot, ()) else GAME

    def _mode(self, variant):
        light = next(l for v, l, _d in self.versions if v == variant)
        use = self.uniforms['versions'].get(str(variant)) or self._default_mode(variant, light)
        return FILE if use.startswith('file:') else use

    def _ice_mode(self):
        use = self.ice.get('use') or ('logo' if self.default_team else 'game')
        return FILE if use.startswith('file:') else COLOURS if use == 'logo' else GAME

    def _colour(self, part):
        return looks.parse_colour(self.entries[part].get() if part in getattr(self, 'entries', {}) else
                                  self.uniforms['colours'].get(part), self.base[part])

    def _colour_typed(self, part):
        self.swatches[part].configure(fg_color=_hex(self._colour(part)))
        self._refresh_colour_rows()

    def _choose_colour(self, part):
        from tkinter import colorchooser
        picked = colorchooser.askcolor(color=_hex(self._colour(part)), parent=self, title="Choose a colour")
        if picked and picked[1]:
            self.entries[part].delete(0, 'end')
            self.entries[part].insert(0, picked[1])
            self._colour_typed(part)

    def _crest_text(self):
        crest = self.uniforms['colours'].get('crest')
        self.crest_label.configure(text="Crest: your picture" if crest else "Crest: the team's logo")

    def _choose_crest(self):
        link = self.tab._pick_picture("A crest for this team's jerseys")
        if link:
            self.uniforms['colours']['crest'] = link
            self._crest_text()
            self._refresh_colour_rows()

    def _clear_crest(self):
        self.uniforms['colours'].pop('crest', None)
        self._crest_text()
        self._refresh_colour_rows()

    def _pick(self, variant, value):
        if value == FILE:
            link = self.tab._pick_picture("Your colour map for this jersey (a flat 1024 x 1024 picture)")
            if not link:
                self.rows[variant]['choice'].set(self._mode(variant))
                return
            self.uniforms['versions'][str(variant)] = link
        else:
            self.uniforms['versions'][str(variant)] = value
        self._thumb(variant)

    def _pick_ice(self, value):
        if value == FILE:
            link = self.tab._pick_picture("Your centre-ice logo (1024 x 1024, clear background)")
            if not link:
                self.ice_choice.set(self._ice_mode())
                return
            self.ice['use'] = link
        else:
            self.ice['use'] = 'logo' if value == COLOURS else GAME
        self._ice_thumb()

    # --- pictures, made in a worker thread ----------------------------------------------------------------------
    def _later(self, fn):
        self.tab.app.queue.put(('ui', lambda: fn() if self.alive else None))

    def _read_game(self):
        """Which versions use the shared shirt layout, then the rows."""
        if self.pictures is None:
            self.note.configure(text="RPCS3 does not say where your game is, so the pictures are not shown here. "
                                     "You can still choose; nothing is made until an update with pictures on.")
            self._fill_rows()
            return

        def job():
            try:
                found = self.pictures.work(lambda m: {v: m.standard(self.slot, v) for v, _l, _d in self.versions})
            except Exception:
                found = {}
            self._later(lambda: (self.standard.update(found), self._fill_rows()))
        threading.Thread(target=job, daemon=True).start()

    def _logo(self, plain=False):
        """The team's logo for the previews (a Pillow picture or None)."""
        link = self.uniforms['colours'].get('crest') or (self.tab.teams.get(str(self.slot)) or {}).get('logo')
        if not link:
            code = next((a for a, s in L.API_TO_SLOT.items() if s == self.slot), None)
            link = ((self.tab.app.pack or {}).get('nhl_logos') or {}).get(code)
        if not link:
            return None
        from ..art import install
        from ..art.photopack import PhotoPack, PictureCache
        return looks.team_logo(install.plain_logo_url(link) if plain else link, PhotoPack.open(), PictureCache())

    def _show(self, label, img):
        if img is None:
            label.configure(image=None, text="no picture")
            return
        img = img.convert('RGBA')
        photo = ctk.CTkImage(light_image=img, dark_image=img, size=(THUMB, THUMB))
        label._photo = photo
        label.configure(image=photo, text="")

    def _thumb(self, variant):
        row = self.rows.get(variant)
        if row is None or self.pictures is None:
            return
        self.token += 1
        token, light = self.token, row['light']
        use = self.uniforms['versions'].get(str(variant)) or self._default_mode(variant, light)
        kind = FILE if use.startswith('file:') else use
        colours = (self._colour('primary'), self._colour('secondary'))

        def job():
            try:
                from PIL import Image
                picture = None
                if kind == FILE:
                    picture = Image.open(use[5:])
                    picture.load()
                    picture = picture.convert('RGB').resize((1024, 1024))
                logo = self._logo(light) if kind == COLOURS else None
                img = self.pictures.work(lambda m: m.thumbnail(self.slot, variant, light, kind, logo, colours, picture))
            except Exception:
                img = None
            self._later(lambda: self._show(row['pic'], img))
        threading.Thread(target=job, daemon=True).start()

    def _refresh_colour_rows(self):
        for variant in self.rows:
            use = self.uniforms['versions'].get(str(variant)) or self._default_mode(variant, self.rows[variant]['light'])
            if use == COLOURS:
                self._thumb(variant)
        if self._ice_mode() == COLOURS:
            self._ice_thumb()

    def _ice_thumb(self):
        if self.pictures is None:
            return
        mode, use = self._ice_mode(), self.ice.get('use') or ''
        arena, ink = self.arena.get().strip() or self.base['arena'], looks._ink(self._colour('secondary'))

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
                    img = self.pictures.work(lambda m: m.own_centre(self.slot))
                if img is not None:
                    back = Image.new('RGBA', img.size, (190, 215, 240, 255))
                    back.alpha_composite(img.convert('RGBA'))
                    img = back.resize((THUMB * 2, THUMB * 2))
            except Exception:
                img = None
            self._later(lambda: self._show(self.ice_pic, img))
        threading.Thread(target=job, daemon=True).start()

    def _template(self, variant):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(parent=self, title="Save the template", defaultextension='.png',
                                            initialfile=f"jersey_{self.slot}_{variant}.png", filetypes=[("PNG", "*.png")])
        if not path or self.pictures is None:
            return

        def job():
            try:
                img = self.pictures.work(lambda m: m.own_colour_map(self.slot, variant))
                img.convert('RGB').save(path)
                text = "Saved. Paint over it in any picture program and keep it 1024 x 1024, then use \"My picture...\"."
            except Exception as err:
                text = f"The template could not be saved: {err}"
            self._later(lambda: self.note.configure(text=text))
        threading.Thread(target=job, daemon=True).start()

    def _ice_template(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(parent=self, title="Save the template", defaultextension='.png',
                                            initialfile=f"centre_ice_{self.slot}.png", filetypes=[("PNG", "*.png")])
        if not path or self.pictures is None:
            return

        def job():
            try:
                img = self.pictures.work(lambda m: m.own_centre(self.slot))
                img.save(path)
                text = "Saved. Paint over it, keep it 1024 x 1024 with a clear background, then use \"My picture...\"."
            except Exception as err:
                text = f"The template could not be saved: {err}"
            self._later(lambda: self.note.configure(text=text))
        threading.Thread(target=job, daemon=True).start()

    # --- keeping it --------------------------------------------------------------------------------------------
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
        arena = self.arena.get().strip() if hasattr(self, 'arena') else ''
        if arena and arena != self.base['arena']:
            ice['arena'] = arena
        return uniforms, ice

    def _save(self, uniforms, ice):
        tab = self.tab
        team = dict(tab.teams.get(str(self.slot)) or {})
        for key, value in (('uniforms', uniforms), ('ice', ice)):
            if value:
                team[key] = value
            else:
                team.pop(key, None)
        if team:
            tab.teams[str(self.slot)] = team
        else:
            tab.teams.pop(str(self.slot), None)
        edits.save(teams=tab.teams)
        tab._update_edits_button()

    def _apply(self):
        uniforms, ice = self._collect()
        self._save(uniforms, ice)
        self.tab.set_status("Jerseys and ice kept. They are made in the next update with \"Photos, logos and team names\" on "
                            "(and My edits on).", T.GOLD)
        self.destroy()

    def _undo(self):
        self._save({}, {})
        self.tab.set_status("This team's jerseys and ice are back to what the update makes (a changed game keeps them until "
                            "the next update).", T.GOLD)
        self.destroy()
