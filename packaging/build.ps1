# Build the Windows program into dist\ :
#   NHLLegacyRosterUpdater.exe          the window (double-click)
#   NHLLegacyRosterUpdater-Photos.exe   the same window with every photo and logo inside
#                                       (only when legacy_roster\data\photopack.zip exists)
#   NHLLegacyRosterUpdater-cli.exe      the same engine on the command line
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
# customtkinter draws the window; Pillow makes the photos and logos (and the brand assets, make_assets.py)
& $py -m pip install --quiet --upgrade pip pyinstaller "customtkinter>=6.0,<7" "pillow>=11.2"
if ($LASTEXITCODE -ne 0) { throw "could not install PyInstaller, customtkinter and Pillow" }

$version = (& $py -c "import legacy_roster; print(legacy_roster.__version__)").Trim()
$data = Join-Path $root 'legacy_roster\data'
$common = @(
    '--noconfirm', '--clean', '--onefile',
    '--add-data', "$data;legacy_roster\data",
    '--icon', (Join-Path $data 'app.ico'),
    # photos and logos: Pillow finds its file readers by name at run time, so name the ones used
    '--hidden-import', 'PIL.PngImagePlugin', '--hidden-import', 'PIL.JpegImagePlugin',
    '--hidden-import', 'PIL.WebPImagePlugin', '--hidden-import', 'PIL.GifImagePlugin',
    '--hidden-import', 'PIL.DdsImagePlugin', '--hidden-import', 'legacy_roster.art.images',
    '--distpath', 'dist', '--workpath', 'build', '--specpath', 'build'
)

# the photo pack goes only into the photo edition: keep it out of the plain builds
$pack = Join-Path $data 'photopack.zip'
$aside = Join-Path $root 'build\photopack.zip.aside'
New-Item -ItemType Directory -Force (Join-Path $root 'build') | Out-Null
if (Test-Path $pack) { Move-Item -Force $pack $aside }
try {
    & $py -m PyInstaller @common --windowed --collect-all customtkinter --name NHLLegacyRosterUpdater packaging\launcher.py
    if ($LASTEXITCODE -ne 0) { throw "building the window program failed" }
} finally {
    if (Test-Path $aside) { Move-Item -Force $aside $pack }
}
if (Test-Path $pack) {
    # the same window with every photo and logo inside (tools\build_photopack.py makes the pack)
    & $py -m PyInstaller @common --windowed --collect-all customtkinter --name NHLLegacyRosterUpdater-Photos packaging\launcher.py
    if ($LASTEXITCODE -ne 0) { throw "building the photo edition failed" }
} else {
    Write-Warning "No photo pack (legacy_roster\data\photopack.zip): the photo edition is not built. Run tools\build_photopack.py first."
}
if (Test-Path $pack) { Move-Item -Force $pack $aside }
try {
    & $py -m PyInstaller @common --console --exclude-module customtkinter --exclude-module tkinter `
        --name NHLLegacyRosterUpdater-cli packaging\launcher_cli.py
    if ($LASTEXITCODE -ne 0) { throw "building the command-line program failed" }
} finally {
    if (Test-Path $aside) { Move-Item -Force $aside $pack }
}

Get-ChildItem dist\*.exe | ForEach-Object { "{0}  {1:N1} MB  (version {2})" -f $_.Name, ($_.Length / 1MB), $version }
