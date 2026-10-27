"""The parts of "pictures" a player switches on one by one (0.76.0; before, one switch did all of it).

    names       the game's text files (team names, Puck Peak texts) and the main menu: made from the player's disc, no download
    photos      players' photos, club logos, crests, the player's own goalie masks (pack `photos`)
    looks       this season's jerseys and centre ice (pack `looks`)
    arenas      the NHL arenas' newer pictures (pack `arenas`)
    bright_ice  centre circles on solid white ice (pack `ice`)
    team_masks  the goalie masks of the teams (pack `masks`)

The player's own pictures (Roster editor) go in whatever is switched on. Every part writes its files with a source tag
of its own in the installed-files list (art/install.py `_Writer`), so one part's clean-up never touches another's files
and Restore can undo one part.
"""
NAMES, PHOTOS, LOOKS, ARENAS, BRIGHT_ICE, TEAM_MASKS = 'names', 'photos', 'looks', 'arenas', 'bright_ice', 'team_masks'
ALL = (NAMES, PHOTOS, LOOKS, ARENAS, BRIGHT_ICE, TEAM_MASKS)
LEGACY = frozenset({NAMES, PHOTOS, LOOKS})      # what the one switch "Photos, logos and team names" always did
PACK_OF = {PHOTOS: 'photos', LOOKS: 'looks', ARENAS: 'arenas', BRIGHT_ICE: 'ice', TEAM_MASKS: 'masks'}

# the tag a part's files carry in the installed-files list (`source` starts with it); photos and logos carry their link
ARENA_TAG, ICE_TAG, TEAM_MASK_TAG = 'arenas:', 'ice:', 'teammask:'
TAGS = {NAMES: ('names:', 'menus:'), LOOKS: ('looks:',), ARENAS: (ARENA_TAG,), BRIGHT_ICE: (ICE_TAG,),
        TEAM_MASKS: (TEAM_MASK_TAG,)}
OTHER_TAGS = tuple(tag for tags in TAGS.values() for tag in tags) + ('crests:', 'mask:')


def packs_for(parts):
    """The packs (names in packs.NAMES) the parts need, in the order of ALL."""
    return [PACK_OF[p] for p in ALL if p in parts and p in PACK_OF]


def belongs(source, part):
    """Does an installed file written from `source` belong to `part`? Photos and logos are what no other tag claims
    (crests and the player's own masks go with them)."""
    source = str(source or '')
    if part == PHOTOS:
        return not source.startswith(tuple(t for t in OTHER_TAGS if t not in ('crests:', 'mask:')))
    return source.startswith(TAGS[part])
