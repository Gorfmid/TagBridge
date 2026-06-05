# =============================================================================
# File:        export_fields.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: Catalog of user-selectable columns for custom export.
# =============================================================================
"""
Field catalog for custom CSV/TSV export.

Each field has a stable ``id`` stored in settings.json. Portal and DCA-style
fields are offered per provider (Biomark vs Allflex RIP). See ``fields_for_provider``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from customer_tag_downloader.export_data import (
    SiteExport,
    _flatten_bio_record,
    _format_detected_parts,
    _format_ind_timestamp,
    _ind_usain_flag,
)
from customer_tag_downloader.ind_event import resolve_ind_event_code, resolve_ind_premise_id

FieldBuilder = Callable[
    [dict[str, str], dict[str, Any], str, str, dict[str, Any] | None, dict[str, Any] | None],
    str,
]

_PROVIDER_BIOMARK = "biomark"
_PROVIDER_ALLFLEX = "allflex"
_BOTH = frozenset({_PROVIDER_BIOMARK, _PROVIDER_ALLFLEX})
_ALLFLEX_ONLY = frozenset({_PROVIDER_ALLFLEX})


def _normalize_provider(provider_id: str | None) -> str:
    key = (provider_id or _PROVIDER_BIOMARK).strip().lower()
    return key if key in _BOTH else _PROVIDER_BIOMARK


@dataclass(frozen=True)
class ExportField:
    id: str
    label: str
    description: str
    build: FieldBuilder
    providers: frozenset[str] = _BOTH


def _site_context(entry: dict[str, Any]) -> tuple[str, str, str, dict[str, Any] | None]:
    site_id = str(entry.get("site_id", ""))
    site_name = str(entry.get("site_name", ""))
    provider = str(entry.get("provider", ""))
    site_info = entry.get("site_info")
    if not isinstance(site_info, dict):
        site_info = None
    return site_id, site_name, provider, site_info


def _ind_context(
    entry: dict[str, Any],
    flat: dict[str, str],
    record: dict[str, Any] | None,
) -> tuple[str, str]:
    site_id, _, provider, site_info = _site_context(entry)
    sample = record if isinstance(record, dict) else None
    event = resolve_ind_event_code(provider, sample, site_id, site_info)
    premise = resolve_ind_premise_id(site_id, flat["site_id"], site_info)
    return event, premise


def _field_site_id(flat, entry, site_id, site_name, site_info, record) -> str:
    return flat.get("site_id", site_id)


def _field_site_name(flat, entry, site_id, site_name, site_info, record) -> str:
    return flat.get("site_name", site_name)


def _field_tag(flat, entry, site_id, site_name, site_info, record) -> str:
    return flat.get("tag", "")


def _field_detected_at(flat, entry, site_id, site_name, site_info, record) -> str:
    return flat.get("detected_at", "")


def _field_detected_date(flat, entry, site_id, site_name, site_info, record) -> str:
    date_part, _ = _format_detected_parts(flat.get("detected_at", ""))
    return date_part


def _field_detected_time(flat, entry, site_id, site_name, site_info, record) -> str:
    _, time_part = _format_detected_parts(flat.get("detected_at", ""))
    return time_part


def _field_reader_code(flat, entry, site_id, site_name, site_info, record) -> str:
    return flat.get("reader_code", "")


def _field_antenna_code(flat, entry, site_id, site_name, site_info, record) -> str:
    return flat.get("antenna_code", "")


def _field_type_specie(flat, entry, site_id, site_name, site_info, record) -> str:
    if site_info:
        return str(site_info.get("type_specie") or "")
    return ""


def _field_premises_number(flat, entry, site_id, site_name, site_info, record) -> str:
    if site_info:
        return str(site_info.get("premises_number") or "")
    return ""


def _field_ind_event_code(flat, entry, site_id, site_name, site_info, record) -> str:
    event, _ = _ind_context(entry, flat, record)
    return event


def _field_ind_premise_id(flat, entry, site_id, site_name, site_info, record) -> str:
    _, premise = _ind_context(entry, flat, record)
    return premise


def _field_ind_timestamp(flat, entry, site_id, site_name, site_info, record) -> str:
    return _format_ind_timestamp(flat.get("detected_at", ""))


def _field_ind_usain_flag(flat, entry, site_id, site_name, site_info, record) -> str:
    return _ind_usain_flag(flat.get("tag", ""))


def _field_ind_electronically_read(flat, entry, site_id, site_name, site_info, record) -> str:
    return "1"


EXPORT_FIELD_CATALOG: tuple[ExportField, ...] = (
    ExportField(
        "site_id",
        "Site code",
        "BioLogic site slug (e.g. JSL, 5RK)",
        _field_site_id,
    ),
    ExportField(
        "site_name",
        "Site name",
        "Display name from tag or portal",
        _field_site_name,
    ),
    ExportField("tag", "Tag ID", "RFID / tag number from API", _field_tag),
    ExportField(
        "detected_at",
        "Detected at",
        "ISO-style read timestamp from API",
        _field_detected_at,
    ),
    ExportField(
        "detected_date",
        "Detected date",
        "Date portion (YYYY-MM-DD)",
        _field_detected_date,
    ),
    ExportField(
        "detected_time",
        "Detected time",
        "Time portion (HH:MM:SS)",
        _field_detected_time,
    ),
    ExportField(
        "reader_code",
        "Reader code",
        "Reader id from tag JSON",
        _field_reader_code,
    ),
    ExportField(
        "antenna_code",
        "Antenna code",
        "Antenna id from tag JSON",
        _field_antenna_code,
    ),
    ExportField(
        "type_specie",
        "Type/Specie",
        "Site Information: facility type (e.g. Packer/Cattle). Allflex: portal page. "
        "Biomark: API siteinfo when available.",
        _field_type_specie,
    ),
    ExportField(
        "premises_number",
        "Premises number",
        "USDA Premises ID (PIN) from site metadata when available",
        _field_premises_number,
    ),
    ExportField(
        "ind_event_code",
        "Event code",
        "9 = livestock, 10 = slaughter (DCA / National Animal Database layout)",
        _field_ind_event_code,
        providers=_ALLFLEX_ONLY,
    ),
    ExportField(
        "ind_premise_id",
        "Premise ID",
        "Resolved USDA PIN or site code for DCA import files",
        _field_ind_premise_id,
        providers=_ALLFLEX_ONLY,
    ),
    ExportField(
        "ind_timestamp",
        "Date/time (compact)",
        "Read time as YYYYMMDDHHmm (DCA import layout)",
        _field_ind_timestamp,
        providers=_ALLFLEX_ONLY,
    ),
    ExportField(
        "ind_usain_flag",
        "USAIN flag",
        "1 if tag starts with 840 (US AIN)",
        _field_ind_usain_flag,
        providers=_ALLFLEX_ONLY,
    ),
    ExportField(
        "ind_electronically_read",
        "Electronically read",
        "1 for reads from an electronic reader (DCA layout)",
        _field_ind_electronically_read,
        providers=_ALLFLEX_ONLY,
    ),
)

EXPORT_FIELD_IDS: tuple[str, ...] = tuple(f.id for f in EXPORT_FIELD_CATALOG)

DEFAULT_CUSTOM_EXPORT_FIELDS: tuple[str, ...] = (
    "site_id",
    "site_name",
    "tag",
    "detected_at",
    "reader_code",
    "antenna_code",
)

_CATALOG_BY_ID = {f.id: f for f in EXPORT_FIELD_CATALOG}

PORTAL_FIELD_IDS: frozenset[str] = frozenset(
    {
        "type_specie",
        "premises_number",
        "ind_event_code",
        "ind_premise_id",
    }
)


def fields_for_provider(provider_id: str | None) -> tuple[ExportField, ...]:
    """Fields available in the column picker for the selected portal."""
    pid = _normalize_provider(provider_id)
    return tuple(f for f in EXPORT_FIELD_CATALOG if pid in f.providers)


def field_ids_for_provider(provider_id: str | None) -> tuple[str, ...]:
    return tuple(f.id for f in fields_for_provider(provider_id))


def default_custom_fields_for_provider(provider_id: str | None) -> list[str]:
    allowed = set(field_ids_for_provider(provider_id))
    return [fid for fid in DEFAULT_CUSTOM_EXPORT_FIELDS if fid in allowed]


def normalize_field_ids(
    field_ids: list[str] | None,
    provider_id: str | None = None,
) -> list[str]:
    """Return valid field ids in catalog order, limited to this portal."""
    allowed = field_ids_for_provider(provider_id)
    if not field_ids:
        return default_custom_fields_for_provider(provider_id)
    wanted = {str(fid).strip() for fid in field_ids if str(fid).strip()}
    return [fid for fid in allowed if fid in wanted]


def field_labels(field_ids: list[str], provider_id: str | None = None) -> list[str]:
    ids = normalize_field_ids(field_ids, provider_id)
    return [_CATALOG_BY_ID[fid].label for fid in ids if fid in _CATALOG_BY_ID]


def needs_site_info(field_ids: list[str]) -> bool:
    return bool(frozenset(normalize_field_ids(field_ids)) & PORTAL_FIELD_IDS)


def build_custom_row(
    entry: SiteExport,
    record: dict[str, Any],
    field_ids: list[str],
) -> dict[str, str]:
    provider = _normalize_provider(str(entry.get("provider", "")))
    site_id, site_name, _, _ = _site_context(entry)
    flat = _flatten_bio_record(record if isinstance(record, dict) else {}, site_id, site_name)
    rec = record if isinstance(record, dict) else None
    _, _, _, site_info = _site_context(entry)
    row: dict[str, str] = {}
    for fid in normalize_field_ids(field_ids, provider):
        field = _CATALOG_BY_ID.get(fid)
        if not field:
            continue
        row[fid] = field.build(flat, entry, site_id, site_name, site_info, rec)
    return row
