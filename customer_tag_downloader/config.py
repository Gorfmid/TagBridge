"""
Application paths, portal definitions, and release version.

Paths resolve to the install folder when frozen (PyInstaller) and fall back to
per-user AppData when Program Files is not writable. Default tag exports go to
``Documents\\Biomark`` (see ``tags_dir()``).
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Biomark Tag Manager"
APP_VERSION_FALLBACK = "1.0.0"


def app_version() -> str:
    """Read version from pyproject.toml (bundled in frozen builds)."""
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass))
    roots.append(Path(__file__).resolve().parent.parent)
    for root in roots:
        path = root / "pyproject.toml"
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if line.strip().startswith("version"):
                match = re.search(r'"([^"]+)"', line)
                if match:
                    return match.group(1)
    return APP_VERSION_FALLBACK
APP_FOLDER = "Biomark"
APP_SUBFOLDER = "TagManager"
EXE_NAME = "BiomarkTagManager.exe"


@dataclass(frozen=True)
class ProviderConfig:
    """BioLogic portal identity and base URLs (API v1.2)."""

    id: str
    label: str
    api_base_url: str
    web_login_url: str


PROVIDERS: dict[str, ProviderConfig] = {
    "biomark": ProviderConfig(
        id="biomark",
        label="Biomark",
        api_base_url="https://www.biologicsites.com/api/v1",
        web_login_url="https://www.biologicsites.com/accounts/login/",
    ),
    "allflex": ProviderConfig(
        id="allflex",
        label="Allflex RIP",
        api_base_url="https://allflexrip.biologicsites.com/api/v1",
        web_login_url="https://allflexrip.biologicsites.com/accounts/login/",
    ),
}


def get_provider(provider_id: str) -> ProviderConfig:
    """Return provider config for ``biomark`` or ``allflex``; raises ValueError if unknown."""
    key = provider_id.strip().lower()
    if key not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider_id}")
    return PROVIDERS[key]


def install_dir() -> Path:
    """Directory containing the exe when frozen; project root when running from source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _writable_root() -> Path:
    """Prefer install dir; fall back to per-user AppData if Program Files is read-only."""
    root = install_dir()
    probe = root / ".write_test"
    try:
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return root
    except OSError:
        pass
    return user_data_dir()


def user_data_dir() -> Path:
    """Per-user data folder (settings); matches default installer layout."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_FOLDER / APP_SUBFOLDER


def default_install_dir() -> Path:
    """Default install location when using the per-user installer (no admin)."""
    return user_data_dir()


def tags_dir() -> Path:
    """Default folder for exported tag files: Documents\\Biomark."""
    if os.name == "nt":
        documents = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents"
    else:
        documents = Path.home() / "Documents"
    path = documents / APP_FOLDER
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    for candidate in (install_dir() / "logs", user_data_dir() / "logs"):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test = candidate / ".write_test"
            test.write_text("", encoding="utf-8")
            test.unlink(missing_ok=True)
            return candidate
        except OSError:
            continue
    return user_data_dir() / "logs"


def settings_path() -> Path:
    path = user_data_dir() / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", install_dir()))
    else:
        base = Path(__file__).resolve().parent
    return base / "resources" / name
