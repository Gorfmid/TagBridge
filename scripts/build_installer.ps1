# Build ONLY the installer (app must already exist in dist\CustomerTagDownloader).
# Run: .\scripts\build_installer.ps1

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

$appDir = Join-Path $Root "dist\BiomarkTagManager"
$exe = Join-Path $appDir "BiomarkTagManager.exe"
if (-not (Test-Path $exe)) {
    throw "App not built yet. Run build.bat first."
}

function Find-Iscc {
    $paths = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $p }
    }
    $keys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    foreach ($key in $keys) {
        $items = Get-ItemProperty $key -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -match "Inno Setup" }
        foreach ($item in $items) {
            if ($item.InstallLocation) {
                $candidate = Join-Path $item.InstallLocation.TrimEnd("\") "ISCC.exe"
                if (Test-Path $candidate) { return $candidate }
            }
        }
    }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$iscc = Find-Iscc
if (-not $iscc) {
    Write-Host "Inno Setup compiler not found. Installing via winget..." -ForegroundColor Yellow
    winget install JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements
    Start-Sleep -Seconds 3
    $iscc = Find-Iscc
}

if (-not $iscc) {
    Write-Host ""
    Write-Host "ERROR: Inno Setup ISCC.exe still not found." -ForegroundColor Red
    Write-Host "Install manually from: https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
    Write-Host "Choose 'Inno Setup 6.x' and install with default options." -ForegroundColor Yellow
    Write-Host "Then run: .\scripts\build_installer.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host "Using Inno Setup: $iscc"
$iss = Join-Path $Root "installer\BiomarkTagManager.iss"
& $iscc "/DAppVersion=$AppVersion" $iss

$installer = Join-Path $Root "dist\Biomark TagManager Setup.exe"
if (-not (Test-Path $installer)) {
    throw "Installer was not created at $installer"
}

$zipName = "BiomarkTagManager-Setup-$AppVersion.zip"
$zipPath = Join-Path $Root "dist\$zipName"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Write-Host "Creating email zip..."
Compress-Archive -LiteralPath $installer -DestinationPath $zipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "Installer created:" -ForegroundColor Green
Write-Host "  $installer"
Write-Host "Email zip:" -ForegroundColor Green
Write-Host "  $zipPath"
