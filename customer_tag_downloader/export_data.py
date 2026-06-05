# =============================================================================
# File:        export_data.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: Export tag data to TXT, CSV, and National Animal Database (.ind).
# =============================================================================
"""
Export tag data to TXT, CSV, or National Animal Database (.ind) format.

Output filenames: ``<SITECODE>-<YYYYMMDD>.<ext>`` or ``ALL-<YYYYMMDD>.<ext>`` when
combined into a single file. IND field reference: ``docs/BiomarkTagManager.txt`` section 14.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Any

from customer_tag_downloader.ind_event import (
    parse_reader_site_label,
    resolve_ind_event_code,
    resolve_ind_premise_id,
)

SiteExport = dict[str, Any]

EXPORT_FORMATS = ("txt", "csv", "ind", "custom")


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

    reader = record.get("antenna") if isinstance(record.get("antenna"), dict) else {}
    reader_obj = reader.get("reader") if isinstance(reader.get("reader"), dict) else {}
    site_slug, site_label = parse_reader_site_label(reader_obj.get("site"))
    slug = _nested_get(record, "antenna.reader.site.slug") or site_slug or site_id
    name = _nested_get(record, "antenna.reader.site.name") or site_label or site_name

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
    """Split ISO datetime into date (YYYY-MM-DD) and time (HH:MM:SS)."""
    if not detected_at:
        return "", ""
    value = detected_at.replace("Z", "").strip()
    if "T" in value:
        date_part, time_part = value.split("T", 1)
        time_part = time_part.split(".")[0]
        return date_part, time_part
    return value, ""


# National Animal Database IND: 9 = livestock, 10 = slaughter (Allflex default).
IND_DEFAULT_EVENT_CODE = "10"
IND_TRAILING_EMPTY_FIELDS = 10


def _format_ind_timestamp(detected_at: str) -> str:
    """Compact YYYYMMDDHHmm timestamp for IND column 4."""
    if not detected_at:
        return ""
    value = detected_at.strip().replace("Z", "")
    if "T" in value:
        date_part, time_part = value.split("T", 1)
        time_part = time_part.split(".")[0].split("+")[0]
        try:
            dt = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%Y%m%d%H%M")
        except ValueError:
            pass
        try:
            dt = datetime.strptime(f"{date_part} {time_part[:5]}", "%Y-%m-%d %H:%M")
            return dt.strftime("%Y%m%d%H%M")
        except ValueError:
            pass
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[:12]


def _ind_usain_flag(tag: str) -> str:
    """USAIN flag (column 5): 1 when tag is a US AIN (840 prefix)."""
    normalized = tag.strip()
    return "1" if normalized.startswith("840") else "0"


def _ind_row(
    *,
    event_code: str,
    premise_id: str,
    timestamp: str,
    usain_flag: str,
    tag_id: str,
    electronically_read: str = "1",
) -> str:
    """
    One IND record: comma-separated, 18 fields, no header.

    Columns: event code, premise ID, (empty), date/time, USAIN flag, tag ID,
    (empty), electronically-read flag, then 10 empty trailing fields.
    """
    fields = [
        event_code,
        premise_id,
        "",
        timestamp,
        usain_flag,
        tag_id,
        "",
        electronically_read,
    ]
    fields.extend([""] * IND_TRAILING_EMPTY_FIELDS)
    return ",".join(fields)


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
    National Animal Database (.ind) export for DCA email import.

    Comma-separated rows (no header), 18 fields per line:
    event code, premise ID, blank, YYYYMMDDHHmm, USAIN flag, tag ID, blank,
    electronically-read flag, then 10 empty trailing fields.

    Event code (column 1) is resolved per site from portal + API (see ind_event.py).
    """
    lines: list[str] = []
    for entry in site_exports:
        site_id = str(entry.get("site_id", ""))
        site_name = str(entry.get("site_name", ""))
        provider = str(entry.get("provider", ""))
        site_info = entry.get("site_info")
        if not isinstance(site_info, dict):
            site_info = None
        records = entry.get("data") or []
        sample = records[0] if records and isinstance(records[0], dict) else None
        event_code = resolve_ind_event_code(provider, sample, site_id, site_info)
        premise_id = resolve_ind_premise_id(site_id, site_id, site_info)
        for record in records:
            flat = _flatten_bio_record(
                record if isinstance(record, dict) else {},
                site_id,
                site_name,
            )
            lines.append(
                _ind_row(
                    event_code=event_code,
                    premise_id=premise_id,
                    timestamp=_format_ind_timestamp(flat["detected_at"]),
                    usain_flag=_ind_usain_flag(flat["tag"]),
                    tag_id=flat["tag"],
                )
            )
    return "\n".join(lines) + ("\n" if lines else "")


def _to_custom(
    site_exports: list[SiteExport],
    field_ids: list[str],
    delimiter: str = ",",
) -> str:
    """User-selected columns; comma (CSV) or tab (TXT) delimited with a header row."""
    from customer_tag_downloader.export_fields import (
        build_custom_row,
        field_labels,
        normalize_field_ids,
    )

    ids = normalize_field_ids(field_ids)
    if not ids:
        return ""

    delim = "\t" if delimiter in ("\t", "tab") else ","
    rows: list[dict[str, str]] = []
    for entry in site_exports:
        for record in entry.get("data") or []:
            rec = record if isinstance(record, dict) else {}
            rows.append(build_custom_row(entry, rec, ids))

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delim, lineterminator="\n")
    writer.writerow(field_labels(ids))
    for row in rows:
        writer.writerow([row.get(fid, "") for fid in ids])
    return buffer.getvalue()


def _custom_file_extension(delimiter: str) -> str:
    return "txt" if delimiter in ("\t", "tab") else "csv"


def export_data(
    site_exports: list[SiteExport],
    export_format: str,
    single_file: bool,
    output_dir: Path,
    *,
    custom_field_ids: list[str] | None = None,
    custom_delimiter: str = ",",
) -> list[Path]:
    """Write tag data to disk in the requested format."""
    export_format = export_format.lower().strip()
    if export_format not in EXPORT_FORMATS:
        raise ValueError(f"Unsupported export format: {export_format}")

    return _write_exports(
        site_exports,
        [export_format],
        single_file,
        output_dir,
        custom_field_ids=custom_field_ids,
        custom_delimiter=custom_delimiter,
    )


def write_site_exports(
    site_export: SiteExport,
    export_format: str,
    output_dir: Path,
    *,
    custom_field_ids: list[str] | None = None,
    custom_delimiter: str = ",",
) -> list[Path]:
    """Write one site's export file(s) to disk immediately."""
    export_format = export_format.lower().strip()
    if export_format == "custom":
        formats = ["custom"]
    elif export_format in EXPORT_FORMATS:
        formats = [export_format]
    else:
        raise ValueError(f"Unsupported export format: {export_format}")
    return _write_exports(
        [site_export],
        formats,
        False,
        output_dir,
        custom_field_ids=custom_field_ids,
        custom_delimiter=custom_delimiter,
    )


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
    *,
    custom_field_ids: list[str] | None = None,
    custom_delimiter: str = ",",
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_stamp = datetime.now().strftime("%Y%m%d")
    written: list[Path] = []

    for export_format in formats:
        if export_format == "custom":
            ext = _custom_file_extension(custom_delimiter)

            def convert(exports: list[SiteExport]) -> str:
                return _to_custom(exports, custom_field_ids or [], custom_delimiter)
        else:
            ext = export_format
            converters = {"txt": _to_txt, "csv": _to_csv, "ind": _to_ind}
            convert = converters[export_format]

        if single_file:
            content = convert(site_exports)
            path = output_dir / f"ALL-{date_stamp}.{ext}"
            path.write_text(content, encoding="utf-8", newline="\n")
            written.append(path)
            continue

        for entry in site_exports:
            site_id = str(entry.get("site_id", "site"))
            content = convert([entry])
            path = output_dir / _export_filename(site_id, ext, date_stamp)
            path.write_text(content, encoding="utf-8", newline="\n")
            written.append(path)

    return written


_SAMPLE_SITE_INFO: dict[str, str] = {
    "type_specie": "Feedyard/Cattle",
    "premises_number": "00J6HQC",
}


def _sample_tag_record(site_code: str, site_name: str, *, tag_suffix: int) -> dict[str, Any]:
    slug = site_code.strip().lower() or "site"
    return {
        "tag": f"840003294655{tag_suffix:03d}",
        "detected_at": "2026-05-16T07:38:00Z",
        "antenna": {
            "code": "1",
            "reader": {
                "code": "RD01",
                "site": {"slug": slug, "name": site_name},
            },
        },
    }


def build_preview_site_exports(
    provider_id: str,
    sites: list[tuple[str, str]],
) -> list[SiteExport]:
    """Synthetic rows for the UI preview pane (one sample tag per site)."""
    exports: list[SiteExport] = []
    for index, (site_code, site_name) in enumerate(sites):
        code = site_code.strip().upper() or "SITE"
        name = site_name.strip() or code
        exports.append(
            {
                "site_id": code,
                "site_name": name,
                "provider": provider_id,
                "site_info": dict(_SAMPLE_SITE_INFO),
                "data": [_sample_tag_record(code, name, tag_suffix=500 + index)],
            }
        )
    return exports


def _preview_line_budget(export_format: str, site_count: int, export_all_formats: bool) -> int:
    if export_all_formats:
        return min(28, 8 + site_count * 2)
    if export_format == "txt":
        return min(24, 2 + site_count * 4)
    if export_format == "csv" or export_format == "custom":
        return min(24, 2 + site_count)
    if export_format == "ind":
        return min(24, 2 + site_count * 2)
    return min(20, 1 + site_count)


def render_export_preview(
    site_exports: list[SiteExport],
    export_format: str,
    *,
    custom_field_ids: list[str] | None = None,
    custom_delimiter: str = ",",
    export_all_formats: bool = False,
    max_lines: int | None = None,
    header_comment: str = "",
) -> str:
    """Format pre-built site export rows for the preview pane."""
    if not site_exports:
        return header_comment + "(no tag reads in the selected date range)"

    converters: dict[str, Any] = {
        "txt": _to_txt,
        "csv": _to_csv,
        "ind": _to_ind,
    }
    line_cap = max_lines or _preview_line_budget(
        export_format, len(site_exports), export_all_formats
    )

    if export_all_formats:
        chunks: list[str] = []
        if header_comment:
            chunks.append(header_comment.rstrip())
            chunks.append("")
        chunks.append(
            f"Preview: {len(site_exports)} site(s) — writes .txt, .csv, and .ind per site.",
        )
        chunks.append("")
        for fmt in ("txt", "csv", "ind"):
            chunks.append(f"--- {fmt.upper()} ---")
            chunks.append(converters[fmt](site_exports).rstrip())
            chunks.append("")
        body = "\n".join(chunks).strip()
    elif export_format == "custom":
        body = _to_custom(site_exports, custom_field_ids or [], custom_delimiter).strip()
        if not body:
            body = "(select at least one column)"
        if header_comment:
            body = header_comment.rstrip() + "\n" + body
    elif export_format == "ind":
        body = _to_ind(site_exports).strip()
        if header_comment:
            body = header_comment.rstrip() + "\n" + body
        if body:
            body = "# IND (no header row)\n" + body
    else:
        convert = converters.get(export_format, _to_csv)
        body = convert(site_exports).strip()
        if header_comment:
            body = header_comment.rstrip() + "\n" + body

    lines = body.splitlines()
    if len(lines) > line_cap:
        lines = lines[:line_cap] + ["…"]
    return "\n".join(lines)


def preview_export_sample(
    export_format: str,
    *,
    provider_id: str = "biomark",
    custom_field_ids: list[str] | None = None,
    custom_delimiter: str = ",",
    export_all_formats: bool = False,
    sites: list[tuple[str, str]] | None = None,
    max_lines: int | None = None,
) -> str:
    """
    Example file body for the UI preview (illustrative sample rows only).

    ``sites`` is a list of (site_id, site_name) for each selected site.
    """
    site_list = sites or []
    if not site_list:
        return ""

    exports = build_preview_site_exports(provider_id, site_list)
    return render_export_preview(
        exports,
        export_format,
        custom_field_ids=custom_field_ids,
        custom_delimiter=custom_delimiter,
        export_all_formats=export_all_formats,
        max_lines=max_lines,
    )
