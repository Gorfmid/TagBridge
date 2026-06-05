# =============================================================================
# File:        services.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: Download tags and write export files (orchestration for the GUI).
# =============================================================================
"""
High-level download workflow used by the GUI.

Fetches tag JSON per selected site, then writes export files via ``export_data``.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Protocol

from customer_tag_downloader import api
from customer_tag_downloader.config import logs_dir
from customer_tag_downloader.export_data import export_all_formats, export_data, write_site_exports
from customer_tag_downloader.ind_event import (
    api_findings_summary,
    resolve_ind_event_code,
    resolve_ind_premise_id,
)
from customer_tag_downloader.logging_util import append_log

_PREVIEW_MAX_SITES = 8
_PREVIEW_MAX_TAGS_PER_SITE = 5


class DownloadProgressReporter(Protocol):
    def begin(self, sites: list[tuple[str, str]], start_date: str, end_date: str) -> None: ...

    def site_started(
        self,
        index: int,
        total: int,
        site_id: str,
        site_name: str,
        *,
        percent: float,
        eta_seconds: float | None,
    ) -> None: ...

    def site_chunk(
        self,
        index: int,
        total: int,
        site_id: str,
        chunk_index: int,
        chunk_total: int,
        *,
        percent: float,
        eta_seconds: float | None,
    ) -> None: ...

    def site_saved(
        self,
        index: int,
        total: int,
        site_id: str,
        tag_count: int,
        paths: list[str],
        elapsed_seconds: float,
        *,
        percent: float,
        eta_seconds: float | None,
    ) -> None: ...

    def combining(self, *, percent: float) -> None: ...


def fetch_preview_site_exports(
    client: api.BioLogicClient,
    sites: list[tuple[str, str]],
    provider_id: str,
    start_date: str | None,
    end_date: str | None,
    *,
    need_site_info: bool = False,
) -> list[dict[str, Any]]:
    """Load a small sample of real tag reads for the export preview pane."""
    site_exports: list[dict[str, Any]] = []
    for site_id, site_name in sites[:_PREVIEW_MAX_SITES]:
        data = client.get_tags(site_id, start_date, end_date)
        if not data:
            continue
        site_info = client.get_site_info(site_id) if need_site_info else None
        site_exports.append(
            {
                "site_id": site_id,
                "site_name": site_name,
                "provider": provider_id,
                "site_info": site_info,
                "data": data[:_PREVIEW_MAX_TAGS_PER_SITE],
            }
        )
    return site_exports


def _estimate_eta(completed_seconds: list[float], remaining_units: float) -> float | None:
    if not completed_seconds or remaining_units <= 0:
        return None
    average = sum(completed_seconds) / len(completed_seconds)
    return average * remaining_units


def _overall_percent(site_index: int, site_total: int, chunk_index: int, chunk_total: int) -> float:
    if site_total <= 0:
        return 0.0
    site_fraction = site_index + (chunk_index / max(chunk_total, 1))
    return min(100.0, (site_fraction / site_total) * 100.0)


def download_tags(
    client: api.BioLogicClient,
    sites: list[api.Site],
    export_format: str,
    single_file: bool,
    output_dir: Path,
    start_date: str | None = None,
    end_date: str | None = None,
    export_all_formats: bool = False,
    provider_id: str = "biomark",
    custom_export_fields: list[str] | None = None,
    custom_delimiter: str = ",",
    progress: DownloadProgressReporter | None = None,
) -> list[Path]:
    """
    Download tags for each site and export to disk.

    Returns list of written file paths. Per-site files are written as each site
    finishes unless ``single_file`` is enabled.
    """
    from customer_tag_downloader.export_fields import needs_site_info, normalize_field_ids

    if not sites:
        return []

    custom_fields = (
        normalize_field_ids(custom_export_fields, provider_id)
        if export_format == "custom"
        else []
    )
    need_site_info = (
        export_format == "ind"
        or export_all_formats
        or (export_format == "custom" and needs_site_info(custom_fields))
    )
    site_labels = [(site.id, site.name) for site in sites]
    start_label = start_date or ""
    end_label = end_date or ""
    if progress:
        progress.begin(site_labels, start_label, end_label)

    written: list[Path] = []
    pending_exports: list[dict[str, Any]] = []
    all_exports: list[dict[str, Any]] = []
    site_durations: list[float] = []
    total_sites = len(sites)

    for index, site in enumerate(sites):
        site_started = time.monotonic()
        remaining_sites = total_sites - index
        eta = _estimate_eta(site_durations, remaining_sites)
        if progress:
            progress.site_started(
                index,
                total_sites,
                site.id,
                site.name,
                percent=_overall_percent(index, total_sites, 0, 1),
                eta_seconds=eta,
            )

        def on_chunk(chunk_index: int, chunk_total: int, *, site_idx=index, site_code=site.id) -> None:
            if not progress:
                return
            progress.site_chunk(
                site_idx,
                total_sites,
                site_code,
                chunk_index,
                chunk_total,
                percent=_overall_percent(site_idx, total_sites, chunk_index - 1, chunk_total),
                eta_seconds=_estimate_eta(site_durations, remaining_sites),
            )

        data = client.get_tags(site.id, start_date, end_date, on_chunk=on_chunk)
        site_info = client.get_site_info(site.id) if need_site_info else None
        if need_site_info and (export_format == "ind" or export_all_formats):
            type_specie = ""
            if isinstance(site_info, dict):
                type_specie = str(site_info.get("type_specie") or "")
            event = resolve_ind_event_code(provider_id, None, site.id, site_info)
            premise = resolve_ind_premise_id(site.id, site.id, site_info)
            source = "portal" if type_specie else "default (portal Type/Specie not loaded — rebuild app?)"
            append_log(
                f"IND {site.id}: event={event} premise={premise} "
                f"Type/Specie={type_specie!r} ({source})"
            )

        site_export = {
            "site_id": site.id,
            "site_name": site.name,
            "provider": provider_id,
            "site_info": site_info,
            "data": data,
        }
        elapsed = time.monotonic() - site_started
        site_durations.append(elapsed)
        all_exports.append(site_export)

        if single_file:
            pending_exports.append(site_export)
            if progress:
                progress.site_saved(
                    index,
                    total_sites,
                    site.id,
                    len(data),
                    [],
                    elapsed,
                    percent=_overall_percent(index + 1, total_sites, 0, 1),
                    eta_seconds=_estimate_eta(site_durations, total_sites - index - 1),
                )
            continue

        if export_all_formats:
            site_paths = export_all_formats([site_export], False, output_dir)
        else:
            site_paths = write_site_exports(
                site_export,
                export_format,
                output_dir,
                custom_field_ids=custom_fields,
                custom_delimiter=custom_delimiter,
            )
        written.extend(site_paths)
        append_log(f"Saved {site.id}: {', '.join(str(path) for path in site_paths)}")
        if progress:
            progress.site_saved(
                index,
                total_sites,
                site.id,
                len(data),
                [str(path) for path in site_paths],
                elapsed,
                percent=_overall_percent(index + 1, total_sites, 0, 1),
                eta_seconds=_estimate_eta(site_durations, total_sites - index - 1),
            )

    if export_format == "ind" or export_all_formats:
        sample = None
        for entry in all_exports:
            batch = entry.get("data") or []
            if batch and isinstance(batch[0], dict):
                sample = batch[0]
                break
        first = all_exports[0] if all_exports else {}
        note_path = logs_dir() / "ind_event_code.txt"
        note_path.write_text(
            api_findings_summary(
                provider_id,
                sample,
                str(first.get("site_id", "")),
                first.get("site_info") if isinstance(first.get("site_info"), dict) else None,
            ),
            encoding="utf-8",
        )

    if single_file:
        if progress:
            progress.combining(percent=95.0)
        if export_all_formats:
            written = export_all_formats(pending_exports, True, output_dir)
        else:
            written = export_data(
                pending_exports,
                export_format,
                True,
                output_dir,
                custom_field_ids=custom_fields,
                custom_delimiter=custom_delimiter,
            )
        for path in written:
            append_log(f"Saved combined file: {path}")

    return written
