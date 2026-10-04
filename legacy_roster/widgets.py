"""The pieces the window is built from: cards, chips, pill buttons, list rows, the result banner."""
import customtkinter as ctk

from . import theme as T

CHIP_COLOURS = {            # kind -> (background, text)
    'new': (T.GOLD_SOFT, T.GOLD),
    'made': (T.ACCENT_SOFT, '#7fd1ee'),
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
        ctk.CTkLabel(head, text=str(number), width=24, height=24, corner_radius=12, fg_color=T.ACCENT,
                     text_color='#ffffff', font=T.font(13, 'bold')).pack(side='left')
        ctk.CTkLabel(head, text=title.upper(), font=T.font(12, 'bold'), text_color=T.MUTED).pack(side='left', padx=(10, 0))
        self.aside = ctk.CTkLabel(head, text='', font=T.font(12), text_color=T.FAINT)
        self.aside.pack(side='right')
        self.body = ctk.CTkFrame(self, fg_color='transparent')
        self.body.pack(fill='both', expand=True, padx=16, pady=(0, 12))


class Chip(ctk.CTkLabel):
    def __init__(self, master, text, kind='muted'):
        bg, fg = CHIP_COLOURS[kind]
        super().__init__(master, text=text, height=20, corner_radius=10, fg_color=bg, text_color=fg,
                         font=T.font(11, 'bold'), padx=8)


class PrimaryButton(ctk.CTkButton):
    def __init__(self, master, text, command, width=170, height=42):
        super().__init__(master, text=text, command=command, width=width, height=height, corner_radius=height // 2,
                         fg_color=T.ACCENT, hover_color=T.ACCENT_DEEP, text_color='#ffffff',
                         text_color_disabled='#7d8b93', font=T.font(15, 'bold'))

    def enable(self, on):
        self.configure(state='normal' if on else 'disabled', fg_color=T.ACCENT if on else T.BORDER_STRONG)


class GhostButton(ctk.CTkButton):
    def __init__(self, master, text, command, width=0, height=32):
        super().__init__(master, text=text, command=command, width=width, height=height, corner_radius=height // 2,
                         fg_color='transparent', hover_color=T.CELL_HOVER, border_width=1,
                         border_color=T.BORDER_STRONG, text_color=T.TEXT, text_color_disabled=T.FAINT,
                         font=T.font(13, 'semibold'))


class RosterRow(ctk.CTkFrame):
    """One roster save in the list: a radio dot, its name, when it was saved, and a chip."""

    def __init__(self, master, title, note, chip=None, problem=None, command=None):
        super().__init__(master, fg_color=T.CELL, corner_radius=10, border_width=1, border_color=T.CELL)
        self.usable = problem is None
        self.columnconfigure(1, weight=1)
        self.dot = ctk.CTkFrame(self, width=16, height=16, corner_radius=8, border_width=2,
                                border_color=T.BORDER_STRONG, fg_color=T.CELL)
        self.dot.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=8)
        colour = T.STRONG if self.usable else T.FAINT
        ctk.CTkLabel(self, text=title, font=T.font(15, 'semibold'), text_color=colour, anchor='w', height=20
                     ).grid(row=0, column=1, sticky='ew', pady=(5, 0))
        ctk.CTkLabel(self, text=problem or note, font=T.font(12), text_color=T.RED if problem else T.MUTED,
                     anchor='w', justify='left', height=16, wraplength=330
                     ).grid(row=1, column=1, sticky='ew', pady=(0, 6))
        if chip:
            Chip(self, *chip).grid(row=0, column=2, rowspan=2, padx=(8, 12))
        if command and self.usable:
            bind_click(self, command)
            self.configure(cursor='hand2')

    def select(self, on):
        self.configure(border_color=T.ACCENT if on else T.CELL, fg_color=T.ACCENT_SOFT if on else T.CELL)
        self.dot.configure(fg_color=T.ACCENT if on else T.CELL, border_color=T.ACCENT if on else T.BORDER_STRONG)


class SwitchRow(ctk.CTkFrame):
    """One thing that can be updated: title, where the data comes from, and an on/off switch."""

    def __init__(self, master, title, note, variable, command, new=False, extra=None):
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
        if new:
            Chip(self, "NEW", 'new').grid(row=0, column=1, rowspan=rows, padx=(0, 8))
        self.switch = ctk.CTkSwitch(self, text='', variable=variable, command=command, width=40,
                                    progress_color=T.ACCENT, fg_color=T.BORDER_STRONG,
                                    button_color=T.TEXT, button_hover_color='#ffffff')
        self.switch.grid(row=0, column=2, rowspan=rows, padx=(0, 10))
        bind_click(self, self.switch.toggle)
        self.configure(cursor='hand2')

    def enable(self, on):
        self.switch.configure(state='normal' if on else 'disabled')


class Banner(ctk.CTkFrame):
    """What happened, shown in the window instead of a pop-up."""

    def __init__(self, master):
        super().__init__(master, corner_radius=T.RADIUS, border_width=1)
        self.columnconfigure(0, weight=1)
        self.title = ctk.CTkLabel(self, text='', font=T.font(16, 'bold'), anchor='w')
        self.title.grid(row=0, column=0, sticky='ew', padx=16, pady=(10, 0))
        self.buttons = ctk.CTkFrame(self, fg_color='transparent')
        self.buttons.grid(row=0, column=1, sticky='e', padx=(0, 12), pady=(10, 0))
        self.text = ctk.CTkLabel(self, text='', font=T.font(13), text_color=T.BODY, anchor='w', justify='left',
                                 wraplength=930)
        self.text.grid(row=1, column=0, columnspan=2, sticky='ew', padx=16, pady=(4, 12))

    def show(self, good, title, lines, buttons=()):
        soft, line, strong = (T.GREEN_SOFT, T.GREEN_LINE, T.GREEN) if good else (T.RED_SOFT, T.RED_LINE, T.RED)
        self.configure(fg_color=soft, border_color=line)
        self.title.configure(text=title, text_color=strong)
        self.text.configure(text='\n'.join(lines))
        for child in self.buttons.winfo_children():
            child.destroy()
        for label, command in buttons:
            GhostButton(self.buttons, label, command, height=30).pack(side='left', padx=(6, 0))
