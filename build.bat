@echo off
setlocal
cd /d "%~dp0"
echo Building Biomark Tag Manager...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_windows.ps1"
if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)
echo.
echo If no installer was created, run: build_installer.bat
echo   (requires Inno Setup from https://jrsoftware.org/isdl.php)
echo.
pause
