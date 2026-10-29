"""Windows-only drawing for the in-game overlay: a layered, click-through, never-activated top-most window with per-pixel
alpha, drawn with GDI+ (part of Windows, no extra packages).

Why not a WebView: WebView2 draws through DirectComposition, which a layered window's colour key or alpha does not reach
(spike 2026-10-28: the keyed colour stayed on screen), so a page cannot be see-through over the game.

`Gfx` is a thin ctypes wrapper over the GDI+ flat API; `Surface` owns one window and its pixels. Everything runs on one
thread (the overlay thread): GDI+ objects and windows belong to the thread that made them.
"""
import ctypes
import time
from ctypes import wintypes as wt

UNIT_PIXEL = 2
SMOOTH_AA = 4
TEXT_AA = 4                  # anti-alias without ClearType (ClearType needs an opaque background)
PIXEL_PARGB = 0xE200B        # PixelFormat32bppPARGB
QUIET = False                # tests set it: draw everything, show nothing


class RectF(ctypes.Structure):
    _fields_ = [('x', ctypes.c_float), ('y', ctypes.c_float), ('w', ctypes.c_float), ('h', ctypes.c_float)]


class _StartupInput(ctypes.Structure):
    _fields_ = [('version', ctypes.c_uint32), ('callback', ctypes.c_void_p), ('suppress_thread', ctypes.c_int),
                ('suppress_bg', ctypes.c_int)]


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [('size', wt.DWORD), ('width', wt.LONG), ('height', wt.LONG), ('planes', wt.WORD), ('bits', wt.WORD),
                ('compression', wt.DWORD), ('image', wt.DWORD), ('xppm', wt.LONG), ('yppm', wt.LONG),
                ('used', wt.DWORD), ('important', wt.DWORD)]


class _Blend(ctypes.Structure):
    _fields_ = [('op', ctypes.c_ubyte), ('flags', ctypes.c_ubyte), ('alpha', ctypes.c_ubyte), ('format', ctypes.c_ubyte)]


class _WndClass(ctypes.Structure):
    _fields_ = [('style', wt.UINT), ('proc', ctypes.c_void_p), ('cls_extra', ctypes.c_int), ('wnd_extra', ctypes.c_int),
                ('instance', wt.HINSTANCE), ('icon', wt.HANDLE), ('cursor', wt.HANDLE), ('brush', wt.HANDLE),
                ('menu', wt.LPCWSTR), ('name', wt.LPCWSTR)]


class _Msg(ctypes.Structure):
    _fields_ = [('hwnd', wt.HWND), ('message', wt.UINT), ('wparam', wt.WPARAM), ('lparam', wt.LPARAM), ('time', wt.DWORD),
                ('pt', wt.POINT)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
_P = ctypes.c_void_p
_gp = None
_user32 = _gdi32 = _kernel32 = None
_token = None


def _bind(lib, name, res, *args):
    fn = getattr(lib, name)
    fn.restype, fn.argtypes = res, list(args)
    return fn


def _load():
    """Bind the Windows functions once (not at import: the module imports on any OS for the unit tests)."""
    global _gp, _user32, _gdi32, _kernel32, _token
    if _gp is not None:
        return
    gp = ctypes.WinDLL('gdiplus')
    f, i, fl, u = ctypes.c_float, ctypes.c_int, ctypes.c_float, ctypes.c_uint32
    d = {}
    for name, res, args in [
        ('GdiplusStartup', i, (_P, _P, _P)),
        ('GdipCreateBitmapFromScan0', i, (i, i, i, i, _P, _P)),
        ('GdipGetImageGraphicsContext', i, (_P, _P)),
        ('GdipDisposeImage', i, (_P,)), ('GdipDeleteGraphics', i, (_P,)),
        ('GdipSetSmoothingMode', i, (_P, i)), ('GdipSetTextRenderingHint', i, (_P, i)),
        ('GdipGraphicsClear', i, (_P, u)),
        ('GdipCreateSolidFill', i, (u, _P)), ('GdipSetSolidFillColor', i, (_P, u)), ('GdipDeleteBrush', i, (_P,)),
        ('GdipFillRectangle', i, (_P, _P, f, f, f, f)), ('GdipFillEllipse', i, (_P, _P, f, f, f, f)),
        ('GdipCreatePath', i, (i, _P)), ('GdipDeletePath', i, (_P,)),
        ('GdipAddPathArc', i, (_P, f, f, f, f, f, f)), ('GdipClosePathFigure', i, (_P,)),
        ('GdipFillPath', i, (_P, _P, _P)),
        ('GdipCreatePen1', i, (u, f, i, _P)), ('GdipDeletePen', i, (_P,)),
        ('GdipDrawEllipse', i, (_P, _P, f, f, f, f)), ('GdipDrawLine', i, (_P, _P, f, f, f, f)),
        ('GdipDrawPath', i, (_P, _P, _P)),
        ('GdipCreateFontFamilyFromName', i, (ctypes.c_wchar_p, _P, _P)), ('GdipDeleteFontFamily', i, (_P,)),
        ('GdipCreateFont', i, (_P, f, i, i, _P)), ('GdipDeleteFont', i, (_P,)),
        ('GdipCreateStringFormat', i, (i, ctypes.c_uint16, _P)), ('GdipDeleteStringFormat', i, (_P,)),
        ('GdipSetStringFormatAlign', i, (_P, i)), ('GdipSetStringFormatLineAlign', i, (_P, i)),
        ('GdipDrawString', i, (_P, ctypes.c_wchar_p, i, _P, _P, _P, _P)),
        ('GdipMeasureString', i, (_P, ctypes.c_wchar_p, i, _P, _P, _P, _P, _P, _P)),
        ('GdipTranslateWorldTransform', i, (_P, f, f, i)), ('GdipScaleWorldTransform', i, (_P, f, f, i)),
        ('GdipResetWorldTransform', i, (_P,)),
        ('GdipSetClipRect', i, (_P, f, f, f, f, i)), ('GdipResetClip', i, (_P,)),
        ('GdipCreateLineBrush', i, (_P, _P, u, u, i, _P)),
        ('GdipCreatePathGradientFromPath', i, (_P, _P)), ('GdipSetPathGradientCenterColor', i, (_P, u)),
        ('GdipSetPathGradientSurroundColorsWithCount', i, (_P, _P, _P)),
        ('GdipSetPathGradientCenterPoint', i, (_P, _P)),
        ('GdipAddPathEllipse', i, (_P, f, f, f, f)),
    ]:
        d[name] = _bind(gp, name, res, *args)
    _gp = type('GP', (), d)
    _user32 = ctypes.WinDLL('user32', use_last_error=True)
    _gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
    _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    LR = ctypes.c_ssize_t
    for name, res, args in [
        ('RegisterClassW', wt.ATOM, (_P,)),
        ('CreateWindowExW', wt.HWND, (wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, i, i, i, i, wt.HWND, wt.HMENU,
                                      wt.HINSTANCE, _P)),
        ('DefWindowProcW', LR, (wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)),
        ('DestroyWindow', wt.BOOL, (wt.HWND,)),
        ('ShowWindow', wt.BOOL, (wt.HWND, i)),
        ('SetWindowPos', wt.BOOL, (wt.HWND, wt.HWND, i, i, i, i, wt.UINT)),
        ('UpdateLayeredWindow', wt.BOOL, (wt.HWND, wt.HDC, _P, _P, wt.HDC, _P, wt.COLORREF, _P, wt.DWORD)),
        ('GetDC', wt.HDC, (wt.HWND,)), ('ReleaseDC', i, (wt.HWND, wt.HDC)),
        ('PeekMessageW', wt.BOOL, (_P, wt.HWND, wt.UINT, wt.UINT, wt.UINT)),
        ('TranslateMessage', wt.BOOL, (_P,)), ('DispatchMessageW', LR, (_P,)),
        ('GetSystemMetrics', i, (i,)),
        ('RegisterHotKey', wt.BOOL, (wt.HWND, i, wt.UINT, wt.UINT)), ('UnregisterHotKey', wt.BOOL, (wt.HWND, i)),
    ]:
        _bind(_user32, name, res, *args)
    for name, res, args in [
        ('CreateCompatibleDC', wt.HDC, (wt.HDC,)), ('DeleteDC', wt.BOOL, (wt.HDC,)),
        ('CreateDIBSection', wt.HBITMAP, (wt.HDC, _P, wt.UINT, _P, wt.HANDLE, wt.DWORD)),
        ('SelectObject', wt.HGDIOBJ, (wt.HDC, wt.HGDIOBJ)), ('DeleteObject', wt.BOOL, (wt.HGDIOBJ,)),
    ]:
        _bind(_gdi32, name, res, *args)
    _bind(_kernel32, 'GetModuleHandleW', wt.HMODULE, wt.LPCWSTR)
    token = ctypes.c_size_t()
    startup = _StartupInput(1, None, 0, 0)
    if _gp.GdiplusStartup(ctypes.byref(token), ctypes.byref(startup), None) != 0:
        raise OSError('GDI+ did not start')
    _token = token.value


def argb(a, r, g, b):
    return ((int(a) & 255) << 24) | ((int(r) & 255) << 16) | ((int(g) & 255) << 8) | (int(b) & 255)


def hexcolor(h, a=255):
    h = h.lstrip('#')
    return argb(a, int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def with_alpha(color, k):
    """`color` (ARGB) with its alpha scaled by k (0..1)."""
    a = int(((color >> 24) & 255) * max(0.0, min(1.0, k)))
    return (a << 24) | (color & 0x00FFFFFF)


class Gfx:
    """Drawing on one Surface. Colours are ARGB ints (see `argb`, `hexcolor`)."""

    def __init__(self, graphics):
        self.g = graphics
        self._fonts = {}
        self._brush = ctypes.c_void_p()
        _gp.GdipCreateSolidFill(0, ctypes.byref(self._brush))
        self._pen = None
        self._fmt = ctypes.c_void_p()
        _gp.GdipCreateStringFormat(0x1000 | 0x4000, 0, ctypes.byref(self._fmt))   # NoWrap | NoClip
        _gp.GdipSetSmoothingMode(graphics, SMOOTH_AA)
        _gp.GdipSetTextRenderingHint(graphics, TEXT_AA)

    def close(self):
        for fam, font in self._fonts.values():
            _gp.GdipDeleteFont(font)
            _gp.GdipDeleteFontFamily(fam)
        _gp.GdipDeleteBrush(self._brush)
        _gp.GdipDeleteStringFormat(self._fmt)
        _gp.GdipDeleteGraphics(self.g)

    def clear(self):
        _gp.GdipGraphicsClear(self.g, 0)

    def fill_rect(self, x, y, w, h, color):
        _gp.GdipSetSolidFillColor(self._brush, color)
        _gp.GdipFillRectangle(self.g, self._brush, x, y, w, h)

    def fill_ellipse(self, x, y, w, h, color):
        _gp.GdipSetSolidFillColor(self._brush, color)
        _gp.GdipFillEllipse(self.g, self._brush, x, y, w, h)

    def _round_path(self, x, y, w, h, r):
        path = ctypes.c_void_p()
        _gp.GdipCreatePath(0, ctypes.byref(path))
        r = max(0.01, min(r, w / 2, h / 2))
        d = r * 2
        _gp.GdipAddPathArc(path, x, y, d, d, 180, 90)
        _gp.GdipAddPathArc(path, x + w - d, y, d, d, 270, 90)
        _gp.GdipAddPathArc(path, x + w - d, y + h - d, d, d, 0, 90)
        _gp.GdipAddPathArc(path, x, y + h - d, d, d, 90, 90)
        _gp.GdipClosePathFigure(path)
        return path

    def fill_round(self, x, y, w, h, r, color):
        path = self._round_path(x, y, w, h, r)
        _gp.GdipSetSolidFillColor(self._brush, color)
        _gp.GdipFillPath(self.g, self._brush, path)
        _gp.GdipDeletePath(path)

    def glow(self, x, y, w, h, r, color, spread, steps=8):
        """A soft halo around a rounded rect: `steps` fading outlines (GDI+ 1.0 has no blur)."""
        for i in range(steps, 0, -1):
            k = i / steps
            grow = spread * k
            self.fill_round(x - grow, y - grow, w + 2 * grow, h + 2 * grow, r + grow, with_alpha(color, (1 - k) ** 2 * .35))

    def ring(self, cx, cy, radius, width, color):
        pen = ctypes.c_void_p()
        _gp.GdipCreatePen1(color, width, UNIT_PIXEL, ctypes.byref(pen))
        _gp.GdipDrawEllipse(self.g, pen, cx - radius, cy - radius, radius * 2, radius * 2)
        _gp.GdipDeletePen(pen)

    def line(self, x1, y1, x2, y2, width, color):
        pen = ctypes.c_void_p()
        _gp.GdipCreatePen1(color, width, UNIT_PIXEL, ctypes.byref(pen))
        _gp.GdipDrawLine(self.g, pen, x1, y1, x2, y2)
        _gp.GdipDeletePen(pen)

    def radial(self, cx, cy, radius, color):
        """A round blob fading from `color` at the middle to nothing at the edge."""
        path = ctypes.c_void_p()
        _gp.GdipCreatePath(0, ctypes.byref(path))
        _gp.GdipAddPathEllipse(path, cx - radius, cy - radius, radius * 2, radius * 2)
        brush = ctypes.c_void_p()
        _gp.GdipCreatePathGradientFromPath(path, ctypes.byref(brush))
        _gp.GdipSetPathGradientCenterColor(brush, color)
        edge = (ctypes.c_uint32 * 1)(color & 0x00FFFFFF)
        count = ctypes.c_int(1)
        _gp.GdipSetPathGradientSurroundColorsWithCount(brush, edge, ctypes.byref(count))
        _gp.GdipFillPath(self.g, brush, path)
        _gp.GdipDeleteBrush(brush)
        _gp.GdipDeletePath(path)

    def font(self, name, px, bold=False):
        key = (name, px, bold)
        if key not in self._fonts:
            fam = ctypes.c_void_p()
            if _gp.GdipCreateFontFamilyFromName(name, None, ctypes.byref(fam)) != 0:
                _gp.GdipCreateFontFamilyFromName('Segoe UI', None, ctypes.byref(fam))
            font = ctypes.c_void_p()
            _gp.GdipCreateFont(fam, float(px), 1 if bold else 0, UNIT_PIXEL, ctypes.byref(font))
            self._fonts[key] = (fam, font)
        return self._fonts[key][1]

    def text(self, s, x, y, font, color, w=2000, h=None, align=0):
        """Draw `s` with its top-left at (x, y); align 0 left, 1 centre, 2 right inside a box `w` wide."""
        _gp.GdipSetStringFormatAlign(self._fmt, align)
        box = RectF(x, y, w, h or 1000)
        _gp.GdipSetSolidFillColor(self._brush, color)
        _gp.GdipDrawString(self.g, s, -1, font, ctypes.byref(box), self._fmt, self._brush)

    def measure(self, s, font):
        _gp.GdipSetStringFormatAlign(self._fmt, 0)
        box, out = RectF(0, 0, 4000, 1000), RectF()
        _gp.GdipMeasureString(self.g, s, -1, font, ctypes.byref(box), self._fmt, ctypes.byref(out), None, None)
        return out.w, out.h

    def push(self, dx, dy, sx=1.0, sy=1.0):
        """Move then scale the origin (scale about the point (dx, dy)); `pop` resets."""
        _gp.GdipTranslateWorldTransform(self.g, dx, dy, 0)
        _gp.GdipScaleWorldTransform(self.g, sx, sy, 0)

    def pop(self):
        _gp.GdipResetWorldTransform(self.g)

    def clip(self, x, y, w, h):
        _gp.GdipSetClipRect(self.g, x, y, w, h, 0)

    def unclip(self):
        _gp.GdipResetClip(self.g)


def _wndproc(hwnd, msg, wparam, lparam):
    if msg == 0x84:                 # WM_NCHITTEST: HTTRANSPARENT, the click goes to the window below
        return -1
    if msg == 0x21:                 # WM_MOUSEACTIVATE: MA_NOACTIVATE
        return 3
    return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)


_proc_ref = None
_class_name = 'OvertimeOverlayClass'
_class_ready = False


def _register():
    global _proc_ref, _class_ready
    if _class_ready:
        return
    _proc_ref = WNDPROC(_wndproc)
    wc = _WndClass()
    wc.proc = ctypes.cast(_proc_ref, ctypes.c_void_p).value
    wc.instance = _kernel32.GetModuleHandleW(None)
    wc.name = _class_name
    if not _user32.RegisterClassW(ctypes.byref(wc)):
        raise OSError(f'RegisterClassW failed: {ctypes.get_last_error()}')
    _class_ready = True


class Surface:
    """One overlay window and its pixel buffer. `draw()` returns the Gfx to paint on (cleared); `present(x, y, alpha)`
    puts the pixels on screen (alpha 0..255 fades the whole surface); `hide()` takes it off."""
    EX = 0x80000 | 0x20 | 0x08000000 | 0x8 | 0x80       # LAYERED | TRANSPARENT | NOACTIVATE | TOPMOST | TOOLWINDOW

    def __init__(self, width, height):
        _load()
        _register()
        self.w, self.h = int(width), int(height)
        self.hwnd = _user32.CreateWindowExW(self.EX, _class_name, 'Overtime overlay', 0x80000000, 0, 0, self.w, self.h,
                                            None, None, _kernel32.GetModuleHandleW(None), None)   # WS_POPUP
        if not self.hwnd:
            raise OSError(f'CreateWindowExW failed: {ctypes.get_last_error()}')
        self.screen_dc = _user32.GetDC(None)
        self.mem_dc = _gdi32.CreateCompatibleDC(self.screen_dc)
        info = _BitmapInfoHeader(ctypes.sizeof(_BitmapInfoHeader), self.w, -self.h, 1, 32, 0, 0, 0, 0, 0, 0)
        self.bits = ctypes.c_void_p()
        self.dib = _gdi32.CreateDIBSection(self.mem_dc, ctypes.byref(info), 0, ctypes.byref(self.bits), None, 0)
        self._old = _gdi32.SelectObject(self.mem_dc, self.dib)
        self.bitmap = ctypes.c_void_p()
        _gp.GdipCreateBitmapFromScan0(self.w, self.h, self.w * 4, PIXEL_PARGB, self.bits, ctypes.byref(self.bitmap))
        graphics = ctypes.c_void_p()
        _gp.GdipGetImageGraphicsContext(self.bitmap, ctypes.byref(graphics))
        self.gfx = Gfx(graphics)
        self.visible = False

    def draw(self):
        self.gfx.clear()
        return self.gfx

    def present(self, x, y, alpha=255):
        pos, size, src = wt.POINT(int(x), int(y)), wt.SIZE(self.w, self.h), wt.POINT(0, 0)
        blend = _Blend(0, 0, max(0, min(255, int(alpha))), 1)       # AC_SRC_OVER, AC_SRC_ALPHA
        _user32.UpdateLayeredWindow(self.hwnd, self.screen_dc, ctypes.byref(pos), ctypes.byref(size), self.mem_dc,
                                    ctypes.byref(src), 0, ctypes.byref(blend), 2)     # ULW_ALPHA
        if not self.visible and not QUIET:
            _user32.ShowWindow(self.hwnd, 4)                     # SW_SHOWNOACTIVATE
            _user32.SetWindowPos(self.hwnd, wt.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)   # topmost, no move/size/activate
            self.visible = True

    def hide(self):
        if self.visible:
            _user32.ShowWindow(self.hwnd, 0)
            self.visible = False

    def close(self):
        self.gfx.close()
        _gp.GdipDisposeImage(self.bitmap)
        _gdi32.SelectObject(self.mem_dc, self._old)
        _gdi32.DeleteObject(self.dib)
        _gdi32.DeleteDC(self.mem_dc)
        _user32.ReleaseDC(None, self.screen_dc)
        _user32.DestroyWindow(self.hwnd)


def register_hotkey(ident, mods, vk):
    """A system-wide hotkey for this thread (it arrives through `pump`); False when another program holds it."""
    _load()
    return bool(_user32.RegisterHotKey(None, ident, mods | 0x4000, vk))       # MOD_NOREPEAT


def unregister_hotkey(ident):
    _load()
    _user32.UnregisterHotKey(None, ident)


def pump():
    """Dispatch this thread's window messages (a window needs them to stay responsive); returns the ids of the hotkeys
    pressed since the last call."""
    msg = _Msg()
    pressed = []
    while _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
        if msg.message == 0x312:                    # WM_HOTKEY
            pressed.append(int(msg.wparam))
            continue
        _user32.TranslateMessage(ctypes.byref(msg))
        _user32.DispatchMessageW(ctypes.byref(msg))
    return pressed


def timer_resolution(on):
    """1 ms timer ticks while the HUD animates (the default 15.6 ms makes sleep()-paced frames uneven)."""
    if QUIET:
        return
    try:
        (ctypes.windll.winmm.timeBeginPeriod if on else ctypes.windll.winmm.timeEndPeriod)(1)
    except (OSError, AttributeError):
        pass


def vsync(fallback=1 / 60):
    """Wait for the compositor's next frame (DwmFlush): layered-window updates then land once per refresh. Falls back to
    a sleep when the compositor is not there to wait for (or in tests)."""
    if not QUIET:
        try:
            if ctypes.windll.dwmapi.DwmFlush() == 0:
                return
        except (OSError, AttributeError):
            pass
    time.sleep(fallback)


def refresh_hz(samples=12):
    """The compositor's rate, measured with DwmFlush (60 when it cannot be measured)."""
    if QUIET:
        return 60.0
    try:
        flush = ctypes.windll.dwmapi.DwmFlush
        flush()
        t0 = time.perf_counter()
        for _ in range(samples):
            if flush() != 0:
                return 60.0
        hz = samples / (time.perf_counter() - t0)
        return hz if 24 <= hz <= 500 else 60.0
    except (OSError, AttributeError):
        return 60.0
