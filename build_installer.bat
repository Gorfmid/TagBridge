@echo off
setlocal
cd /d "%~dp0"
echo Building installer only (app must exist in dist\BiomarkTagManager)...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_installer.ps1"
if errorlevel 1 (
    echo.
    echo Installer build failed.
    echo Install Inno Setup from https://jrsoftware.org/isdl.php then run this again.
    pause
    exit /b 1
)
echo.
pause
