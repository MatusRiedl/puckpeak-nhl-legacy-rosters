#!/usr/bin/env bash
# Build the program on Linux or macOS into dist/ (PyInstaller builds for the system it runs on, so
# build the Mac version on a Mac and the Linux version on Linux; .github/workflows/build.yml does
# both on GitHub's machines):
#   Linux:  dist/NHLLegacyRosterUpdater          the window (needs Tk: apt install python3-tk)
#           dist/NHLLegacyRosterUpdater-cli      the command line
#   macOS:  dist/NHLLegacyRosterUpdater.app      the window
#           dist/NHLLegacyRosterUpdater-cli      the command line
# With legacy_roster/data/photopack.zip (tools/build_photopack.py) every photo and logo goes inside,
# as in the Windows exe; without it the pictures are downloaded on the player's computer.
#
#   bash packaging/build.sh
set -euo pipefail
cd "$(dirname "$0")/.."

py=.venv-build/bin/python
if [ ! -x "$py" ]; then
    python3 -m venv .venv-build
fi
"$py" -m pip install --quiet --upgrade pip pyinstaller "customtkinter>=6.0,<7" "pillow>=11.2" certifi

version=$("$py" -c "import legacy_roster; print(legacy_roster.__version__)")
cacert=$("$py" -c "import certifi; print(certifi.where())")
data=legacy_roster/data
if [ ! -f "$data/photopack.zip" ]; then
    echo "No photo pack ($data/photopack.zip): the pictures will be downloaded on the player's computer."
    echo "To put them inside, run first:  $py tools/build_photopack.py"
fi

common=(--noconfirm --clean
        --add-data "$data:legacy_roster/data"
        --add-data "$cacert:legacy_roster/data"
        --hidden-import PIL.PngImagePlugin --hidden-import PIL.JpegImagePlugin
        --hidden-import PIL.WebPImagePlugin --hidden-import PIL.GifImagePlugin
        --hidden-import PIL.DdsImagePlugin --hidden-import legacy_roster.art.images
        --distpath dist --workpath build --specpath build)

if [ "$(uname)" = "Darwin" ]; then
    "$py" -m PyInstaller "${common[@]}" --windowed --icon "$PWD/$data/app_256.png" \
        --collect-all customtkinter --name NHLLegacyRosterUpdater packaging/launcher.py
    (cd dist && ditto -c -k --keepParent NHLLegacyRosterUpdater.app "NHLLegacyRosterUpdater-$version-macos.zip")
else
    "$py" -m PyInstaller "${common[@]}" --onefile --windowed \
        --collect-all customtkinter --name NHLLegacyRosterUpdater packaging/launcher.py
fi
# the command line stays small: no photo pack, no window toolkit
aside=build/photopack.zip.aside
mkdir -p build
[ -f "$data/photopack.zip" ] && mv "$data/photopack.zip" "$aside"
trap '[ -f "$aside" ] && mv "$aside" "$data/photopack.zip"' EXIT
"$py" -m PyInstaller "${common[@]}" --onefile --console --exclude-module customtkinter --exclude-module tkinter \
    --name NHLLegacyRosterUpdater-cli packaging/launcher_cli.py

ls -l dist
echo "version $version"
