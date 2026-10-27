"""Bright ice (0.76.0, the "Bright ice" switch): brighter faceoff circles and a white-backed centre circle.

Both are pictures that go into the player's own disc file, which keeps its size and layout (art/rpsgl.py `replace`):

    rendering/icesurface/ice_hotspot_0_<n>_cm.rpsgl   the faceoff circles (512 x 512 DXT5; the NHL rink's)
    rendering/icesurface/centerlogo_<art>_cm.rpsgl    the centre circle (1024 x 1024 DXT5), white behind the logo

Not taken: the community's `ice_hotspot_1_*` (another height than the game's, 512 x 512 for 512 x 256) and `ice_lines`
(2048 x 4096 for 1024 x 2048): a picture of another size cannot go into the game's file without a new header.

The centre circle of a team whose look this season's jerseys and centre ice (`looks`) installs is left to that part:
the player's choices and the look pack win. The pack (`ice`): index.json {"format": 1, "built": ..., "hotspots":
{"<file name>": "h/<name>.webp"}, "centres": {"<art id>": "c/<art id>.webp"}} (lossless pictures). NOT played in the game yet.
"""
from . import parts, rpsgl

HOTSPOT = 'rendering/icesurface/{n}.rpsgl'
CENTRE = 'rendering/icesurface/centerlogo_{a}_cm.rpsgl'
DRAWING = '#1'


def _file(disc, inner, raster, picture):
    raw = disc.render(inner)
    if raw is None:
        raise rpsgl.RpsglError(f"the disc has no {inner}")
    f = rpsgl.Rpsgl(raw)
    f.replace(raster, picture)
    return f.build()


def install_bright(rpcs3, title_id, pack, say=print, also=()):
    """Write the faceoff circles and centre circles of `pack` as loose files (RPCS3 closed). Returns how many files were
    written."""
    from . import install
    from .lab import Disc
    install.check(rpcs3, title_id)
    targets = [title_id] + [t for t in also if t != title_id]
    writer = install._Writer([rpcs3.game_folder(t) for t in targets])
    disc = Disc(rpcs3.game_disc(title_id))
    written, wanted = 0, set()
    index = pack.index
    work = [(HOTSPOT.format(n=n), n, member) for n, member in sorted(index.get('hotspots', {}).items())]
    work += [(CENTRE.format(a=a), f"centerlogo_{a}_cm", member)
             for a, member in sorted(index.get('centres', {}).items(), key=lambda kv: int(kv[0]))]
    try:
        for inner, raster, member in work:
            rel = tuple(inner.split('/'))
            if any(str(e.get('source', '')).startswith('looks:') for files in writer.manifest['games'].values()
                   for k, e in files.items() if k == inner):
                continue                    # this season's centre ice is installed here: it wins
            source = f"{parts.ICE_TAG}{DRAWING}:{raster}:{index.get('built', '')}"
            wanted.add(inner)
            if writer.current(rel, source):
                continue
            try:
                data = _file(disc, inner, raster, pack.picture(member))
            except (rpsgl.RpsglError, KeyError, ValueError) as err:
                say(f"Bright ice: {raster} left as it is ({err})")
                wanted.discard(inner)
                continue
            writer.write(rel, data, source)
            written += 1
        for key in writer.stale(parts.ICE_TAG, wanted):
            writer.drop(tuple(key.split('/')))
    finally:
        writer.save()
    say(f"Bright ice: {written} files made" if written else "Bright ice: everything is installed already")
    return written
