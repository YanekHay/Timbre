<#
.SYNOPSIS
  Builds Timbre: a windowed app folder (dist\Timbre) and, if Inno Setup 6 is
  installed, a per-user installer (dist\Timbre-Setup-<version>.exe).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#>
param(
    [string]$Python = "python",
    [string]$UvVersion = "0.13.9",
    # Standalone CPython shipped with the installer; runtimes are built from it.
    [string]$PythonBuild = "20261124",
    [string]$PythonVersion = "3.12.16",
    [string]$PythonSha256 = "8152ff5b6c6c044ddbbaa3531dda59cb9ce5bd6cb670d4c9ac2e3ab91afa8778"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

Write-Host "1/5  Build environment" -ForegroundColor Cyan
if (-not (Test-Path ".build-venv\Scripts\python.exe")) { & $Python -m venv .build-venv }
$Py = Join-Path $Root ".build-venv\Scripts\python.exe"
& $Py -m pip install --quiet --disable-pip-version-check -r requirements-ui.txt "pyinstaller>=6.10"
if ($LASTEXITCODE -ne 0) { throw "Installing build dependencies failed" }

Write-Host "2/5  uv and standalone Python (build the GPU runtime on users' machines)" -ForegroundColor Cyan
if (-not (Test-Path "bin\uv.exe")) {
    New-Item -ItemType Directory -Force bin | Out-Null
    $zip = Join-Path $env:TEMP "uv-$UvVersion.zip"
    $url = "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip"
    Invoke-WebRequest $url -OutFile $zip
    $tmp = Join-Path $env:TEMP "uv-$UvVersion"
    Expand-Archive $zip -DestinationPath $tmp -Force
    Copy-Item (Join-Path $tmp "uv.exe") "bin\uv.exe"
}
if (-not (Test-Path "bin\python\python.exe")) {
    $name = "cpython-$PythonVersion+$PythonBuild-x86_64-pc-windows-msvc-install_only.tar.gz"
    $tgz = Join-Path $env:TEMP $name
    $url = "https://github.com/astral-sh/python-build-standalone/releases/download/$PythonBuild/" + [uri]::EscapeDataString($name)
    Invoke-WebRequest $url -OutFile $tgz
    $hash = (Get-FileHash $tgz -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $PythonSha256) { Remove-Item $tgz; throw "Python download checksum mismatch ($hash)" }
    tar -xzf $tgz -C bin           # unpacks to bin\python
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path "bin\python\python.exe")) { throw "Unpacking Python failed" }
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
    Write-Host "Installer: dist\Timbre-Setup-0.3.0.exe" -ForegroundColor Green
} else {
    Write-Warning "Inno Setup 6 not found, so only dist\Timbre\ was built. Install it with: winget install JRSoftware.InnoSetup"
}
