#!/usr/bin/env bash
# Build the program on Linux or macOS into dist/ (PyInstaller builds for the system it runs on, so
# build the Mac version on a Mac and the Linux version on Linux; .github/workflows/build.yml does
# both on GitHub's machines):
#   Linux:  dist/NHLLegacyRosterUpdater          the window (the page in legacy_roster/web through pywebview and the
#                                                system's WebKitGTK: apt install gir1.2-webkit2-4.1; without it the
#                                                classic window, which needs Tk: apt install python3-tk)
#           dist/NHLLegacyRosterUpdater-cli      the command line
#   macOS:  dist/NHLLegacyRosterUpdater.app      the window
#           dist/NHLLegacyRosterUpdater-cli      the command line
# No picture pack goes inside: the program downloads its pictures (legacy_roster/packs.py), as the Windows exe does.
#
#   bash packaging/build.sh
set -euo pipefail
cd "$(dirname "$0")/.."

py=.venv-build/bin/python
if [ ! -x "$py" ]; then
    python3 -m venv .venv-build
fi
"$py" -m pip install --quiet --upgrade pip pyinstaller "pywebview==6.2.1" "customtkinter>=6.0,<7" "pillow>=11.2" certifi
if [ "$(uname)" != "Darwin" ]; then
    # pywebview draws with GTK on Linux; PyGObject needs the system's GObject headers (apt install libgirepository1.0-dev
    # libcairo2-dev). Without it the program opens the classic window instead.
    "$py" -m pip install --quiet "PyGObject<3.51" || echo "PyGObject not installed: the Linux program will open the classic window."
fi

version=$("$py" -c "import legacy_roster; print(legacy_roster.__version__)")
cacert=$("$py" -c "import certifi; print(certifi.where())")
web="$PWD/legacy_roster/web"
data="$PWD/legacy_roster/data"         # full paths: PyInstaller reads relative ones from its spec folder (build/)
if ls "$data"/*.zip* >/dev/null 2>&1; then
    echo "$data holds a zip: packs never go inside the program (private/packs)." >&2
    exit 1
fi
"$py" tools/clean_check.py || { echo "tools/clean_check.py found words that must not ship (see above)" >&2; exit 1; }

# PIL._tkinter_finder: Pillow's bridge to Tk, imported only on a fallback path that PyInstaller does
# not see; without it the window stops at start ("invalid command name PyImagingPhoto").
common=(--noconfirm --clean
        --add-data "$data:legacy_roster/data"
        --add-data "$cacert:legacy_roster/data"
        --hidden-import PIL.PngImagePlugin --hidden-import PIL.JpegImagePlugin
        --hidden-import PIL.WebPImagePlugin --hidden-import PIL.GifImagePlugin
        --hidden-import PIL.DdsImagePlugin --hidden-import legacy_roster.art.images
        --hidden-import legacy_roster.art.looks --hidden-import legacy_roster.art.lookpack --hidden-import PIL._tkinter_finder
        --distpath dist --workpath build --specpath build)

if [ "$(uname)" = "Darwin" ]; then
    "$py" -m PyInstaller "${common[@]}" --windowed --icon "$data/app_256.png" --add-data "$web:legacy_roster/web" \
        --collect-all webview --collect-all customtkinter --name NHLLegacyRosterUpdater packaging/launcher.py
    (cd dist && ditto -c -k --keepParent NHLLegacyRosterUpdater.app "NHLLegacyRosterUpdater-$version-macos.zip")
else
    "$py" -m PyInstaller "${common[@]}" --onefile --windowed --add-data "$web:legacy_roster/web" \
        --collect-all webview --collect-all customtkinter --name NHLLegacyRosterUpdater packaging/launcher.py
fi
# the command line stays small: no window toolkit
"$py" -m PyInstaller "${common[@]}" --onefile --console --exclude-module customtkinter --exclude-module tkinter \
    --exclude-module webview --exclude-module gi \
    --name NHLLegacyRosterUpdater-cli packaging/launcher_cli.py

ls -l dist
echo "version $version"
