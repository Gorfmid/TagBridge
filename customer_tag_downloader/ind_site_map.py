# =============================================================================
# File:        ind_site_map.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: Optional per-site IND overrides (premise PIN, event code).
# =============================================================================
"""
Optional per-site overrides for IND export (premise PIN, event code).

Save as ``%LOCALAPPDATA%\\Biomark\\TagManager\\ind_site_map.json``.
Example: ``docs/ind_site_map.json.example``. See docs/BiomarkTagManager.txt section 14.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from customer_tag_downloader.config import user_data_dir

_VALID_EVENT_CODES = frozenset({"9", "10"})

# Fallback when portal site lookup fails (normally loaded from /sites/<code>).
# User entries in ind_site_map.json override these.
REFERENCE_SITES: dict[str, dict[str, str]] = {}


def ind_site_map_path() -> Path:
    return user_data_dir() / "ind_site_map.json"


def load_ind_site_map() -> dict[str, dict[str, str]]:
    path = ind_site_map_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}

    normalized: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        site_key = str(key).strip().upper()
        if not site_key:
            continue
        if isinstance(value, str):
            normalized[site_key] = {"premise_id": value.strip()}
            continue
        if not isinstance(value, dict):
            continue
        entry: dict[str, str] = {}
        premise = value.get("premise_id") or value.get("premise") or value.get("pin")
        if premise is not None and str(premise).strip():
            entry["premise_id"] = str(premise).strip().upper()
        event = value.get("event_code") or value.get("event")
        if event is not None and str(event).strip() in _VALID_EVENT_CODES:
            entry["event_code"] = str(event).strip()
        if entry:
            normalized[site_key] = entry
    return normalized


def lookup_site(site_code: str) -> dict[str, str]:
    if not site_code:
        return {}
    key = site_code.strip().upper()
    merged = dict(REFERENCE_SITES.get(key, {}))
    merged.update(load_ind_site_map().get(key, {}))
    return merged
