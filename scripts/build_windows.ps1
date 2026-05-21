# Build standalone app + Windows installer (.exe setup).
# Run from project root: .\scripts\build_windows.ps1

param(
    [switch]$InstallerOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$AppVersion = "1.0.0"
$pyproject = Join-Path $Root "pyproject.toml"
if (Test-Path $pyproject) {
    $versionLine = Get-Content $pyproject | Where-Object { $_ -match '^\s*version\s*=' } | Select-Object -First 1
    if ($versionLine -match 'version\s*=\s*"([0-9.]+)"') {
        $AppVersion = $Matches[1]
    }
}

if (-not $InstallerOnly) {
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path $Python)) {
        $Python = (Get-Command python -ErrorAction Stop).Source
    }

    Write-Host "Using Python: $Python"
    & $Python -c "import sys; print('Version:', sys.version)"

    & $Python -m pip install --upgrade pip -q
    & $Python -m pip install -e . -q
    & $Python -m pip install "pyinstaller>=6.0.0" -q

    $dist = Join-Path $Root "dist"
    $build = Join-Path $Root "build"
    if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
    if (Test-Path $build) { Remove-Item $build -Recurse -Force }

    Write-Host "Building application (PyInstaller)..."
& $Python -m PyInstaller --noconfirm (Join-Path $Root "BiomarkTagManager.spec")

$appDir = Join-Path $dist "BiomarkTagManager"
$exe = Join-Path $appDir "BiomarkTagManager.exe"
    if (-not (Test-Path $exe)) {
        throw "Build failed: $exe was not created."
    }

    $internal = Join-Path $appDir "_internal"
    $dllNames = @("python3.dll", "python314.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll")
    foreach ($dll in $dllNames) {
        $src = Join-Path $internal $dll
        if (Test-Path $src) {
            Copy-Item $src (Join-Path $appDir $dll) -Force
        }
    }
}

Write-Host ""
Write-Host "Building installer..."
& (Join-Path $Root "scripts\build_installer.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$installer = Join-Path $Root "dist\Biomark TagManager Setup.exe"
$appDir = Join-Path $Root "dist\BiomarkTagManager"

Write-Host ""
Write-Host "All done." -ForegroundColor Green
Write-Host "  Installer (ship this): $installer"
Write-Host "  App folder (dev only): $appDir"
