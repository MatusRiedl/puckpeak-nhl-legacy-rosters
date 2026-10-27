"""The NHL arenas' newer pictures (0.76.0, the "Arenas" switch).

The game draws an arena from one 3D file, `rendering/stadium/stadium_<art>_container_0.rpsgl` (about 10 MB, the arena's
pictures after a header). A newer version of an arena changes about 1 MB of it, in place: the file keeps its size and
layout. The pack (`arenas`, art/extrapack.py) holds only those bytes for each arena:

    index.json  {"format": 1, "built": ..., "arenas": {"<art id>": {"base": sha1 of the game's file unpacked,
                 "id": digest of the runs, "runs": [[offset, length], ...], "file": "a/<art id>.bin"}}}
    a/<art id>.bin  the runs' bytes one after the other

The player's own disc has the file: it is unpacked, the runs are laid over it, and it is packed again as a loose file.
A file of another game version (its sha1 differs from "base") is left as it is, and the List of changes says so.
Nothing of the game is shipped. NOT played in the game yet (lab check first, docs/plans/i-got-access-to-structured-bunny.md).
"""
import hashlib

from . import parts, rpsgl

STADIUM = 'rendering/stadium/stadium_{a}_container_0.rpsgl'
DRAWING = '#1'              # raise it when the way the file is made changes: installed files are made again


def arena_file(disc, art, entry, blob):
    """The arena file of `art` with the pack's bytes laid over the disc's own (bytes). RpsglError when the disc has none
    or has another version of it."""
    raw = disc.render(STADIUM.format(a=art))
    if raw is None:
        raise rpsgl.RpsglError(f"the disc has no arena file for {art}")
    data = bytearray(rpsgl.unpack(raw))
    if hashlib.sha1(data).hexdigest() != entry['base']:
        raise rpsgl.RpsglError("this copy of the game has another version of the arena file")
    pos = 0
    for offset, size in entry['runs']:
        if offset + size > len(data) or pos + size > len(blob):
            raise rpsgl.RpsglError("the pack does not fit the arena file")
        data[offset:offset + size] = blob[pos:pos + size]
        pos += size
    return rpsgl.pack(bytes(data))


def install_arenas(rpcs3, title_id, pack, say=print, also=(), skipped=None):
    """Write the arenas of `pack` as loose files into the game folder(s) (RPCS3 closed), with kept copies of anything
    replaced; an arena the pack no longer holds is put back as the game had it. `skipped` (a list) gets (art id, why).
    Returns how many files were written."""
    from . import install
    from .lab import Disc
    install.check(rpcs3, title_id)
    targets = [title_id] + [t for t in also if t != title_id]
    writer = install._Writer([rpcs3.game_folder(t) for t in targets])
    disc = Disc(rpcs3.game_disc(title_id))
    written, wanted = 0, set()
    try:
        for art, entry in sorted(pack.index.get('arenas', {}).items(), key=lambda kv: int(kv[0])):
            rel = STADIUM.format(a=art)
            source = f"{parts.ARENA_TAG}{DRAWING}:{art}:{entry['id']}"
            wanted.add(rel)
            if writer.current(tuple(rel.split('/')), source):
                continue
            try:
                data = arena_file(disc, art, entry, pack.read(entry['file']))
            except (rpsgl.RpsglError, KeyError, ValueError) as err:
                say(f"Arenas: arena {art} left as it is ({err})")
                wanted.discard(rel)
                if skipped is not None:
                    skipped.append((art, str(err)))
                continue
            writer.write(tuple(rel.split('/')), data, source)
            written += 1
            writer.save()
        for key in writer.stale(parts.ARENA_TAG, wanted):
            writer.drop(tuple(key.split('/')))
    finally:
        writer.save()
    say(f"Arenas: {written} arenas made" if written else "Arenas: all arenas are installed already")
    return written
