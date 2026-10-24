"""Coachella Valley and Henderson with art ids of their own, 900 and 901 (0.50.4; lab round 48, docs/notes/lab-round-48.md).

On a roster for the patched game the two clubs are AHL clubs (gamepatch.league_fit) with art ids like any club's
(gamepatch.art_fit: the created-team flag off, jersey rows of a donor club). The game then looks for their files under those
ids, and the disc has none. This module makes them from a donor club's files on the player's own disc: Charlotte's (162) for
Coachella Valley, Utica's (141) for Henderson (layout.CLUB_DONOR). The donor's file is read, its art number in the container
header changed to the new one (same digit count, so nothing moves) and handed to the same maker that paints Utah, Seattle and
Vegas (looks.Maker), which puts the club's colours and crest on it. `AliasDisc` does the reading; `extra_files` copies what
the maker does not paint (name and number sheets, banner, puck, goalie helmet). Standard library only.
"""
import re

from .. import layout as L

DRAWING = '#1'              # a change in how these files are made redraws them once (looks.look_digest)
ARTS = tuple(L.CLUB_ART.values())
NAME = "rendering/jersey/name_1_{a}_{v}_cm.rpsgl"
EXTRA = ("rendering/banner/banner_{a}_cm.rpsgl", "rendering/goaliehelmet/goaliehelmet_0_{a}_cm.rpsgl",
         "rendering/puck/puck_{a}_cm.rpsgl")
DONOR_OF = {art: L.CLUB_DONOR[slot] for slot, art in L.CLUB_ART.items()}       # art -> (donor art id, its variants)


def number(art):
    """A regular expression for the whole number `art` inside a path or a name (not part of a longer number)."""
    return rf'(?<!\d){art}(?!\d)'


def donor_path(inner):
    """(art id, donor art id, donor path) for a path of a file of art 900 / 901, or None for any other path."""
    for art, (donor, _variants) in DONOR_OF.items():
        if re.search(number(art), inner):
            return art, donor, re.sub(number(art), str(donor), inner)
    return None


def renamed(raw, old, new):
    """The texture file `raw` (bytes) with the whole number `old` in its header (the raster names) changed to `new`: the
    same digit count, so the header keeps its layout. Returns the file's bytes."""
    from . import rpsgl
    if len(str(old)) != len(str(new)):
        raise ValueError(f"{old} -> {new}: the numbers differ in length")
    f = rpsgl.Rpsgl(raw)
    data = bytearray(f.data)
    data[:f.header] = re.sub(number(old).encode(), str(new).encode(), bytes(data[:f.header]))
    return rpsgl.Rpsgl(rpsgl.pack(bytes(data)) if f.packed else bytes(data)).build()


class AliasDisc:
    """The player's disc (art/lab.Disc), with the files of art 900 / 901 read from the donor club's: a 3D texture with its
    art number changed, a menu picture as it is. Every other file is the disc's own."""

    def __init__(self, disc):
        self.disc = disc.disc if isinstance(disc, AliasDisc) else disc

    def __getattr__(self, name):
        return getattr(self.disc, name)

    def has(self, inner):
        d = donor_path(inner)
        return self.disc.has(d[2] if d else inner)

    def find(self, inner):
        d = donor_path(inner)
        return self.disc.find(d[2] if d else inner)

    def render(self, inner):
        d = donor_path(inner)
        if d is None:
            return self.disc.render(inner)
        raw = self.disc.render(d[2])
        return None if raw is None else renamed(raw, d[1], d[0])


def extra_paths(art):
    """The files of art `art` the maker does not paint: the name and number sheets, the banner, the puck and the goalie
    helmet."""
    if art not in DONOR_OF:
        return []
    return [NAME.format(a=art, v=v) for v in DONOR_OF[art][1]] + [t.format(a=art) for t in EXTRA]


def extra_files(disc, art):
    """{path inside USRDIR: file} of extra_paths(art), copied from the donor club's (`disc`: an AliasDisc)."""
    out = {}
    for path in extra_paths(art):
        raw = disc.render(path)
        if raw is not None:
            out[path] = raw
    return out


def slots(R):
    """[slot] of the teams of roster `R` that hold art 900 / 901 (a roster for the patched game)."""
    return [slot for slot, art in sorted(L.CLUB_ART.items()) if slot < R.T.cur_rec and R.T.get(slot, 'artid') == art]


def rekey_logos(R, logos):
    """The menu logos `logos` ({team art id: (link, colours)}, portraits.plan: made from the roster as built, with the
    create-a-team art ids) under the art ids the patched roster `R` gives Coachella Valley and Henderson."""
    out = dict(logos)
    for slot in slots(R):
        old = L.OWN_ART[slot]
        if old in out:
            out[L.CLUB_ART[slot]] = out.pop(old)
    return out
