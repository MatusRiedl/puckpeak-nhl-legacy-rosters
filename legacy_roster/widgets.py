"""The pieces the window is built from: cards, chips, pill buttons, list rows, the result banner,
the flags of the game's versions."""
import customtkinter as ctk

from . import theme as T

_UNSET = object()


def configure_if_changed(widget, **options):
    """configure() only the options whose value differs from what this helper set last time: every
    configure() of a customtkinter widget redraws it, and the window flickers when everything is
    configured again on each click. Options of a widget set through this helper must not be set
    with configure() elsewhere."""
    last = widget.__dict__.setdefault('_shown_options', {})
    changed = {k: v for k, v in options.items() if last.get(k, _UNSET) != v}
    if changed:
        widget.configure(**changed)
        last.update(changed)


# --- flags ------------------------------------------------------------------------------------------
# Windows has no flag emoji (its emoji font shows the letters) and Tk draws no colour emoji, so the
# versions of the game get small drawn flags: the EU's for the European version, the USA's for NA.
FLAG_SIZE = (20, 13)            # in window units; drawn at 4x so they stay sharp at 200 % and more
_flags = {}


def _draw_flag(region, w, h):
    from PIL import Image, ImageDraw
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if region == 'EU':
        d.rectangle((0, 0, w, h), fill=(0, 51, 153, 255))
        import math
        cx, cy, r, star = w / 2, h / 2, h / 3, h / 15
        for k in range(12):
            a = math.pi * 2 * k / 12
            x, y = cx + r * math.sin(a), cy - r * math.cos(a)
            points = []
            for j in range(10):      # a five-pointed star
                b = math.pi * j / 5
                rr = star if j % 2 == 0 else star * 0.45
                points.append((x + rr * math.sin(b), y - rr * math.cos(b)))
            d.polygon(points, fill=(255, 204, 0, 255))
    else:
        stripe = h / 13
        for k in range(13):
            d.rectangle((0, round(k * stripe), w, round((k + 1) * stripe)),
                        fill=(178, 34, 52, 255) if k % 2 == 0 else (255, 255, 255, 255))
        cw, ch = w * 0.4, stripe * 7
        d.rectangle((0, 0, cw, ch), fill=(60, 59, 110, 255))
        rows, dot = 5, max(1, h / 52)
        for row in range(rows):
            n = 6 if row % 2 == 0 else 5
            for k in range(n):
                x = cw * (k + (0.5 if row % 2 == 0 else 1.0)) / 6.0
                y = ch * (row + 0.5) / rows
                d.ellipse((x - dot, y - dot, x + dot, y + dot), fill=(255, 255, 255, 255))
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=max(2, h // 8), fill=255)
    img.putalpha(mask)
    return img


def flag_image(regions):
    """A CTkImage of the flag of a version of the game ('EU' or 'NA'), or of several side by side;
    None without Pillow (running from source without it: the chips then show text only)."""
    key = tuple(regions) if not isinstance(regions, str) else (regions,)
    if key not in _flags:
        try:
            from PIL import Image
        except ImportError:
            _flags[key] = None
            return None
        fw, fh = FLAG_SIZE
        gap = 4
        width = fw * len(key) + gap * (len(key) - 1)
        canvas = Image.new('RGBA', (width * 4, fh * 4), (0, 0, 0, 0))
        for k, region in enumerate(key):
            canvas.alpha_composite(_draw_flag(region, fw * 4, fh * 4), (k * (fw + gap) * 4, 0))
        _flags[key] = ctk.CTkImage(light_image=canvas, dark_image=canvas, size=(width, fh))
    return _flags[key]

CHIP_COLOURS = {            # kind -> (background, text)
    'made': (T.ACCENT_SOFT, '#7fd1ee'),
    'EU': (T.BORDER_STRONG, T.STRONG),          # the game's versions
    'NA': (T.GOLD_SOFT, T.GOLD),
    'bad': (T.RED_SOFT, T.RED),
    'muted': (T.CELL, T.MUTED),
}


def bind_click(widget, callback):
    """Make a whole row clickable: the frame and everything inside it."""
    widget.bind('<Button-1>', lambda _e: callback(), add='+')
    for child in widget.winfo_children():
        if not isinstance(child, (ctk.CTkSwitch, ctk.CTkButton, ctk.CTkEntry)):
            bind_click(child, callback)


class Card(ctk.CTkFrame):
    """A numbered step: badge, small upper-case title, then `self.body` for the content."""

    def __init__(self, master, number, title):
        super().__init__(master, fg_color=T.CARD, border_color=T.BORDER, border_width=1, corner_radius=T.RADIUS)
        head = ctk.CTkFrame(self, fg_color='transparent')
        head.pack(fill='x', padx=16, pady=(12, 6))
        ctk.CTkLabel(head, text=str(number), width=28, height=28, corner_radius=14, fg_color=T.ACCENT,
                     text_color='#ffffff', font=T.font(15, 'bold')).pack(side='left')
        ctk.CTkLabel(head, text=title.upper(), font=T.font(13, 'bold'), text_color=T.TEXT).pack(side='left', padx=(10, 0))
        self.aside = ctk.CTkLabel(head, text='', font=T.font(12), text_color=T.FAINT)
        self.aside.pack(side='right')
        self.body = ctk.CTkFrame(self, fg_color='transparent')
        self.body.pack(fill='both', expand=True, padx=16, pady=(0, 12))


class Chip(ctk.CTkLabel):
    def __init__(self, master, text, kind='muted', image=None):
        bg, fg = CHIP_COLOURS[kind]
        super().__init__(master, text=f" {text}" if image else text, image=image, compound='left', height=20,
                         corner_radius=10, fg_color=bg, text_color=fg, font=T.font(11, 'bold'), padx=8)


class Choice(ctk.CTkFrame):
    """A row of buttons of which one is chosen (like a segmented button, but each can carry a
    picture: the "Save for" flags). `options` [(value, text, image or None)]."""

    def __init__(self, master, options, command, height=36):
        super().__init__(master, fg_color=T.CELL, corner_radius=height // 2)
        self.command, self.value, self.buttons = command, None, {}
        for k, (value, text, image) in enumerate(options):
            b = ctk.CTkButton(self, text=text, image=image, compound='left', height=height - 6, width=0,
                              corner_radius=(height - 6) // 2, fg_color='transparent', hover_color=T.CELL_HOVER,
                              text_color=T.TEXT, text_color_disabled=T.FAINT, font=T.font(13, 'semibold'),
                              command=lambda v=value: self._pick(v))
            b.pack(side='left', padx=(3 if k == 0 else 0, 3), pady=3)
            self.buttons[value] = b

    def _pick(self, value):
        self.set(value)
        self.command(value)

    def set(self, value):
        self.value = value
        for v, b in self.buttons.items():
            on = v == value
            configure_if_changed(b, fg_color=T.ACCENT if on else 'transparent',
                                 hover_color=T.ACCENT_DEEP if on else T.CELL_HOVER,
                                 text_color='#ffffff' if on else T.TEXT)

    def enable(self, on):
        for b in self.buttons.values():
            configure_if_changed(b, state='normal' if on else 'disabled')


class PrimaryButton(ctk.CTkButton):
    def __init__(self, master, text, command, width=170, height=42):
        super().__init__(master, text=text, command=command, width=width, height=height, corner_radius=height // 2,
                         fg_color=T.ACCENT, hover_color=T.ACCENT_DEEP, text_color='#ffffff',
                         text_color_disabled='#7d8b93', font=T.font(15, 'bold'))

    def enable(self, on):
        configure_if_changed(self, state='normal' if on else 'disabled', fg_color=T.ACCENT if on else T.BORDER_STRONG)


class GhostButton(ctk.CTkButton):
    def __init__(self, master, text, command, width=0, height=32):
        super().__init__(master, text=text, command=command, width=width, height=height, corner_radius=height // 2,
                         fg_color='transparent', hover_color=T.CELL_HOVER, border_width=1,
                         border_color=T.BORDER_STRONG, text_color=T.TEXT, text_color_disabled=T.FAINT,
                         font=T.font(13, 'semibold'))


class RosterRow(ctk.CTkFrame):
    """One roster save in the list: a radio dot, its name, when it was saved and its folder, the
    version of the game it belongs to (EU / NA), and a chip."""

    def __init__(self, master, title, note, chip=None, problem=None, command=None, region=None):
        super().__init__(master, fg_color=T.CELL, corner_radius=10, border_width=1, border_color=T.CELL)
        self.usable = problem is None
        self.columnconfigure(1, weight=1)
        self.dot = ctk.CTkFrame(self, width=16, height=16, corner_radius=8, border_width=2,
                                border_color=T.BORDER_STRONG, fg_color=T.CELL)
        self.dot.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=8)
        colour = T.STRONG if self.usable else T.FAINT
        ctk.CTkLabel(self, text=title, font=T.font(15, 'semibold'), text_color=colour, anchor='w', height=20
                     ).grid(row=0, column=1, sticky='ew', pady=(5, 0))
        line = ctk.CTkFrame(self, fg_color='transparent')
        line.grid(row=1, column=1, sticky='ew', pady=(0, 6))
        if region:
            Chip(line, region, region if region in CHIP_COLOURS else 'muted',
                 image=flag_image(region)).pack(side='left', padx=(0, 6))
        ctk.CTkLabel(line, text=problem or note, font=T.font(12), text_color=T.RED if problem else T.MUTED,
                     anchor='w', justify='left', height=16, wraplength=300 if region else 330
                     ).pack(side='left', fill='x', expand=True)
        if chip:
            Chip(self, *chip).grid(row=0, column=2, rowspan=2, padx=(8, 12))
        if command and self.usable:
            bind_click(self, command)
            self.configure(cursor='hand2')

    def select(self, on):
        configure_if_changed(self, border_color=T.ACCENT if on else T.CELL, fg_color=T.ACCENT_SOFT if on else T.CELL)
        configure_if_changed(self.dot, fg_color=T.ACCENT if on else T.CELL,
                             border_color=T.ACCENT if on else T.BORDER_STRONG)


class SwitchRow(ctk.CTkFrame):
    """One thing that can be updated: title, where the data comes from, and an on/off switch."""

    def __init__(self, master, title, note, variable, command, extra=None):
        super().__init__(master, fg_color=T.CELL, corner_radius=10)
        self.columnconfigure(0, weight=1)
        rows = 3 if extra else 2
        ctk.CTkLabel(self, text=title, font=T.font(15, 'semibold'), text_color=T.STRONG, anchor='w', height=20
                     ).grid(row=0, column=0, sticky='ew', padx=(14, 6), pady=(5, 0))
        ctk.CTkLabel(self, text=note, font=T.font(12), text_color=T.MUTED, anchor='w', height=16
                     ).grid(row=1, column=0, sticky='ew', padx=(14, 6), pady=(0, 0 if extra else 6))
        if extra:       # a second, fainter line: e.g. the clubs the game has no slot for
            ctk.CTkLabel(self, text=extra, font=T.font(12), text_color=T.FAINT, anchor='w', height=16
                         ).grid(row=2, column=0, sticky='ew', padx=(14, 6), pady=(0, 6))
        self.switch = ctk.CTkSwitch(self, text='', variable=variable, command=command, width=40,
                                    progress_color=T.ACCENT, fg_color=T.BORDER_STRONG,
                                    button_color=T.TEXT, button_hover_color='#ffffff')
        self.switch.grid(row=0, column=2, rowspan=rows, padx=(0, 10))
        bind_click(self, self.switch.toggle)
        self.configure(cursor='hand2')

    def enable(self, on):
        configure_if_changed(self.switch, state='normal' if on else 'disabled')


class Banner(ctk.CTkFrame):
    """What happened, shown in the window instead of a pop-up: a title, buttons, what each part of
    the update did (one line each, in two columns when there are many), then a few plain lines."""

    COLUMNS_FROM = 7            # this many items or more go into two columns

    def __init__(self, master):
        super().__init__(master, corner_radius=T.RADIUS, border_width=1)
        self.columnconfigure(0, weight=1)
        self.title = ctk.CTkLabel(self, text='', font=T.font(16, 'bold'), anchor='w')
        self.title.grid(row=0, column=0, sticky='ew', padx=16, pady=(10, 0))
        self.buttons = ctk.CTkFrame(self, fg_color='transparent')
        self.buttons.grid(row=0, column=1, sticky='e', padx=(0, 12), pady=(10, 0))
        # the lines scroll when the screen is too short to show them all (App.show_banner: fit())
        self.items = ctk.CTkScrollableFrame(self, fg_color='transparent', height=40,
                                            scrollbar_button_color=T.BORDER_STRONG,
                                            scrollbar_button_hover_color=T.FAINT)
        self.items.grid(row=1, column=0, columnspan=2, sticky='ew', padx=(10, 6), pady=(6, 10))
        self.lines_height = 40          # the scrolling area's height (window units), set by fit()

    def show(self, good, title, lines, buttons=(), items=()):
        soft, line, strong = (T.GREEN_SOFT, T.GREEN_LINE, T.GREEN) if good else (T.RED_SOFT, T.RED_LINE, T.RED)
        self.configure(fg_color=soft, border_color=line)
        self.items.configure(fg_color=soft)
        self.title.configure(text=title, text_color=strong)
        for child in self.buttons.winfo_children() + self.items.winfo_children():
            child.destroy()
        for label, command in buttons:
            GhostButton(self.buttons, label, command, height=30).pack(side='left', padx=(6, 0))
        rows = self._items(list(items))
        # the plain lines scroll with the rest, so a short window can always show the whole box
        ctk.CTkLabel(self.items, text='\n'.join(lines), font=T.font(13), text_color=T.BODY, anchor='w', justify='left',
                     wraplength=920).grid(row=rows, column=0, columnspan=4, sticky='ew', padx=(6, 0), pady=(6, 0))

    def fit(self, limit=None):
        """Show all the lines, or at most `limit` pixels (window units) of them with a scroll bar."""
        self.update_idletasks()
        need = self.items.winfo_reqheight() / max(self.items._get_widget_scaling(), 0.1)
        height = need if limit is None else min(need, limit)
        self.items.configure(height=max(20, round(height)))
        self.lines_height = max(20, round(height))
        bar = getattr(self.items, '_scrollbar', None)
        if bar is not None:
            bar.configure(height=max(20, round(height)))       # its own default (200) would stretch the box
            if height < need:
                bar.grid()
            else:
                bar.grid_remove()

    def _items(self, items):
        """(title, text) pairs: the title in bold, its text beside it, one pair per line. Returns
        the number of grid rows used."""
        if not items:
            return 0
        columns = 2 if len(items) >= self.COLUMNS_FROM else 1
        per = (len(items) + columns - 1) // columns
        for c in range(columns):
            self.items.columnconfigure(2 * c + 1, weight=1, uniform='text')
        for k, (title, text) in enumerate(items):
            c, r = divmod(k, per)
            ctk.CTkLabel(self.items, text=title, font=T.font(13, 'bold'), text_color=T.STRONG, anchor='nw',
                         justify='left', height=18, wraplength=190
                         ).grid(row=r, column=2 * c, sticky='nw', padx=(0 if c == 0 else 18, 10), pady=1)
            ctk.CTkLabel(self.items, text=text, font=T.font(13), text_color=T.BODY, anchor='nw', justify='left',
                         height=18, wraplength=330 if columns == 2 else 760
                         ).grid(row=r, column=2 * c + 1, sticky='nw', pady=1)
        return per

    def dim(self, title):
        """While a new update runs: the last result stays (the window keeps its size), greyed out."""
        self.configure(fg_color=T.CARD, border_color=T.BORDER)
        self.items.configure(fg_color=T.CARD)
        self.title.configure(text=title, text_color=T.MUTED)
        for child in self.buttons.winfo_children():
            child.configure(state='disabled')
