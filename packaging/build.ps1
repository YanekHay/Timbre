<#
.SYNOPSIS
  Builds Timbre: a windowed app folder (dist\Timbre) and, if Inno Setup 6 is
  installed, a per-user installer (dist\Timbre-Setup-<version>.exe).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#>
param(
    [string]$Python = "python",
    [string]$UvVersion = "0.13.9"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

Write-Host "1/5  Build environment" -ForegroundColor Cyan
if (-not (Test-Path ".build-venv\Scripts\python.exe")) { & $Python -m venv .build-venv }
$Py = Join-Path $Root ".build-venv\Scripts\python.exe"
& $Py -m pip install --quiet --disable-pip-version-check -r requirements-ui.txt "pyinstaller>=6.10"
if ($LASTEXITCODE -ne 0) { throw "Installing build dependencies failed" }

Write-Host "2/5  uv (installs the GPU runtime on users' machines)" -ForegroundColor Cyan
if (-not (Test-Path "bin\uv.exe")) {
    New-Item -ItemType Directory -Force bin | Out-Null
    $zip = Join-Path $env:TEMP "uv-$UvVersion.zip"
    $url = "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip"
    Invoke-WebRequest $url -OutFile $zip
    $tmp = Join-Path $env:TEMP "uv-$UvVersion"
    Expand-Archive $zip -DestinationPath $tmp -Force
    Copy-Item (Join-Path $tmp "uv.exe") "bin\uv.exe"
}

Write-Host "3/5  Icon" -ForegroundColor Cyan
& $Py packaging\make_icon.py
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }

Write-Host "4/5  App bundle" -ForegroundColor Cyan
& $Py -m PyInstaller packaging\timbre.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "5/5  Installer" -ForegroundColor Cyan
$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    Write-Host "Installer: dist\Timbre-Setup-0.1.0.exe" -ForegroundColor Green
} else {
    Write-Warning "Inno Setup 6 not found, so only dist\Timbre\ was built. Install it with: winget install JRSoftware.InnoSetup"
}
