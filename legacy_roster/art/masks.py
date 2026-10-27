"""A goalie's own picture on his mask (needs Pillow, imported when a picture is made).

The game paints a goalie's mask from one 3D texture per mask number: `rendering/goaliehelmet/goaliehelmet_0_<n>_cm.rpsgl`
(a 512 x 512 colour map laid out flat: the shell's front, sides and top, the cage's bars and the chin). Every goalie with
mask number n wears the same one, so a goalie with a picture of his own gets a mask number nobody wears
(`equipment.free_mask_ids`, set in edits.py) and his picture goes into that number's file as a loose file, the way the
jerseys do (`looks.py`, loose files proven in the game by `cli rendering-test`). The disc's file is the template: only its
colour map is replaced, so the file keeps its layout. Nothing of the game's is shipped. NOT played in the game yet.
"""
import hashlib

from . import rpsgl

MASK = 'rendering/goaliehelmet/goaliehelmet_0_{n}_cm.rpsgl'
RASTER = 'goaliehelmet_0_{n}_cm'
SOURCE = 'mask:'
DRAWING = '#1'              # raise it when the way the file is made changes: installed files are made again


def path_of(link):
    return link[5:] if str(link).startswith('file:') else str(link)


def own_picture(disc, n):
    """The game's own colour map of mask `n` as a Pillow picture (the template to paint on)."""
    raw = disc.render(MASK.format(n=n))
    if raw is None:
        raise rpsgl.RpsglError(f"the disc has no texture for mask {n}")
    return rpsgl.Rpsgl(raw).image(RASTER.format(n=n)).convert('RGB')


def mask_file(disc, n, picture):
    """The texture file of mask `n` with `picture` (a path or a Pillow picture) as its colour map."""
    from PIL import Image
    raw = disc.render(MASK.format(n=n))
    if raw is None:
        raise rpsgl.RpsglError(f"the disc has no texture for mask {n}")
    f = rpsgl.Rpsgl(raw)
    img = picture if hasattr(picture, 'convert') else Image.open(path_of(picture))
    f.replace(RASTER.format(n=n), img.convert('RGBA'))
    return f.build()


def _digest(n, path):
    try:
        with open(path_of(path), 'rb') as f:
            h = hashlib.sha1(f.read()).hexdigest()[:10]
    except OSError:
        h = 'missing'
    return f"{SOURCE}{DRAWING}:{n}:{h}"


def install_team_masks(rpcs3, title_id, pack, say=print, also=(), own=()):
    """The team masks of the pack `masks` (art/extrapack.py; index.json {"format": 1, "built": ..., "masks": {"<mask number>":
    "m/<mask number>.webp"}}): the pictures of the masks the teams' goalies share (numbers 2-29: the mask number is the
    team's art id), laid into the disc's own file of that number as loose files (RPCS3 closed). A number in `own` (a
    mask picture of the player's own) is left to it. A mask the pack no longer holds is put back as the game had it.
    Returns how many files were written."""
    from . import install, parts
    from .lab import Disc
    install.check(rpcs3, title_id)
    targets = [title_id] + [t for t in also if t != title_id]
    writer = install._Writer([rpcs3.game_folder(t) for t in targets])
    disc = Disc(rpcs3.game_disc(title_id))
    written, wanted = 0, set()
    try:
        for n, member in sorted(pack.index.get('masks', {}).items(), key=lambda kv: int(kv[0])):
            if int(n) in own:
                continue
            rel = MASK.format(n=n)
            source = f"{parts.TEAM_MASK_TAG}{DRAWING}:{n}:{pack.index.get('built', '')}"
            wanted.add(rel)
            if writer.current(tuple(rel.split('/')), source):
                continue
            try:
                data = mask_file(disc, n, pack.picture(member))
            except Exception as err:
                say(f"Team masks: mask {n} left out ({err})")
                wanted.discard(rel)
                continue
            writer.write(tuple(rel.split('/')), data, source)
            written += 1
            writer.save()
        for key in writer.stale(parts.TEAM_MASK_TAG, wanted):
            writer.drop(tuple(key.split('/')))
    finally:
        writer.save()
    say(f"Team masks: {written} masks made" if written else "Team masks: all masks are installed already")
    return written


def install_masks(rpcs3, title_id, masks, say=print, also=()):
    """Write the mask files of `masks` ({mask number: picture link}) into the game folder(s) (RPCS3 closed), with kept
    copies of anything replaced; a mask no goalie wears with a picture any more is put back as the game had it.
    Returns how many files were written."""
    from . import install
    from .lab import Disc
    install.check(rpcs3, title_id)
    targets = [title_id] + [t for t in also if t != title_id]
    writer = install._Writer([rpcs3.game_folder(t) for t in targets])
    disc = Disc(rpcs3.game_disc(title_id)) if masks else None
    written, wanted = 0, set()
    try:
        for n, link in sorted(masks.items()):
            rel = MASK.format(n=n)
            wanted.add(rel)
            source = _digest(n, link)
            if writer.current(tuple(rel.split('/')), source):
                say(f"Goalie masks: mask {n} is installed already")
                continue
            try:
                data = mask_file(disc, n, link)
            except Exception as err:
                say(f"Goalie masks: mask {n} left out ({err})")
                wanted.discard(rel)
                continue
            say(f"Goalie masks: making mask {n}")
            writer.write(tuple(rel.split('/')), data, source)
            written += 1
            writer.save()
        for key in writer.stale(SOURCE, wanted):
            writer.drop(tuple(key.split('/')))
    finally:
        writer.save()
    return written
