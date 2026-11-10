<#
.SYNOPSIS
  Build PurpleAIControl.exe — a windowed (no-console) GUI launcher.

.EXAMPLE
  .\build.ps1          # build dist\PurpleAIControl.exe
  .\build.ps1 -Clean   # wipe build/ dist/ *.spec first
#>
[CmdletBinding()]
param(
    [switch]$Clean,
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$Name = 'PurpleAIControl'
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if ($Clean) {
    Remove-Item -Recurse -Force build, dist, *.spec -ErrorAction SilentlyContinue
}

# --no-project: the GUI uses only the stdlib (tkinter), so we skip syncing the
# project's heavy deps. PyInstaller is pulled in ephemerally with --with.
# --add-data bundles the Siege (Medieval_Pixel_Pack) sprites into the exe.
uv run --no-project --python 3.12 --with pyinstaller pyinstaller `
    --noconsole --onefile --name $Name `
    --distpath dist --workpath build --specpath . `
    --icon "assets\cogito.ico" `
    --add-data "assets;assets" `
    app.py

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$exe = Join-Path $PSScriptRoot "dist\$Name.exe"
if (-not (Test-Path $exe)) { throw "Build did not produce $exe" }
Write-Host ""
Write-Host "Built: $exe" -ForegroundColor Green
Write-Host "Double-click it to open the control panel." -ForegroundColor Green
