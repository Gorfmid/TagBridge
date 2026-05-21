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

Ship: `dist\Biomark TagManager Setup.exe`

## Documentation

Full project documentation (SiteShift-style): **[docs/BiomarkTagManager.txt](docs/BiomarkTagManager.txt)**

Topics covered: API endpoints, GUI workflow, export formats, paths, build steps, module reference, troubleshooting.

## Version

See `version` in [pyproject.toml](pyproject.toml). The UI footer displays the same value at runtime.
