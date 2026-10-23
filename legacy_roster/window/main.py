"""Open the window: the page in `web/`, the controllers of `app/`, pywebview between them."""
import os
import sys

from .. import __version__, datasource
from ..app import texts as X
from . import webview2

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'web')
DATA = os.path.join(os.path.dirname(WEB), 'data')
NEEDED = [os.path.join(WEB, *p) for p in (('index.html',), ('js', 'main.js'), ('vendor', 'react.production.min.js'),
                                          ('vendor', 'react-dom.production.min.js'), ('img', 'logo.png'))] \
    + [os.path.join(DATA, 'datapack.json.gz')]
WIDTH, HEIGHT, MIN_SIZE = 1080, 780, (940, 640)
BACKGROUND = '#07111f'
TITLE_BAR = 0x2e1a0a        # the title bar's colour on Windows 11 (#0a1a2e as Windows writes it: blue, green, red)


def missing_files():
    """The program's own files that are not there (an antivirus or a cleaner removed them from the
    temporary folder the exe unpacks into)."""
    return [p for p in NEEDED if not os.path.exists(p)]


def classic(reason):
    """The old window, while it is kept (0.10.x), when the new one cannot start; False without it."""
    try:
        import customtkinter  # noqa: F401
        from ..gui import main as old
    except ImportError:
        return False
    if reason:
        try:
            with open(datasource.app_dir('logs', 'error.log'), 'a', encoding='utf-8') as f:
                f.write(f"The new window could not start ({reason}); the classic window was used.\n")
        except OSError:
            pass
    old()
    return True


def dark_title_bar(window):
    """Windows: a dark title bar in the colour of the panels (Windows 10 takes the dark mode only)."""
    if os.name != 'nt':
        return
    try:
        import ctypes
        hwnd = window.native.Handle.ToInt64()
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))        # dark mode
        colour = ctypes.c_int(TITLE_BAR)
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colour), ctypes.sizeof(colour))  # caption colour (Windows 11)
    except Exception:
        pass


LARGEST, SHARE = (1760, 1100), (0.9, 0.94)


def fit(area):
    """(x, y, width, height) of the screen's free area (no taskbar) -> the window's (width, height, x, y): most of
    it, centred, at least the old 1080 x 780 where that fits."""
    ax, ay, aw, ah = area
    w = min(LARGEST[0], max(min(WIDTH, aw), int(aw * SHARE[0])))
    h = min(LARGEST[1], max(min(HEIGHT, ah), int(ah * SHARE[1])))
    w, h = max(w, MIN_SIZE[0]), max(h, MIN_SIZE[1])
    return w, h, ax + max(0, (aw - w) // 2), ay + max(0, (ah - h) // 2)


def work_area(webview):
    """The main screen's free area in the window's units (Windows: its WorkingArea; elsewhere the screen less 80)."""
    screens = list(webview.screens)
    screen = next((s for s in screens if s.x == 0 and s.y == 0), screens[0])
    frame = getattr(screen, 'frame', None)
    try:
        return int(frame.X), int(frame.Y), int(frame.Width), int(frame.Height)
    except AttributeError:
        return int(screen.x), int(screen.y), int(screen.width), int(screen.height) - 80


def window_box(webview):
    try:
        return fit(work_area(webview))
    except Exception:
        return WIDTH, HEIGHT, None, None


QUEUE = 64


def roomy_server():
    """pywebview's local server listens with Python's default queue of 5 connections; the page asks for more files at
    once, Windows refuses what does not fit and the window stayed blank (lab round 47c)."""
    from wsgiref.simple_server import WSGIServer
    WSGIServer.request_queue_size = QUEUE


def main(argv=None, after=None):
    """`after(window, controllers)`: run in a thread once the window shows (tools/window_shot.py)."""
    argv = sys.argv[1:] if argv is None else argv
    if '--classic' in argv:
        if not classic(None):
            webview2.message("Legacy Roster Updater", "The classic window is not part of this program.")
        return
    if missing_files():
        webview2.message("Legacy Roster Updater", X.MISSING_FILES)
        return
    if not webview2.available():
        if classic("no WebView2 Runtime"):
            return
        if webview2.message("Legacy Roster Updater",
                            "This program needs Microsoft Edge WebView2 Runtime, a free part of Windows from Microsoft.\n\n"
                            "Open the download page now? Install the \"Evergreen Bootstrapper\", then start this "
                            "program again.", ask=True):
            import webbrowser
            webbrowser.open(webview2.DOWNLOAD)
        return
    try:
        import webview
    except ImportError as err:
        if not classic(f"pywebview missing: {err}"):
            sys.exit("The window needs the 'pywebview' package:  pip install pywebview\n"
                     "(the command line works without it:  python -m legacy_roster list --rpcs3 <rpcs3.exe>)")
        return

    from ..app import selfupdate
    from ..app.update import UpdateController
    from ..app.editor import EditorController
    from ..app.uniforms import UniformsController
    from ..app.equipment import EquipmentController
    from ..app.lines import LinesController
    from ..app.strategy import StrategyController
    from ..app.calendar import CalendarController
    from ..app.office import OfficeController
    from ..app.prospects import ProspectsController
    from ..app.career import CareerController
    from ..app.season import SeasonSource
    from .api import Api
    from .host import WebHost

    host = WebHost()
    update = UpdateController(host)
    editor = EditorController(host, update)
    uniforms = UniformsController(host, editor)
    equipment = EquipmentController(host, editor)
    lines = LinesController(host, editor)
    strategy = StrategyController(host, editor)
    season = SeasonSource(editor)                    # the player's own Season / Be a GM save, read only
    calendar = CalendarController(host, editor, season)
    office = OfficeController(host, editor, season)
    career = CareerController(host, editor)          # running Be a Pro careers (saved only on the player's Save)
    prospects = ProspectsController(host, editor, career)
    host.register('update', update.snapshot)
    host.register('editor', editor.snapshot)
    host.register('picture', editor.picture_view)
    host.register('face_pics', editor.face_pics_view)
    host.register('look_pics', editor.look_pics_view)
    host.register('uniforms', uniforms.snapshot)
    host.register('thumbs', uniforms.thumbs_view)
    host.register('equipment', equipment.snapshot)
    host.register('equip_pics', equipment.pics_view)
    host.register('lines', lines.snapshot)
    host.register('strategy', strategy.snapshot)
    host.register('rail', editor.rail_view)
    host.register('calendar', calendar.snapshot)
    host.register('office', office.snapshot)
    host.register('contract', office.contract_snapshot)
    host.register('prospects', prospects.snapshot)
    host.register('career', career.snapshot)
    api = Api(host, update, editor, uniforms, equipment, lines, strategy, calendar, office, prospects, career)
    width, height, x, y = window_box(webview)
    window = webview.create_window(f"Puck Peak  -  Legacy Roster Updater {__version__}",
                                   url=os.path.join(WEB, 'index.html'), js_api=api, width=width, height=height,
                                   x=x, y=y, min_size=MIN_SIZE, background_color=BACKGROUND, text_select=False)
    host.attach(window)
    window.events.closing += lambda: update.closing() and editor.closing() and career.closing()
    window.events.shown += lambda: dark_title_bar(window)
    update.start_up()
    host.every(15, update.tick)
    selfupdate.clean_leftovers()
    update.check_for_update()
    update.download_pictures()
    controllers = {'host': host, 'update': update, 'editor': editor, 'uniforms': uniforms, 'equipment': equipment,
                   'lines': lines, 'strategy': strategy, 'calendar': calendar, 'office': office,
                   'prospects': prospects, 'career': career}
    roomy_server()
    try:
        webview.start(func=(lambda: after(window, controllers)) if after else None,
                      http_server=True, private_mode=True, storage_path=datasource.app_dir('webview'),
                      debug=os.environ.get('LEGACY_ROSTER_DEVTOOLS') == '1',
                      icon=os.path.join(DATA, 'app.ico' if os.name == 'nt' else 'app_256.png'))
    except Exception as err:
        from ..app import jobs
        jobs.log_unexpected(err)
        if not classic(f"pywebview failed: {err}"):
            webview2.message("Legacy Roster Updater",
                             f"The window could not start: {err}\n\nThe command line works without it "
                             "(NHLLegacyRosterUpdater-cli).")
