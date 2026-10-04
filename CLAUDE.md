@AGENTS.md

## Notes for Claude Code (Windows)

- **Two Pythons.** `python` (3.13, has pytest) runs the tests and the command line.
  `.venv\Scripts\python.exe` has CustomTkinter, Pillow and PyInstaller: use it for the window,
  `tools/window_shot.py`, `packaging/make_assets.py` and builds.
- **PowerShell tool.** Pipe Python through a single-quoted here-string (`@'…'@ | python -B -`)
  rather than `python -c "…"` (quoting gets mangled). Set `$env:PYTHONDONTWRITEBYTECODE='1'` so
  no `__pycache__` lands in the repo.
- **Safety filter false alarms.** The command filter reads some tokens inside here-strings as
  deletion commands and blocks the call: the words `rd`, `del`, `rm`, `ri`, and a single letter
  followed by a colon (`lambda c:`, `except OSError as e:`), which looks like a drive. Use longer
  names.
- `Stop-Process -Confirm:$false` (no backtick before `$false`).
- **RPCS3's log** (`<rpcs3>\log\RPCS3.log`) is held open by RPCS3. Open it with full sharing, for
  example `ctypes.windll.kernel32.CreateFileW(path, 0x80000000, 7, None, 3, 0x80, None)`, or it
  fails with "Permission denied".
- **The owner's real RPCS3** (ask for its path, or find it with `savedata.running_rpcs3()` while
  it runs) is read only for you: list, inspect, read the log. Never write there; the game may be
  running. Keep personal paths out of committed files.
- **Screenshots.** A plain screen grab can be stale (locked or remote screen) or catch other
  windows; use `tools/window_shot.py`, which paints the window itself. Display scaling can
  change between sessions, so picture sizes vary.
- **Building**: stop a running `NHLLegacyRosterUpdater` first (`build.ps1` refuses otherwise).
  A copy left running by a test also blocks the build.
