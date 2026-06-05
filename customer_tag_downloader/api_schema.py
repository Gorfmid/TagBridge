# =============================================================================
# File:        api_schema.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: Introspect BioLogic API payloads (discovery / diagnostics).
# =============================================================================
"""
Introspect BioLogic API payloads to find fields useful for IND export (e.g. site type).

Used by scripts/discover_api_schema.py and optional download-time logging.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

# Terms that may indicate livestock (9) vs slaughter (10) event codes.
_TYPE_HINT_RE = re.compile(
    r"livestock|slaughter|event|facility|premise|site.?type|operation|species|ind",
    re.IGNORECASE,
)


def _walk_keys(obj: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.add(path)
            paths |= _walk_keys(value, path)
    elif isinstance(obj, list) and obj:
        paths |= _walk_keys(obj[0], f"{prefix}[]")
    return paths


def _hint_paths(paths: set[str]) -> list[str]:
    return sorted(p for p in paths if _TYPE_HINT_RE.search(p))


def _sample_values(obj: Any, path: str) -> list[str]:
    """Return up to 3 distinct scalar values at a dotted path ([] = first list item)."""
    parts = path.replace("[]", "").split(".")
    seen: list[str] = []

    def collect(current: Any, index: int) -> None:
        if index >= len(parts):
            if isinstance(current, (str, int, float, bool)) and str(current) not in seen:
                seen.append(str(current))
            return
        key = parts[index]
        if isinstance(current, dict) and key in current:
            collect(current[key], index + 1)
        elif isinstance(current, list) and current:
            collect(current[0], index + 1)

    collect(obj, 0)
    return seen[:3]


def analyze_site_items(items: list[Any]) -> dict[str, Any]:
    dict_items = [i for i in items if isinstance(i, dict)]
    string_items = [i for i in items if isinstance(i, str) and i.strip()]
    keys: set[str] = set()
    for item in dict_items[:20]:
        keys |= _walk_keys(item)
    hints = _hint_paths(keys)
    samples: dict[str, list[str]] = {}
    if dict_items:
        for path in hints:
            vals = _sample_values(dict_items[0], path)
            if vals:
                samples[path] = vals
    return {
        "count": len(items),
        "dict_count": len(dict_items),
        "string_count": len(string_items),
        "sample_string_sites": string_items[:5],
        "all_keys": sorted(keys),
        "hint_paths": hints,
        "hint_samples_first_site": samples,
        "first_site_raw": dict_items[0] if dict_items else None,
    }


def analyze_tag_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    keys: set[str] = set()
    for record in records[:50]:
        keys |= _walk_keys(record)
    hints = _hint_paths(keys)
    samples: dict[str, list[str]] = {}
    if records:
        for path in hints:
            vals = _sample_values(records[0], path)
            if vals:
                samples[path] = vals
    return {
        "count": len(records),
        "all_keys": sorted(keys),
        "hint_paths": hints,
        "hint_samples_first_tag": samples,
        "first_tag_raw": records[0] if records else None,
    }


def format_report(
    *,
    provider: str,
    sites_report: dict[str, Any],
    tags_by_site: dict[str, dict[str, Any]],
) -> str:
    lines = [
        f"BioLogic API schema report — {datetime.now().isoformat(timespec='seconds')}",
        f"Provider: {provider}",
        "",
        "=== authorized_sites ===",
        f"Sites returned: {sites_report['count']} ({sites_report['dict_count']} objects)",
        "",
        "Keys (all):",
        *(f"  {k}" for k in sites_report["all_keys"]),
        "",
    ]
    if sites_report["hint_paths"]:
        lines.append("Keys matching livestock/slaughter/type hints:")
        for path in sites_report["hint_paths"]:
            samples = sites_report["hint_samples_first_site"].get(path, [])
            sample_txt = f"  e.g. {samples!r}" if samples else ""
            lines.append(f"  {path}{sample_txt}")
    else:
        lines.append("No obvious site-type keys on authorized_sites objects.")
    lines.append("")

    for site_id, tag_report in tags_by_site.items():
        lines.extend(
            [
                f"=== tags/{site_id} ===",
                f"Tags sampled: {tag_report['count']}",
                "",
                "Keys (all):",
                *(f"  {k}" for k in tag_report["all_keys"]),
                "",
            ]
        )
        if tag_report["hint_paths"]:
            lines.append("Keys matching hints:")
            for path in tag_report["hint_paths"]:
                samples = tag_report["hint_samples_first_tag"].get(path, [])
                sample_txt = f"  e.g. {samples!r}" if samples else ""
                lines.append(f"  {path}{sample_txt}")
        else:
            lines.append("No obvious type keys on tag records.")
        lines.append("")

    return "\n".join(lines) + "\n"


def write_schema_report(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def write_schema_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
