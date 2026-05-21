"""Export tag data to txt, csv, or National Animal Database (.ind) format."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Any

SiteExport = dict[str, Any]

EXPORT_FORMATS = ("txt", "csv", "ind")


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


def _flatten_bio_record(
    record: dict[str, Any],
    site_id: str = "",
    site_name: str = "",
) -> dict[str, str]:
    """Flatten BioLogic API tag JSON into export-friendly columns."""
    if not isinstance(record, dict):
        return {
            "site_id": site_id,
            "site_name": site_name,
            "tag": str(record),
            "detected_at": "",
            "reader_code": "",
            "antenna_code": "",
        }

    slug = _nested_get(record, "antenna.reader.site.slug") or site_id
    name = _nested_get(record, "antenna.reader.site.name") or site_name

    return {
        "site_id": slug.upper() if slug else site_id,
        "site_name": name or site_name,
        "tag": _nested_get(record, "tag", "tag_id", "tagId", "id"),
        "detected_at": _nested_get(
            record, "detected_at", "date", "timestamp", "read_date", "created_at"
        ),
        "reader_code": _nested_get(record, "antenna.reader.code", "reader.code", "reader_code"),
        "antenna_code": _nested_get(record, "antenna.code", "antenna_code"),
    }


def _flatten_records(site_exports: list[SiteExport]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for entry in site_exports:
        site_id = str(entry.get("site_id", ""))
        site_name = str(entry.get("site_name", ""))
        for record in entry.get("data") or []:
            if isinstance(record, dict):
                rows.append(_flatten_bio_record(record, site_id, site_name))
            else:
                rows.append(_flatten_bio_record({}, site_id, site_name) | {"tag": str(record)})
    return rows


def _format_detected_parts(detected_at: str) -> tuple[str, str]:
    """Split ISO datetime into date (YYYY-MM-DD) and time (HH:MM:SS) for IND."""
    if not detected_at:
        return "", ""
    value = detected_at.replace("Z", "").strip()
    if "T" in value:
        date_part, time_part = value.split("T", 1)
        time_part = time_part.split(".")[0]
        return date_part, time_part
    return value, ""


def _to_txt(site_exports: list[SiteExport]) -> str:
    lines: list[str] = []
    for entry in site_exports:
        site_name = entry.get("site_name", entry.get("site_id", "Unknown"))
        site_id = entry.get("site_id", "")
        data = entry.get("data") or []
        lines.append(f"=== Site: {site_name} [{site_id}] ({len(data)} tags) ===")
        if not data:
            lines.append("(no tags)")
            lines.append("")
            continue
        for index, record in enumerate(data, start=1):
            flat = _flatten_bio_record(record if isinstance(record, dict) else {}, site_id, site_name)
            lines.append(
                f"{index}. tag={flat['tag']} | detected={flat['detected_at']} | "
                f"reader={flat['reader_code']} | antenna={flat['antenna_code']}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _to_csv(site_exports: list[SiteExport]) -> str:
    rows = _flatten_records(site_exports)
    buffer = io.StringIO()
    fieldnames = [
        "site_id",
        "site_name",
        "tag",
        "detected_at",
        "reader_code",
        "antenna_code",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def _to_ind(site_exports: list[SiteExport]) -> str:
    """
    National Animal Database (.ind) export.

    Tab-delimited rows for import tools:
    SITE_CODE, TAG_CODE, DATE, TIME, READER, ANTENNA
    """
    lines = [
        "SITE\tTAG\tDATE\tTIME\tREADER\tANTENNA",
    ]
    for entry in site_exports:
        site_id = str(entry.get("site_id", ""))
        site_name = str(entry.get("site_name", ""))
        for record in entry.get("data") or []:
            flat = _flatten_bio_record(
                record if isinstance(record, dict) else {},
                site_id,
                site_name,
            )
            date_part, time_part = _format_detected_parts(flat["detected_at"])
            lines.append(
                "\t".join(
                    [
                        flat["site_id"],
                        flat["tag"],
                        date_part,
                        time_part,
                        flat["reader_code"],
                        flat["antenna_code"],
                    ]
                )
            )
    return "\n".join(lines) + "\n"


def export_data(
    site_exports: list[SiteExport],
    export_format: str,
    single_file: bool,
    output_dir: Path,
) -> list[Path]:
    """Write tag data to disk in the requested format."""
    export_format = export_format.lower().strip()
    if export_format not in EXPORT_FORMATS:
        raise ValueError(f"Unsupported export format: {export_format}")

    return _write_exports(site_exports, [export_format], single_file, output_dir)


def export_all_formats(
    site_exports: list[SiteExport],
    single_file: bool,
    output_dir: Path,
) -> list[Path]:
    """Write txt, csv, and ind files in one run."""
    return _write_exports(site_exports, list(EXPORT_FORMATS), single_file, output_dir)


def _export_filename(site_id: str, export_format: str, date_stamp: str) -> str:
    code = "".join(ch if ch.isalnum() else "_" for ch in site_id.upper()) or "SITE"
    return f"{code}-{date_stamp}.{export_format}"


def _write_exports(
    site_exports: list[SiteExport],
    formats: list[str],
    single_file: bool,
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_stamp = datetime.now().strftime("%Y%m%d")
    converters = {"txt": _to_txt, "csv": _to_csv, "ind": _to_ind}
    written: list[Path] = []

    for export_format in formats:
        convert = converters[export_format]
        if single_file:
            content = convert(site_exports)
            path = output_dir / f"ALL-{date_stamp}.{export_format}"
            path.write_text(content, encoding="utf-8", newline="\n")
            written.append(path)
            continue

        for entry in site_exports:
            site_id = str(entry.get("site_id", "site"))
            content = convert([entry])
            path = output_dir / _export_filename(site_id, export_format, date_stamp)
            path.write_text(content, encoding="utf-8", newline="\n")
            written.append(path)

    return written
