# Biomark Tag Manager

Windows desktop app for downloading and exporting RFID tag data from BioLogic portals (Biomark and Allflex RIP).

## Quick start

```powershell
cd TagBridge
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m customer_tag_downloader
```

## Build installer

```powershell
.\build.bat
```

Ship: `dist\Biomark TagManager Setup.exe` or `dist\BiomarkTagManager-Setup-<version>.zip` (for email)

## Documentation

All project documentation is in one file:

**[docs/BiomarkTagManager.txt](docs/BiomarkTagManager.txt)**

Includes API reference, GUI workflow, IND/DCA field definitions (with data sources per column),
build steps, module reference, and troubleshooting.

## Version

See `version` in [pyproject.toml](pyproject.toml). The UI footer displays the same value at runtime.
