# =============================================================================
# File:        ind_event.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: IND export columns 1 (event code) and 2 (premise PIN) resolution.
# =============================================================================
"""
IND column 1 (event code): 9 = livestock, 10 = slaughter.

Resolves event code and USDA premise PIN from portal site info, optional
ind_site_map.json, and provider defaults. See docs/BiomarkTagManager.txt section 14.
"""

from __future__ import annotations

import re
from typing import Any

from customer_tag_downloader.ind_site_map import ind_site_map_path, load_ind_site_map, lookup_site

# Slaughter customers typically use Allflex RIP; livestock tagging uses Biomark.
IND_EVENT_BY_PROVIDER: dict[str, str] = {
    "allflex": "10",
    "biomark": "9",
}
IND_DEFAULT_EVENT_CODE = "10"
_VALID_EVENT_CODES = frozenset({"9", "10"})

_SITE_CODE_IN_NAME = re.compile(r"\(([^)]+)\)\s*$")


def _nested_get(data: dict[str, Any], *paths: str) -> str:
    for path in paths:
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if current is not None and str(current).strip():
            return str(current).strip()
    return ""


def _code_from_tag_record(record: dict[str, Any] | None) -> str | None:
    """Return event code if the API ever adds a known field on tag or site objects."""
    if not record:
        return None
    direct = _nested_get(
        record,
        "event_code",
        "ind_event_code",
        "eventCode",
    )
    if direct in ("9", "10"):
        return direct
    site_type = _nested_get(
        record,
        "antenna.reader.site.type",
        "antenna.reader.site.site_type",
        "antenna.reader.site.facility_type",
    )
    if not site_type:
        return None
    lowered = site_type.lower()
    if "slaughter" in lowered:
        return "10"
    if "livestock" in lowered:
        return "9"
    return None


def _event_from_type_specie(type_specie: str) -> str | None:
    """Map RIP portal Type/Specie (e.g. Packer/Cattle) to IND event code."""
    lowered = type_specie.lower()
    if any(word in lowered for word in ("packer", "slaughter", "kill", "processor")):
        return "10"
    if any(
        word in lowered
        for word in (
            "livestock",
            "ranch",
            "farm",
            "feeder",
            "feedyard",
            "auction",
            "cow/calf",
            "cow-calf",
            "border",
        )
    ):
        return "9"
    return None


def _premise_from_site_info(site_info: dict[str, Any] | None) -> str | None:
    if not site_info:
        return None
    for key in (
        "premise_id",
        "premise",
        "pin",
        "usda_premise_id",
        "premises_id",
        "premisesId",
        "premises_number",
        "premisesNumber",
        "premise_number",
        "Premises Number",
    ):
        value = site_info.get(key)
        if value is not None and str(value).strip():
            return str(value).strip().upper()
    return None


def _event_from_site_info(site_info: dict[str, Any] | None) -> str | None:
    if not site_info:
        return None
    for key in ("ind_event_code", "event_code", "eventCode"):
        value = site_info.get(key)
        if value is not None and str(value).strip() in _VALID_EVENT_CODES:
            return str(value).strip()
    for key in ("type_specie", "type_species", "type", "species", "site_type", "Type/Specie"):
        value = site_info.get(key)
        if value is not None and str(value).strip():
            from_type = _event_from_type_specie(str(value))
            if from_type:
                return from_type
    return None


def resolve_ind_event_code(
    provider_id: str,
    tag_record: dict[str, Any] | None = None,
    site_code: str = "",
    site_info: dict[str, Any] | None = None,
) -> str:
    """Pick IND event code (9 or 10) for a site export batch."""
    mapped = lookup_site(site_code).get("event_code")
    if mapped in _VALID_EVENT_CODES:
        return mapped
    from_site = _event_from_site_info(site_info)
    if from_site:
        return from_site
    from_api = _code_from_tag_record(tag_record)
    if from_api:
        return from_api
    return IND_EVENT_BY_PROVIDER.get(provider_id.strip().lower(), IND_DEFAULT_EVENT_CODE)


def resolve_ind_premise_id(
    site_code: str,
    fallback: str,
    site_info: dict[str, Any] | None = None,
) -> str:
    """USDA Premises ID (column 2); falls back to BioLogic site code if unmapped."""
    mapped = lookup_site(site_code).get("premise_id")
    if mapped:
        return mapped
    from_site = _premise_from_site_info(site_info)
    if from_site:
        return from_site
    return fallback.strip().upper() if fallback else ""


def parse_reader_site_label(site_value: Any) -> tuple[str, str]:
    """
    Parse ``antenna.reader.site`` from API.

    Allflex returns a display string like ``Creekstone Farms (CRK)``; Biomark may
    return a nested object with slug/name.
    """
    if isinstance(site_value, dict):
        slug = str(site_value.get("slug") or site_value.get("id") or "").strip()
        name = str(site_value.get("name") or slug or "").strip()
        return slug.upper(), name
    if isinstance(site_value, str):
        label = site_value.strip()
        match = _SITE_CODE_IN_NAME.search(label)
        code = match.group(1).upper() if match else ""
        return code, label
    return "", ""


def api_findings_summary(
    provider_id: str,
    sample_tag: dict[str, Any] | None,
    site_code: str = "",
    site_info: dict[str, Any] | None = None,
) -> str:
    """Short note written to logs when exporting IND (no user action required)."""
    code = resolve_ind_event_code(provider_id, sample_tag, site_code, site_info)
    premise = resolve_ind_premise_id(site_code, site_code, site_info)
    mapped = lookup_site(site_code)
    portal = provider_id or "unknown"
    site_key = site_code.strip().upper()
    if site_info and site_info.get("premises_number"):
        map_src = "RIP portal /sites/<code> (or site_cache)"
    elif mapped and load_ind_site_map().get(site_key):
        map_src = "ind_site_map.json"
    elif mapped:
        map_src = "reference site table"
    else:
        map_src = "portal default / site code fallback"
    lines = [
        "IND / DCA field resolution (see docs/BiomarkTagManager.txt section 14)",
        "",
        "Customer-confirmed columns:",
        "  1 Event code (9 livestock, 10 slaughter)",
        "  2 Premise ID (USDA PIN, 7 chars e.g. 00J6HQC for site JSL — not site code JSL)",
        "  3 empty",
        "  4 Date/time YYYYMMDDHHmm",
        "  5 USAIN flag (1 if tag starts with 840)",
        "  6 Tag ID",
        "  7 empty",
        "  8 Electronically read flag (1 for portal reads)",
        "  9-18 empty (10 trailing fields)",
        "",
        "Note: older notes guessed col 5/8 were reader/antenna; customer email says",
        "  USAIN flag and Electronically Read — sample values of 1 match that.",
        "",
        f"This export — site {site_code or '(unknown)'}:",
        f"  Event code: {code} ({'slaughter' if code == '10' else 'livestock'})",
        f"  Premise ID:  {premise}",
        f"  Map source:  {map_src}",
        "",
        "Site metadata: API /siteinfo/ when available; else RIP portal /sites/<code>",
        "  (Premises Number, Type/Specie). Cached under site_cache/ for 24h.",
        "",
        f"  Portal: {portal}",
        f"  siteinfo: {'yes — ' + ', '.join(sorted(site_info)) if site_info else 'not available on this portal'}",
        "  Tag API fields: tag, detected_at, antenna.code, antenna.reader.code,",
        "    antenna.reader.site (object on Biomark, display string on Allflex).",
    ]
    if sample_tag:
        site_val = (
            sample_tag.get("antenna", {}).get("reader", {}).get("site")
            if isinstance(sample_tag.get("antenna"), dict)
            else None
        )
        lines.append(f"  Sample antenna.reader.site: {site_val!r}")
    lines.append(
        f"\nOptional overrides: {ind_site_map_path()} "
        "(ask DCA team to export site code → premise_id + event_code)."
    )
    return "\n".join(lines) + "\n"
