"""Open the updater window in a given state and save a picture of it: for checking the window
after a change, and for the README. It never touches a real RPCS3: it builds a pretend RPCS3
folder in a temporary folder from the base roster (the same one the tests use) and keeps the
program's settings, caches and reports there too.

    .venv\\Scripts\\python tools\\window_shot.py <state> <out.png> [options]

states:
    none       RPCS3 not set yet
    ready      RPCS3 found, a roster selected
    updating   an update in progress (made-up progress messages)
    done       runs a real offline update into the pretend folder, then shows the result
    details    done, with the details panel open
    failed     a made-up failure banner
    editor           the Roster editor tab on the base roster, Edmonton and its first player picked
    editor-preview   the same in "To be" (a real offline update, in memory)

The pretend RPCS3 has the base roster, an earlier update of it, and a copy saved for the NA
version, so the EU / NA tags and "Save for" show.

options:
    --scale F           multiplies the screen's own scaling, to see another one: 0.5 on a 200 % screen
                        or 0.667 on a 150 % screen shows the 100 % look. Stay at 100 % or above:
                        no real screen goes lower, and there the 1-pixel outlines vanish
    --screen-lines N    pretend the screen is N lines tall (window units): 768 = small laptop
    --show-path TEXT    path shown in step 1, so a public picture does not show a real user name
    --all               switch on every league before a done/details update
    --disc PATH         your own game disc image (read only): the editor's card then shows the players'
                        pictures instead of saying where the game is

The window paints itself into the picture (PrintWindow), so it comes out right even when the
screen is locked or covered. Windows only; needs Pillow (in .venv).
"""
import argparse
import ctypes
import datetime
import os
import shutil
import sys
import tempfile
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
BASE = os.environ.get('LEGACY_ROSTER_BASE') or os.path.join(ROOT, 'work', 'backup', 'BLES021530202')


def pretend_rpcs3(folder, disc=None):
    """An RPCS3 folder with the base roster, one earlier update of it and a copy for the NA version
    (`disc`: a game disc image both versions are said to be on)."""
    from legacy_roster import savedata
    sd = os.path.join(folder, 'rpcs3', 'dev_hdd0', 'home', '00000001', 'savedata')
    shutil.copytree(BASE, os.path.join(sd, os.path.basename(BASE)))
    exe = os.path.join(folder, 'rpcs3', 'rpcs3.exe')
    open(exe, 'wb').close()
    base = savedata.list_rosters(sd)[0]
    with open(base.sys_data, 'rb') as f:
        data = f.read()
    savedata.install(sd, base, data, savedata.default_name(datetime.datetime.now() - datetime.timedelta(days=1)))
    savedata.install(sd, base, data, "Community roster NA", title_id='BLUS31540')
    if disc:
        os.makedirs(os.path.join(folder, 'rpcs3', 'config'))
        with open(os.path.join(folder, 'rpcs3', 'config', 'games.yml'), 'w', encoding='utf-8') as f:
            f.write(''.join(f'{t}: "{os.path.abspath(disc)}"\n' for t in savedata.GAMES))
    return exe


def capture(root, out):
    """The window as it paints itself, cropped to its visible frame."""
    from PIL import Image
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    for fn in (user32.GetWindowDC, gdi32.CreateCompatibleDC, gdi32.CreateCompatibleBitmap, gdi32.SelectObject):
        fn.restype = wintypes.HANDLE
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HANDLE]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.UINT]
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HANDLE]
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    gdi32.GetDIBits.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                                ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteDC.argtypes = [wintypes.HANDLE]
    hwnd = wintypes.HWND(int(root.wm_frame(), 16))
    whole, visible = wintypes.RECT(), wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(whole))
    # the window rectangle also counts the invisible resize border; DWM knows the visible frame
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(visible), ctypes.sizeof(visible))
    w, h = whole.right - whole.left, whole.bottom - whole.top
    wdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(wdc)
    bmp = gdi32.CreateCompatibleBitmap(wdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    painted = user32.PrintWindow(hwnd, mdc, 2)                  # PW_RENDERFULLCONTENT
    header = (ctypes.c_uint32 * 10)(40, w, (-h) & 0xFFFFFFFF, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)    # top-down, 32 bit
    bits = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, bits, header, 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, wdc)
    if not painted:
        raise RuntimeError("the window could not be painted into a picture")
    img = Image.frombuffer('RGB', (w, h), bits, 'raw', 'BGRX', 0, 1)
    img = img.crop((visible.left - whole.left, visible.top - whole.top,
                    visible.right - whole.left, visible.bottom - whole.top))
    img.save(out)
    return img.size


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('state', choices=('none', 'ready', 'updating', 'done', 'details', 'failed', 'editor',
                                      'editor-preview'))
    ap.add_argument('out')
    ap.add_argument('--scale', type=float)
    ap.add_argument('--screen-lines', type=int)
    ap.add_argument('--show-path')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--disc')
    args = ap.parse_args()
    if not os.path.exists(os.path.join(BASE, 'SYS-DATA')):
        sys.exit("no base roster save: set LEGACY_ROSTER_BASE to a roster save folder (see docs/DEVELOPING.md)")

    work = tempfile.mkdtemp(prefix='window-shot-')
    os.environ['LOCALAPPDATA'] = work                 # settings, caches and reports stay in the temp folder
    try:
        import customtkinter as ctk
        if args.scale:
            ctk.set_widget_scaling(args.scale)
            ctk.set_window_scaling(args.scale)
        from legacy_roster import gui, pipeline, savedata
        from legacy_roster import layout as L
        from legacy_roster import theme as T

        exe = pretend_rpcs3(work, args.disc)
        gui.load_settings = lambda: {} if args.state == 'none' else {'rpcs3': exe}
        gui.save_settings = lambda values: None
        savedata.running_rpcs3 = lambda: None         # a running RPCS3 on this PC must not be picked up
        real_update = pipeline.update
        pipeline.update = lambda *a, **k: real_update(*a, offline=True, **k)
        if args.screen_lines:
            T.screen_height = lambda widget: args.screen_lines

        ctk.set_appearance_mode('dark')
        root = ctk.CTk(fg_color=T.BG)
        T.load_fonts(root)
        app = gui.App(root)
        root.geometry('+40+30')

        def pump(seconds):
            end = time.time() + seconds
            while time.time() < end:
                root.update()
                time.sleep(0.02)

        pump(1.0)
        deadline = time.time() + 60
        while app.scanning and time.time() < deadline:     # the rosters are read in the background
            pump(0.1)
        if args.state == 'updating':
            app.busy = True
            app.refresh_state()
            app.go.configure(text="Updating...")
            for msg in ('Starting from "ROSTER2526" (BLES021530202)', 'NHL rosters: ANA (1/32)',
                        'NHL rosters: TOR (28/32)'):
                app.say(msg)
        elif args.state in ('done', 'details'):
            if args.all:
                for var in app.steps.values():
                    var.set(True)
            if not args.disc:                        # the pretend RPCS3 has no game to make pictures from
                app.photos.set(False)
            app.select(os.path.basename(BASE))
            app.start()
            deadline = time.time() + 600
            while app.busy and time.time() < deadline:
                pump(0.2)
            if args.state == 'details':
                app.toggle_details()
        elif args.state.startswith('editor'):
            ed = app.editor
            app.select(os.path.basename(BASE))
            app.tabs.set(gui.EDITOR_TAB)
            app.tab_changed()

            def wait():
                pump(0.3)
                deadline = time.time() + 600
                while ed.busy and time.time() < deadline:
                    pump(0.2)
                pump(0.5)
            wait()
            if args.state == 'editor-preview':
                from legacy_roster.editor.view import TO_BE
                ed.mode_switch.set(TO_BE)
                ed.set_mode(TO_BE)                   # what a click on "To be" does
                wait()
            edm = str(L.API_TO_SLOT['EDM'])
            ed.team_tree.selection_set(edm)
            pump(0.5)
            first = ed.table.get_children()[0]
            ed.table.selection_set(first)
            pump(2.5)                                # the picture is made in the background
        elif args.state == 'failed':
            app.failed("The new roster failed the safety checks, so nothing was saved",
                       ["Anaheim Ducks dresses 19 players (4 C, 4 LW, 3 RW, 6 D, 2 G); "
                        "the game needs 20 with 2 G and at least 6 D",
                        "Your existing rosters are untouched."])
        if args.show_path:
            app.show_path(args.show_path, T.TEXT)
        pump(1.2)
        size = capture(root, args.out)
        print(f"{args.state}: {args.out} {size[0]}x{size[1]}, scaling {T.scaling(root)}, "
              f"font {T._FAMILY['normal']}, {len(app.slots)} rosters")
        root.destroy()
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
