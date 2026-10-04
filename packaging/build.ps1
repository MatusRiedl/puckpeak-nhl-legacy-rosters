# Build the Windows program into dist\ :
#   NHLLegacyRosterUpdater.exe          the window (double-click), with every photo and logo inside
#                                       (legacy_roster\data\photopack.zip, made by tools\build_photopack.py)
#   NHLLegacyRosterUpdater-cli.exe      the same engine on the command line (no photo pack)
#
# Uses its own virtual environment (.venv) so nothing is installed into your Python.
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$running = Get-Process -Name NHLLegacyRosterUpdater, NHLLegacyRosterUpdater-Photos, NHLLegacyRosterUpdater-cli -ErrorAction SilentlyContinue
if ($running) { throw "Close NHLLegacyRosterUpdater first: Windows does not let a running program be replaced." }

$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    python -m venv .venv
}
# customtkinter draws the window; Pillow makes the photos and logos (and the brand assets, make_assets.py);
# certifi brings Mozilla's list of trusted certificates (Windows' own list can lack the one a site uses)
& $py -m pip install --quiet --upgrade pip pyinstaller "customtkinter>=6.0,<7" "pillow>=11.2" certifi
if ($LASTEXITCODE -ne 0) { throw "could not install PyInstaller, customtkinter, Pillow and certifi" }

$version = (& $py -c "import legacy_roster; print(legacy_roster.__version__)").Trim()
$cacert = (& $py -c "import certifi; print(certifi.where())").Trim()
$data = Join-Path $root 'legacy_roster\data'
$common = @(
    '--noconfirm', '--clean', '--onefile',
    '--add-data', "$data;legacy_roster\data",
    '--add-data', "$cacert;legacy_roster\data",           # datasource.CA_BUNDLE
    '--icon', (Join-Path $data 'app.ico'),
    # photos and logos: Pillow finds its file readers by name at run time, so name the ones used
    '--hidden-import', 'PIL.PngImagePlugin', '--hidden-import', 'PIL.JpegImagePlugin',
    '--hidden-import', 'PIL.WebPImagePlugin', '--hidden-import', 'PIL.GifImagePlugin',
    '--hidden-import', 'PIL.DdsImagePlugin', '--hidden-import', 'legacy_roster.art.images',
    '--distpath', 'dist', '--workpath', 'build', '--specpath', 'build'
)

# one window program for everyone, with every photo and logo inside (owner, 2026-10-04): new players'
# pictures are downloaded by it and kept on the player's PC
$pack = Join-Path $data 'photopack.zip'
$aside = Join-Path $root 'build\photopack.zip.aside'
New-Item -ItemType Directory -Force (Join-Path $root 'build') | Out-Null
if (-not (Test-Path $pack)) {
    throw "No photo pack (legacy_roster\data\photopack.zip). Run .venv\Scripts\python tools\build_photopack.py first."
}
$old = Join-Path $root 'dist\NHLLegacyRosterUpdater-Photos.exe'     # the second exe of 0.4-0.5
if (Test-Path $old) { Remove-Item -Force $old }
& $py -m PyInstaller @common --windowed --collect-all customtkinter --name NHLLegacyRosterUpdater packaging\launcher.py
if ($LASTEXITCODE -ne 0) { throw "building the window program failed" }
# the command line stays small: no pack (it downloads, and keeps what it downloaded)
if (Test-Path $pack) { Move-Item -Force $pack $aside }
try {
    & $py -m PyInstaller @common --console --exclude-module customtkinter --exclude-module tkinter `
        --name NHLLegacyRosterUpdater-cli packaging\launcher_cli.py
    if ($LASTEXITCODE -ne 0) { throw "building the command-line program failed" }
} finally {
    if (Test-Path $aside) { Move-Item -Force $aside $pack }
}

Get-ChildItem dist\*.exe | ForEach-Object { "{0}  {1:N1} MB  (version {2})" -f $_.Name, ($_.Length / 1MB), $version }
