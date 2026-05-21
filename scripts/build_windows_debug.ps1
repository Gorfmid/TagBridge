# Console build for troubleshooting DLL/load errors on another machine.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = (Get-Command python).Source }

& $Python -m pip install -e . -q
& $Python -m pip install "pyinstaller>=6.0.0" -q

& $Python -m PyInstaller --noconfirm --console --name "CustomerTagDownloader-debug" `
  --paths $Root `
  --hidden-import=customer_tag_downloader.api `
  --hidden-import=customer_tag_downloader.export_data `
  --hidden-import=customer_tag_downloader.services `
  --hidden-import=customer_tag_downloader.ui.main_window `
  (Join-Path $Root "customer_tag_downloader\__main__.py")

Write-Host "Debug build: dist\CustomerTagDownloader-debug\CustomerTagDownloader-debug.exe"
Write-Host "Run from a Command Prompt to see error messages."
