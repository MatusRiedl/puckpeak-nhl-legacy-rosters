"""Windows: is Microsoft's WebView2 Runtime there (it draws the window)? Windows 11 and an updated
Windows 10 have it; an old Windows 10 may not. Standard library only."""
import os

CLIENT = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
DOWNLOAD = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"


def available():
    """True when the runtime is installed (or when this is not Windows: the question does not arise)."""
    if os.name != 'nt':
        return True
    import winreg
    places = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node" + CLIENT[len("SOFTWARE"):]),
              (winreg.HKEY_LOCAL_MACHINE, CLIENT), (winreg.HKEY_CURRENT_USER, CLIENT)]
    for root, key in places:
        try:
            with winreg.OpenKey(root, key) as k:
                version, _kind = winreg.QueryValueEx(k, 'pv')
                if version and version != '0.0.0.0':
                    return True
        except OSError:
            continue
    return False


def message(title, text, ask=False):
    """A plain Windows message box (no window toolkit needed). With `ask`: Yes / No, True for Yes."""
    if os.name != 'nt':
        print(f"{title}\n{text}")
        return False
    import ctypes
    flags = 0x00000004 | 0x00000030 if ask else 0x00000010      # MB_YESNO | MB_ICONWARNING, or MB_ICONERROR
    return ctypes.windll.user32.MessageBoxW(None, text, title, flags) == 6     # IDYES
