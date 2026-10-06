"""The in-game test of loose 3D textures (cli `rendering-test`): does the game take jerseys and the centre-ice logo
from loose files under `<game folder>/rendering/...` before the disc's?

The game asks for `/dev_hdd0/game/<TITLEID>/USRDIR/rendering/...` first, as it does for the pictures we already
replace under `fe/` (RPCS3 log), but no loose `rendering` file has ever been tried. This writes loud versions of
Utah's (slot 22, the former Arizona's) files: every home and away jersey of both styles with red and blue swapped
(a red Coyotes jersey comes out blue) and a magenta circle with the words UTAH TEST as the centre-ice logo. They are
installed and taken away again like every other picture of ours (art/install.py: kept copies, `installed.json`,
"Restore the game's own pictures"). Nothing else is touched.
"""
from . import install, rpsgl
from .lab import Disc

TEAM = 22                                   # Utah's art id (the Arizona files the game still has)
STYLES = (0, 1)                             # jersey styles; the game's default is 1 for the teams we looked at
VARIANTS = (0, 1, 3, 4)                     # the files the disc has for Utah (3 and 4 are home and away)
JERSEY = "rendering/jersey/texlib_{style}_{team}_{variant}.rpsgl"
CENTRE = "rendering/icesurface/centerlogo_{team}_cm.rpsgl"
SOURCE = "rendering-test:1"


def loud_jersey(raw, style, variant):
    """The jersey file with red and blue swapped in its colour map (everything else as it is)."""
    from PIL import Image
    f = rpsgl.Rpsgl(raw)
    name = f"jersey_{style}_{TEAM}_{variant}_cm"
    r, g, b, a = f.image(name).split()
    f.replace(name, Image.merge('RGBA', (b, g, r, a)))
    return f.build()


def loud_centre(raw):
    """The centre-ice logo file with a magenta circle and 'UTAH TEST' on it."""
    from PIL import Image, ImageDraw, ImageFont
    f = rpsgl.Rpsgl(raw)
    name = f"centerlogo_{TEAM}_cm"
    img = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((30, 30, 994, 994), fill=(255, 0, 255, 255))
    draw.ellipse((120, 120, 904, 904), fill=(255, 255, 0, 255))
    try:
        font = ImageFont.load_default(size=170)
    except TypeError:                                  # Pillow before 10.1: the small bitmap font
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), "UTAH", font=font)
    draw.text(((1024 - (box[2] - box[0])) / 2 - box[0], 330 - box[1]), "UTAH", font=font, fill=(0, 0, 0, 255))
    box = draw.textbbox((0, 0), "TEST", font=font)
    draw.text(((1024 - (box[2] - box[0])) / 2 - box[0], 530 - box[1]), "TEST", font=font, fill=(0, 0, 0, 255))
    f.replace(name, img)
    return f.build()


def rendering_test(rpcs3, title_id, say=print):
    """Install the loud files for `title_id`'s game (RPCS3 closed). Returns how many files were written."""
    install.check(rpcs3, title_id)
    disc = Disc(rpcs3.game_disc(title_id))
    writer = install._Writer([rpcs3.game_folder(title_id)])
    files = {}
    for style in STYLES:
        for variant in VARIANTS:
            inner = JERSEY.format(style=style, team=TEAM, variant=variant)
            raw = disc.render(inner)
            if raw is not None:
                files[inner] = loud_jersey(raw, style, variant)
    inner = CENTRE.format(team=TEAM)
    raw = disc.render(inner)
    if raw is not None:
        files[inner] = loud_centre(raw)
    if not files:
        raise install.ArtError("The game's 3D textures were not found on your disc, so nothing was written.")
    try:
        for inner, data in sorted(files.items()):
            writer.write(tuple(inner.split('/')), data, SOURCE)
            say(f"Wrote {inner} ({len(data) / 1e6:.1f} MB)")
    finally:
        writer.save()
    return len(files)
