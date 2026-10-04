"""Command-line front end.

    list    --rpcs3 <rpcs3.exe>                       roster saves found there (and the game's own roster)
    update  --rpcs3 <rpcs3.exe> [--source <save>]     build and save an updated roster
            [--source disc[:EU|:NA]]                  start from the game's own roster on your disc
            [--leagues nhl,ratings,national,liiga,... | all] [--name "<roster name>"] [--dry-run] [--offline]
            [--for EU|NA|both]                        which version(s) of the game to save it for
            [--photos]                                also install current photos and logos (RPCS3 closed)
            [--edits]                                 apply your edits from the window's Roster editor
    photos remove                                     take the photos and logos away again
    stock-test --rpcs3 <rpcs3.exe> [--version EU|NA]  the in-game check of the game's own roster (two LAB rosters)
    export  --rpcs3 <rpcs3.exe> [--source <save>] --out <folder>    every table as CSV, real names

--savedata <folder> can be given instead of --rpcs3 when the saves are not in an RPCS3 folder.
"""
import argparse
import sys

from . import APP_NAME, __version__, datasource, edits, layout, pipeline, savedata
from .builder import Data
from .roster import Roster
from .tdb import RosterFile


def _folder(args):
    """(savedata folder, roster folder pointed at or None) from --rpcs3 or --savedata."""
    if args.rpcs3:
        return savedata.find_rpcs3(args.rpcs3).savedata, None
    return savedata.find_savedata(args.savedata)


def _disc_slot(args, wanted='disc'):
    """The game's own roster on the disc RPCS3 has (`wanted`: 'disc', 'disc:EU' or 'disc:NA')."""
    if not args.rpcs3:
        sys.exit("the game's own roster needs --rpcs3 <rpcs3.exe>: the disc is found from RPCS3's games list")
    found = savedata.find_rpcs3(args.rpcs3)
    region = wanted.partition(':')[2].upper()
    slots = [s for s in found.disc_slots() if not region or s.region == region]
    if not slots:
        sys.exit("RPCS3 does not list " + (f"the {region} version of " if region else "") + "the game, so its own "
                 "roster cannot be read. Start the game once from RPCS3's game list.")
    return found.savedata, slots[0]


def _source(args):
    wanted = getattr(args, 'source', None)
    if wanted and wanted.lower().startswith('disc'):
        return _disc_slot(args, wanted.lower())
    folder, preselected = _folder(args)
    slots = savedata.list_rosters(folder)
    if not slots and not wanted:
        return _disc_slot(args)             # no roster saved yet: the game's own roster
    wanted = wanted or preselected
    if wanted:
        slot = next((s for s in slots if s.folder == wanted or s.name == wanted), None)
        if slot is None:
            sys.exit(f"roster save '{wanted}' not found in {folder}")
        return folder, slot
    return folder, slots[0]


def cmd_list(args):
    folder, _ = _folder(args)
    print(folder)
    for s in savedata.list_rosters(folder):
        try:
            kind = layout.check_base(Roster(s.sys_data))
            status = "ok" if kind == layout.COMMUNITY else "ok (the game's own roster)"
        except (layout.LayoutError, ValueError) as err:
            status = f"not usable: {err}"
        print(f"  {s.folder}  {s.region:<3} {s.name:<24} {s.modified:%Y-%m-%d %H:%M}  {status}")
    if args.rpcs3:
        for s in savedata.find_rpcs3(args.rpcs3).disc_slots():
            print(f"  disc:{s.region}        {s.region:<3} {s.name}  (from {s.path})")


def cmd_update(args):
    pack = datasource.load_pack(offline=True)
    available = pipeline.steps_for(pack)
    if args.leagues == 'all':
        steps = available
    elif args.leagues == 'default':
        steps = pipeline.default_steps(pack)
    else:
        steps = [s for s in args.leagues.split(',') if s]
    unknown = [s for s in steps if s not in available]
    if unknown:
        sys.exit(f"unknown or unavailable: {', '.join(unknown)}; choose from {', '.join(available)}")
    folder, slot = _source(args)
    targets = None
    if args.save_for:
        wanted = list(savedata.GAMES) if args.save_for.lower() == 'both' else [savedata.title_of(args.save_for)]
        if None in wanted:
            sys.exit("--for takes EU, NA or both")
        targets = wanted
    art_rpcs3 = None
    if args.photos:
        if not args.rpcs3:
            sys.exit("--photos needs --rpcs3 <rpcs3.exe>: the pictures go into RPCS3's game folder")
        art_rpcs3 = savedata.find_rpcs3(args.rpcs3)
    data = None
    if args.research:      # saved inputs instead of live data (tests, reproducing an old build)
        r = datasource.load_research_dir(args.research)
        data = Data(nhl_players=datasource.flatten_nhl(r['teams'], r['extra']) if pipeline.NHL in steps else [],
                    ea_ratings=r['ea'] if pipeline.RATINGS in steps else None,
                    iihf=r['iihf'] if pipeline.NATIONAL in steps else None,
                    leagues={k: v for k, v in pack.get('leagues', {}).items() if k in steps})
    try:
        mine = edits.load() if args.edits else None
        if args.edits:
            print(f"My edits: {len(mine)} from {edits.path()}")
        res = pipeline.update(folder, slot.folder, steps, args.name, print, args.offline, args.dry_run, data,
                              art_rpcs3=art_rpcs3, my_edits=mine, team_edits=edits.load_teams() if args.edits else None,
                              targets=targets, disc=slot if getattr(slot, 'disc', False) else None)
    except RuntimeError as err:          # photos and logos: RPCS3 running, game not found
        sys.exit(str(err))
    for line in res.build.summary() + ([res.art_line()] if res.art_line() else []):
        print(line)
    if not res.build.ok:
        for p in res.build.problems[:40]:
            print("  problem:", p)
        sys.exit(2)
    print("Report:", res.report_path)
    if res.slot:
        print(f"Saved in {res.saved_where()}.")
        print(f"In the game: Roster Management > Load Roster > \"{res.slot.name}\", then save it once.")
    else:
        print("Dry run: nothing was written.")


def cmd_stock_test(args):
    """The owner's in-game check of the game's own roster: two LAB rosters, one as the disc has it
    (does the game load a roster made from its own database?), one updated (does it play?)."""
    from . import stock
    folder, slot = _disc_slot(args, f"disc:{args.version}" if args.version else 'disc')
    try:
        raw = slot.read()
        plain = savedata.install(folder, slot, raw, "LAB game roster as is")
        print(f"Saved \"{plain.name}\" in {plain.folder}.")
        res = pipeline.update(folder, None, pipeline.default_steps(datasource.load_pack(offline=True)),
                              "LAB game roster updated", print, disc=slot)
    except (RuntimeError, stock.StockError) as err:
        sys.exit(str(err))
    if not res.build.ok:
        for p in res.build.problems[:40]:
            print("  problem:", p)
        sys.exit(2)
    print(f"Saved \"{res.slot.name}\" in {res.saved_where()}.")
    print("In the game: Roster Management > Load Roster, load each LAB roster in turn and check what "
          "docs/ROADMAP.md (\"The game's own roster\") lists.")


def cmd_export(args):
    _, slot = _source(args)
    RosterFile(data=savedata.read_roster(slot)).export_csv(args.out)
    print(f"{slot.name} exported to {args.out}")


def cmd_photos(args):
    from .art import install
    try:
        install.remove()
    except RuntimeError as err:
        sys.exit(str(err))


def cmd_league_test(args):
    from .art import lab
    try:
        lab_slot = lab.league_test(savedata.find_rpcs3(args.rpcs3), args.source)
    except RuntimeError as err:
        sys.exit(str(err))
    print(f"In the game: Roster Management > Load Roster > \"{lab_slot.name}\". Then look, as docs/ROADMAP.md "
          "(\"League test\") says, whether Coachella and Henderson are in the AHL list, Jokerit in Liiga, Ajoie in "
          "the National League and Penticton in the WHL, and play one game with each.")


def cmd_art_test(args):
    from .art import lab
    try:
        if args.action == 'remove':
            lab.remove()
            return
        if not args.rpcs3:
            sys.exit("art-test install needs --rpcs3 <rpcs3.exe>")
        lab_slot = lab.install(savedata.find_rpcs3(args.rpcs3), args.source)
    except RuntimeError as err:          # RPCS3 running, test already installed: a sentence for the user
        sys.exit(str(err))
    print(f"In the game: Roster Management > Load Roster > \"{lab_slot.name}\". Then look at the pictures "
          "listed in docs/ROADMAP.md (\"Art test\"). Afterwards: art-test remove.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog='NHLLegacyRosterUpdater', description=f"{APP_NAME} {__version__}")
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name, fn, text in (('list', cmd_list, "show the roster saves in a savedata folder"),
                           ('update', cmd_update, "build an updated roster and save it as a new roster save"),
                           ('export', cmd_export, "dump every table of a roster save to CSV")):
        p = sub.add_parser(name, help=text)
        p.set_defaults(fn=fn)
        where = p.add_mutually_exclusive_group(required=True)
        where.add_argument('--rpcs3', help="your rpcs3.exe (or the folder it is in); the saves are found from there")
        where.add_argument('--savedata',
                           help="instead of --rpcs3: a savedata folder, anything above it, or one roster save folder")
        if name != 'list':
            p.add_argument('--source', help="roster save to start from (folder or roster name), or disc / disc:EU / "
                                            "disc:NA for the game's own roster; default: the newest save")
        if name == 'update':
            p.add_argument('--leagues', default='default',
                           help="comma list of " + ', '.join(pipeline.CORE_STEPS + pipeline.LEAGUE_ORDER)
                                + ", or 'all'; default: everything the data pack has")
            p.add_argument('--name', help="in-game name of the new roster (default: current date and time)")
            p.add_argument('--for', dest='save_for', metavar='EU|NA|both',
                           help="the version(s) of the game to save the new roster for (default: the version "
                                "of the roster it starts from); the two read the same roster file")
            p.add_argument('--dry-run', action='store_true', help="build and check, but write nothing")
            p.add_argument('--offline', action='store_true', help="use the data shipped with the program only")
            p.add_argument('--photos', action='store_true',
                           help="also install current photos and logos into RPCS3's game folder (new; RPCS3 must "
                                "be closed; 'photos remove' takes them away)")
            p.add_argument('--edits', action='store_true',
                           help="apply your own edits from the window's Roster editor after the update")
            p.add_argument('--research', help=argparse.SUPPRESS)
        if name == 'export':
            p.add_argument('--out', required=True)
    p = sub.add_parser('photos', help="remove the installed photos and logos (every file goes back as it was)")
    p.set_defaults(fn=cmd_photos)
    p.add_argument('action', choices=('remove',))
    p = sub.add_parser('stock-test', help="save two LAB rosters made from the game's own roster (in-game test)")
    p.set_defaults(fn=cmd_stock_test)
    p.add_argument('--rpcs3', required=True, help="your rpcs3.exe")
    p.add_argument('--version', choices=('EU', 'NA'), help="which version's disc (default: the first RPCS3 lists)")
    p = sub.add_parser('league-test', help="save a LAB roster with custom teams moved into real leagues (in-game test)")
    p.set_defaults(fn=cmd_league_test)
    p.add_argument('--rpcs3', required=True, help="your rpcs3.exe")
    p.add_argument('--source', help="roster save to start from (default: newest)")
    p = sub.add_parser('art-test', help="install or remove the in-game test of photos and logos (see docs/ROADMAP.md)")
    p.set_defaults(fn=cmd_art_test)
    p.add_argument('action', choices=('install', 'remove'))
    p.add_argument('--rpcs3', help="your rpcs3.exe (needed for install)")
    p.add_argument('--source', help="roster save to start from (default: newest)")
    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except (FileNotFoundError, layout.LayoutError, datasource.Offline) as err:
        sys.exit(str(err))


if __name__ == '__main__':
    main()
