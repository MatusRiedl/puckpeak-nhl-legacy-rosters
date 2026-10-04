"""The Puck Peak look: colours, fonts and images for the window.

Puck Peak's page is #0b1318; its cards are that colour with 3% white on top and a 10% white
border, 12-14 px corners, pill buttons, Source Sans, and #2596be as the accent. Tk has no
transparency, so the blended colours are written out here.
"""
import os
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

BG = '#0b1318'              # page
CARD = '#121a1f'            # page + 3% white
BORDER = '#232b2f'          # page + 10% white
BORDER_STRONG = '#32393d'   # page + 16% white
CELL = '#171f24'            # page + 5% white: rows and fields inside a card
CELL_HOVER = '#1d262c'
TEXT = '#e2f1f8'
STRONG = '#f8fafc'
BODY = '#cbd5e1'
MUTED = '#94a3b8'
FAINT = '#64748b'
ACCENT = '#2596be'
ACCENT_DEEP = '#2b71c7'
ACCENT_SOFT = '#0f2833'     # accent at 16% on the page
ACCENT_LINE = '#174e63'
GOLD = '#fde68a'
GOLD_SOFT = '#282918'
GOLD_LINE = '#5c5217'
GREEN = '#4ade80'
GREEN_SOFT = '#0f2f23'
GREEN_LINE = '#135130'
RED = '#f87171'
RED_SOFT = '#2c2024'
RED_LINE = '#5a2a2e'

RADIUS = 14
_FAMILY = {'normal': 'Segoe UI', 'semibold': 'Segoe UI Semibold', 'bold': 'Segoe UI'}
_images = []                # Tk drops images nobody holds on to


def load_fonts(root):
    """Make Puck Peak's font available to this program; Segoe UI stays in place if that fails."""
    folder = os.path.join(DATA, 'fonts')
    try:
        loaded = [ctk.FontManager.load_font(os.path.join(folder, f)) for f in sorted(os.listdir(folder))
                  if f.lower().endswith('.ttf')]
    except OSError:
        loaded = []
    if loaded and all(loaded):
        for key, family in (('normal', 'Source Sans 3'), ('bold', 'Source Sans 3'), ('semibold', 'Source Sans 3 Semibold')):
            if tkfont.Font(root=root, family=family, size=12).actual('family').lower() == family.lower():
                _FAMILY[key] = family


def font(size, weight='normal', underline=False):
    return ctk.CTkFont(family=_FAMILY[weight], size=size, weight='bold' if weight == 'bold' else 'normal',
                       underline=underline)


_measures = {}


def text_width(widget, text, size, weight='normal'):
    """How wide `text` shows in font(size, weight), in the window's own (scaled) units."""
    scale = scaling(widget)
    key = (_FAMILY[weight], round(size * scale), weight)
    if key not in _measures:        # same pixel size as customtkinter gives the label
        _measures[key] = tkfont.Font(root=widget, family=key[0], size=-key[1],
                                     weight='bold' if weight == 'bold' else 'normal')
    return _measures[key].measure(text) / scale


def scaling(widget):
    return ctk.ScalingTracker.get_window_scaling(widget.winfo_toplevel())


def screen_height(widget):
    """Height of the screen in the window's own (scaled) units."""
    try:
        import ctypes
        pixels = ctypes.windll.user32.GetSystemMetrics(1)       # real pixels: the program is DPI aware
    except (AttributeError, OSError):
        pixels = widget.winfo_screenheight()
    return int(pixels / scaling(widget))


NEEDED = ('logo_100.png', 'logo_125.png', 'logo_150.png', 'logo_200.png', 'datapack.json.gz')


def missing_files():
    """The program's own files that are not there. The exe unpacks them into Windows' temporary
    folder at every start; an antivirus or a cleaning program can remove them from there."""
    return [name for name in NEEDED if not os.path.exists(os.path.join(DATA, name))]


def logo(master):
    """The Puck Peak header logo in the size that suits the screen's scaling."""
    wanted = scaling(master) * 100
    size = next((s for s in (100, 125, 150, 200) if s >= wanted - 1), 200)
    img = tk.PhotoImage(master=master, file=os.path.join(DATA, f"logo_{size}.png"))
    _images.append(img)
    return img


def glow_line(master, width, height=2):
    """Puck Peak's header rule: the accent colour fading out towards both ends."""
    width = max(2, int(width * scaling(master)))
    height = max(1, round(height * scaling(master)))
    a = tuple(int(BG[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(ACCENT[i:i + 2], 16) for i in (1, 3, 5))
    row = []
    for x in range(width):
        t = 1 - abs(2 * x / (width - 1) - 1)
        t = t * t * (3 - 2 * t)
        row.append('#%02x%02x%02x' % tuple(round(a[k] + (b[k] - a[k]) * t) for k in range(3)))
    img = tk.PhotoImage(master=master, width=width, height=height)
    line = '{' + ' '.join(row) + '}'
    img.put(' '.join([line] * height))
    _images.append(img)
    return img
