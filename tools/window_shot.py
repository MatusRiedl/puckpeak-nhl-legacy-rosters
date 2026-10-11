"""Show the updater window in a given state and save a picture of it: for checking the window after a change,
and for the README. It never touches a real RPCS3: it builds a pretend RPCS3 folder in a temporary folder
from the base roster (the same one the tests use) and keeps the program's settings, caches and reports there.

    python tools\\window_shot.py <state> <out.png> [options]

states:
    none       RPCS3 not set yet
    ready      RPCS3 found, a roster selected
    updating   an update in progress (made-up progress messages)
    done       runs a real offline update into the pretend folder, then shows the result
    details    done, with the details drawer open
    failed     a made-up failure
    delete     the question before a roster save goes to the Recycle Bin (its Delete button pressed)
    export     the window with "Export only SYS-DATA roster" ticked, after making the roster (export-ready: before)
    editor     the Roster editor tab on the base roster, Edmonton and its first player picked
    equipment  the Roster editor's "Equipment" window for the first Edmonton player (pictures need --disc)
    uniforms   the Roster editor's "Jerseys and ice" window for Edmonton (pictures need --disc)

The pretend RPCS3 has the base roster, an earlier update of it, and a copy saved for the NA version, so the
EU / NA tags and "Save for" show.

How the picture is made: the program's own controllers (legacy_roster/app/) are driven into the state, what
they would push to the page is written to a file, and Microsoft Edge (headless, nothing shows on the screen)
draws the page from web/ with it. So the picture is the same on every PC, at any scaling, without a window.

options:
    --scale F           the screen's scaling: 1 (100 %), 1.5 (150 %), 2 (200 %); default 1
    --screen-lines N    pretend the screen is N lines tall: 768 = small laptop (the window is 80 lines less)
    --show-path TEXT    path shown in step 1, so a public picture does not show a real user name
    --all               switch on every league before a done/details update
    --disc PATH         your own game disc image (read only): the editor's card then shows the players' pictures
    --saves             step 1 points at a copied folder of roster saves instead of RPCS3
    --live              open the real window (pywebview) and let it paint itself into the picture (PrintWindow;
                        Windows, needs .venv: pywebview, Pillow); --scale has no effect there
    --browser           open the page in your web browser instead of saving a picture (for design work; the
                        buttons do nothing there). Ctrl+C stops it; `out` is not used.
"""
import argparse
import ctypes
import datetime
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
BASE = os.environ.get('LEGACY_ROSTER_BASE') or os.path.join(ROOT, 'work', 'backup', 'BLES021530202')
WEB = os.path.join(ROOT, 'legacy_roster', 'web')
STATES = ('none', 'ready', 'updating', 'done', 'details', 'failed', 'delete', 'editor', 'uniforms', 'equipment', 'export',
          'export-ready')
WINDOW = (1080, 780)            # the window's size (main.py), with its frame and title bar
FRAME = (16, 39)                # what the frame and title bar take of it at 100 %
FIXTURE = '__fixture.json'


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


def capture(hwnd, out):
    """The window (its handle) as it paints itself, cropped to its visible frame."""
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
    hwnd = wintypes.HWND(hwnd)
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



def wait(condition, seconds=600):
    end = time.time() + seconds
    while time.time() < end and not condition():
        time.sleep(0.1)


def drive(args, upd, ed, uni, work):
    """Bring the controllers into the state asked for. Says which tab shows and whether the details are open."""
    from legacy_roster import layout as L
    wait(lambda: not upd.scanning, 60)
    state, tab, details = args.state, 'update', False
    if state == 'updating':
        upd._begin(None)
        for msg in ('Starting from "ROSTER2526" (BLES021530202)', 'NHL rosters: ANA (1/32)', 'NHL rosters: TOR (28/32)'):
            upd.say(msg)
    elif state in ('done', 'details'):
        if args.all:
            for key in upd.steps:
                upd.steps[key] = True
        if not args.disc:                   # the pretend RPCS3 has no game to make pictures from
            upd.photos = False
        upd.select(os.path.basename(BASE))
        upd.start()
        wait(lambda: upd.busy, 10)
        wait(lambda: not upd.busy and not upd.scanning)
        details = state == 'details'
    elif state in ('editor', 'uniforms', 'equipment'):
        tab = 'editor'
        upd.select(os.path.basename(BASE))
        ed.opened()
        wait(lambda: ed.view is not None and not ed.busy and ed.after_busy is None)
        ed.pick_team(L.API_TO_SLOT['EDM'])
        rows = ed.snapshot()['rows']
        ed.pick_player(next((r for r in rows if r['pos'] == 'G'), rows[0])['id'] if os.environ.get('SHOT_GOALIE') else rows[0]['id'])
        wait(lambda: not (ed.picture or {}).get('loading'), 60)
        if state == 'uniforms':
            ed.uniforms_open()
            wait(lambda: uni.snapshot() and uni.snapshot()['loaded'], 120)
            wanted = len(uni.versions) + 1 if uni.pictures is not None and args.disc else 0
            wait(lambda: len(uni.thumbs) >= wanted, 120)
        if state == 'equipment':
            ed.equipment.open()
            wait(lambda: ed.equipment.loaded, 120)
    elif state in ('export', 'export-ready'):     # "Export only SYS-DATA roster": the file is written into the temp folder
        os.chdir(work)
        upd.set_export_only(True)
        upd.use_export_file(os.path.join(BASE, 'SYS-DATA'))
        if state == 'export':
            upd.start()
            wait(lambda: upd.busy, 10)
            wait(lambda: not upd.busy)
    elif state == 'delete':
        upd.ask_delete(next(s.folder for s in upd.slots if s.tool_made))
    elif state == 'failed':
        upd.status = ("Nothing was saved.", 'bad')
        upd.show_result(False, "The new roster failed the safety checks, so nothing was saved",
                        ["Anaheim Ducks dresses 19 players (4 C, 4 LW, 3 RW, 6 D, 2 G); the game needs 20 with 2 G "
                         "and at least 6 D", "Your existing rosters are untouched."], [("Show details", 'details')])
    return tab, details


def controllers():
    from legacy_roster.app.editor import EditorController
    from legacy_roster.app.equipment import EquipmentController
    from legacy_roster.app.uniforms import UniformsController
    from legacy_roster.app.update import UpdateController
    from legacy_roster.window.host import WebHost
    host = WebHost()                        # without a window: it only collects what would be pushed
    upd = UpdateController(host)
    ed = EditorController(host, upd)
    uni = UniformsController(host, ed)
    eq = EquipmentController(host, ed)
    for name, snapshot in (('update', upd.snapshot), ('editor', ed.snapshot), ('picture', ed.picture_view),
                           ('uniforms', uni.snapshot), ('thumbs', uni.thumbs_view),
                           ('equipment', eq.snapshot), ('equip_pics', eq.pics_view)):
        host.register(name, snapshot)
    upd.start_up()
    return host, upd, ed, uni


def serve(message):
    """The page and the fixture on a local web server (ES modules do not load from file://): its address."""
    data = json.dumps(message)
    with open(os.path.join(WEB, 'index.html'), encoding='utf-8') as f:
        page = f.read()
    # the state goes into the page itself, so it is there before the first picture is drawn
    shot = page.replace('<head>', '<head>\n<script>window.__FIXTURE__ = ' + data.replace('</', '<\\/') + ';</script>', 1)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split('?')[0]
            if path in ('/' + FIXTURE, '/shot.html'):
                body = (data if path.endswith('.json') else shot).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json' if path.endswith('.json') else 'text/html')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=WEB))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def browser_program():
    for path in (os.path.join(os.environ.get('ProgramFiles(x86)', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                 os.path.join(os.environ.get('ProgramFiles', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                 '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                 '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'):
        if os.path.exists(path):
            return path
    for name in ('msedge', 'microsoft-edge', 'google-chrome', 'chromium', 'chromium-browser'):
        if shutil.which(name):
            return shutil.which(name)
    sys.exit("no Microsoft Edge or Chrome found to draw the page (or use --live)")


def headless(url, out, args, work):
    height = (args.screen_lines - 80) if args.screen_lines else WINDOW[1]
    size = (WINDOW[0] - FRAME[0], height - FRAME[1])
    out = os.path.abspath(out)
    if os.path.exists(out):
        os.remove(out)
    subprocess.run([browser_program(), '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
                    f'--user-data-dir={os.path.join(work, "browser")}', f'--force-device-scale-factor={args.scale}',
                    f'--window-size={size[0]},{size[1]}', '--virtual-time-budget=10000', f'--screenshot={out}', url],
                   check=False, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(out):
        sys.exit("the browser made no picture")
    return size


def live(args, work):
    """The real window, painted into the picture by itself."""
    from legacy_roster.window import main as window_main

    def after(window, c):
        window.events.loaded.wait(30)
        time.sleep(2)
        tab, details = drive(args, c['update'], c['editor'], c['uniforms'], work)
        if tab == 'editor':
            window.run_js("document.querySelectorAll('.tabset button')[1].click()")
        if details:
            c['host'].send('details', {'open': True})
        time.sleep(2.5)
        print(args.state, args.out, capture(window.native.Handle.ToInt64(), args.out))
        window.destroy()
    window_main.main([], after=after)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('state', choices=STATES)
    ap.add_argument('out')
    ap.add_argument('--scale', type=float, default=1.0)
    ap.add_argument('--screen-lines', type=int)
    ap.add_argument('--show-path')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--disc')
    ap.add_argument('--saves', action='store_true')
    ap.add_argument('--live', action='store_true')
    ap.add_argument('--browser', action='store_true')
    args = ap.parse_args()
    if not os.path.exists(os.path.join(BASE, 'SYS-DATA')):
        sys.exit("no base roster save: set LEGACY_ROSTER_BASE to a roster save folder (see docs/DEVELOPING.md)")

    work = tempfile.mkdtemp(prefix='window-shot-')
    os.environ['LOCALAPPDATA'] = os.environ['XDG_DATA_HOME'] = work    # settings, caches and reports stay here
    here = os.getcwd()
    try:
        from legacy_roster import __version__, pipeline, savedata
        from legacy_roster.app import settings as S
        from legacy_roster.app import texts as X
        exe = pretend_rpcs3(work, args.disc)
        if args.saves:                                # the saves copied out of RPCS3: no RPCS3 above them
            copied = os.path.join(work, 'copied saves')
            shutil.copytree(os.path.join(os.path.dirname(exe), 'dev_hdd0', 'home', '00000001', 'savedata'), copied)
            exe = copied
        S.load = lambda: {} if args.state == 'none' else {'rpcs3': exe}
        S.save = lambda values: None
        savedata.running_rpcs3 = lambda: None         # a running RPCS3 on this PC must not be picked up
        savedata.default_rpcs3 = lambda: None         # nor one in its usual place
        real_update = pipeline.update
        pipeline.update = lambda *a, **k: real_update(*a, offline=True, **k)
        if args.live:
            live(args, work)
            return
        host, upd, ed, uni = controllers()
        tab, details = drive(args, upd, ed, uni, work)
        time.sleep(0.3)
        message = host.first()
        message['meta'] = {'version': __version__, 'tagline': X.TAGLINE, 'site_label': X.SITE_LABEL}
        if args.show_path:
            if (message['slices'].get('update', {}).get('rpcs3') or {}).get('path'):
                message['slices']['update']['rpcs3']['path'] = args.show_path
            # the temporary folder and the home folder name the user: a public picture shows made-up ones
            text = json.dumps(message)
            for real, shown in ((work, r'C:\Users\Player\AppData\Local'), (os.path.expanduser('~'), r'C:\Users\Player')):
                text = text.replace(json.dumps(real)[1:-1], json.dumps(shown)[1:-1])
            message = json.loads(text)
        server, url = serve(message)
        query = ('&tab=editor' if tab == 'editor' else '') + ('&details' if details else '')
        if args.browser:
            import webbrowser
            url += f"index.html?fixture={FIXTURE}" + query
            webbrowser.open(url)
            print("The page is open in your browser at", url, "- Ctrl+C stops.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                return
        size = headless(url + "shot.html?still" + query, args.out, args, work)
        server.shutdown()
        print(f"{args.state}: {args.out} {size[0]}x{size[1]} at {args.scale:g}x, {len(upd.slots)} rosters")
    finally:
        os.chdir(here)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
