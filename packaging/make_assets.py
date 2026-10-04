"""Build the window's images from the Puck Peak brand assets (legacy_roster/data/).

    .venv\\Scripts\\python packaging\\make_assets.py ["<puck-peak>\\assets"]

  logo_<scale>.png   the header logo (Puck Peak's BB.png) for 100 / 125 / 150 / 200 % screens
  app.ico            the Puck Peak puck (drawn from favicon.svg's shapes), 16 to 256 px

Needs Pillow; run when the brand assets change. The results are committed, so building the
program does not need the Puck Peak project.
"""
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'legacy_roster', 'data')
DEFAULT_ASSETS = os.path.join(os.path.expanduser('~'), 'Documents', 'puck-peak', 'assets')
PAGE = (0x0b, 0x13, 0x18)          # the window background the logo sits on
LOGO_HEIGHT = 46                   # at 100 % scaling
SCALES = (100, 125, 150, 200)


def logos(assets):
    src = Image.open(os.path.join(assets, 'BB.png')).convert('RGBA')
    box = src.getbbox()                                  # trim transparent margins
    src = src.crop(box) if box else src
    for scale in SCALES:
        h = round(LOGO_HEIGHT * scale / 100)
        w = round(src.width * h / src.height)
        img = src.resize((w, h), Image.LANCZOS)
        flat = Image.new('RGB', img.size, PAGE)          # Tk blends alpha poorly: bake the background in
        flat.paste(img, mask=img.split()[3])
        flat.save(os.path.join(OUT, f"logo_{scale}.png"), optimize=True)
        print(f"logo_{scale}.png  {w}x{h}")


def icon():
    """favicon.svg redrawn: puck, peak, rising arrow (the SVG is a 256 unit square)."""
    k = 4                                               # draw large, shrink for smooth edges
    img = Image.new('RGBA', (256 * k, 256 * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p = lambda *xy: [(x * k, y * k) for x, y in zip(xy[0::2], xy[1::2])]
    # puck: side wall, bottom rim, top face
    d.rectangle(p(28, 180, 228, 215), fill='#1c2024')
    d.ellipse(p(28, 185, 228, 245), fill='#1c2024')
    d.ellipse(p(28, 150, 228, 210), fill='#323842')
    # peak and its lit face
    d.polygon(p(45, 180, 105, 70, 140, 125, 180, 45, 215, 180), fill='#003459')
    d.polygon(p(45, 180, 105, 70, 140, 125, 110, 180), fill='#00a8e8')
    # rising arrow: quadratic curve from (25,140) via (128,240) to (205,75), then the head
    curve = []
    for i in range(61):
        t = i / 60
        x = (1 - t) ** 2 * 25 + 2 * (1 - t) * t * 128 + t ** 2 * 205
        y = (1 - t) ** 2 * 140 + 2 * (1 - t) * t * 240 + t ** 2 * 75
        curve.append((x * k, y * k))
    d.line(curve, fill='#ffffff', width=20 * k, joint='curve')
    r = 10 * k
    for x, y in (curve[0], curve[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill='#ffffff')
    d.polygon(p(180, 60, 230, 35, 215, 90), fill='#ffffff')
    # a dark plate behind it: the white arrow has to show on a light taskbar too
    size = 256 * k
    plate = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(plate).rounded_rectangle((4 * k, 4 * k, size - 4 * k, size - 4 * k), radius=52 * k,
                                            fill=PAGE + (255,), outline=(0x25, 0x96, 0xbe, 255), width=5 * k)
    art = img.resize((round(size * 0.8), round(size * 0.8)), Image.LANCZOS)
    plate.alpha_composite(art, ((size - art.width) // 2, (size - art.height) // 2 - 6 * k))
    img = plate.resize((256, 256), Image.LANCZOS)
    img.save(os.path.join(OUT, 'app.ico'), sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)])
    img.save(os.path.join(OUT, 'app_256.png'))
    print("app.ico, app_256.png")


if __name__ == '__main__':
    assets = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ASSETS
    os.makedirs(OUT, exist_ok=True)
    logos(assets)
    icon()
