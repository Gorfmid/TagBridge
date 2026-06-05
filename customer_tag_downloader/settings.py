# =============================================================================
# File:        settings.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: Persist UI settings and optional Windows keyring credentials.
# =============================================================================
"""
Persist UI settings and optional saved credentials.

Settings are stored as JSON under ``%LOCALAPPDATA%\\Biomark\\TagManager\\settings.json``.
Passwords use Windows Credential Manager (``keyring``) when "Save credentials" is enabled.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from customer_tag_downloader.config import settings_path

try:
    import keyring
except ImportError:  # pragma: no cover
    keyring = None  # type: ignore[assignment]

SERVICE_NAME = "BiomarkTagManager"


@dataclass
class AppSettings:
    """Serializable UI preferences; unknown keys in settings.json are ignored on load."""
    provider: str = "biomark"
    login_id: str = ""
    api_email: str = ""
    save_credentials: bool = False
    skip_ssl_verify: bool = False
    save_ui_settings: bool = True
    export_format: str = "csv"
    custom_export_fields: list[str] = field(default_factory=list)
    custom_export_delimiter: str = ","
    export_all_formats: bool = False
    single_file: bool = False
    use_custom_date_range: bool = True
    start_date: str = ""
    end_date: str = ""
    selected_site_ids: list[str] = field(default_factory=list)
    site_groups: dict[str, list[str]] = field(default_factory=dict)
    active_site_group: str = ""
    output_dir: str = ""

    @classmethod
    def load(cls) -> AppSettings:
        path = settings_path()
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        settings = cls(**filtered)
        if not isinstance(settings.selected_site_ids, list):
            settings.selected_site_ids = []
        if not isinstance(settings.custom_export_fields, list):
            settings.custom_export_fields = []
        settings.site_groups = normalize_site_groups(getattr(settings, "site_groups", {}))
        if not isinstance(settings.active_site_group, str):
            settings.active_site_group = ""
        return settings

    def save(self) -> None:
        path = settings_path()
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def normalize_site_groups(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    groups: dict[str, list[str]] = {}
    for name, site_ids in raw.items():
        label = str(name).strip()
        if not label or not isinstance(site_ids, list):
            continue
        ids = sorted({str(site_id).strip().upper() for site_id in site_ids if site_id})
        if ids:
            groups[label] = ids
    return groups


def _credential_key(provider: str, login_id: str) -> str:
    return f"{provider}:{login_id.strip().lower()}"


def save_password(provider: str, login_id: str, password: str) -> None:
    if not keyring:
        raise RuntimeError("keyring is not installed")
    keyring.set_password(SERVICE_NAME, _credential_key(provider, login_id), password)


def load_password(provider: str, login_id: str) -> str | None:
    if not keyring:
        return None
    try:
        return keyring.get_password(SERVICE_NAME, _credential_key(provider, login_id))
    except Exception:  # noqa: BLE001
        return None


def delete_password(provider: str, login_id: str) -> None:
    if not keyring:
        return
    try:
        keyring.delete_password(SERVICE_NAME, _credential_key(provider, login_id))
    except Exception:  # noqa: BLE001
        pass
