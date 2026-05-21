"""High-level operations used by the UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from customer_tag_downloader import api
from customer_tag_downloader.export_data import export_data


def download_tags(
    client: api.BioLogicClient,
    sites: list[api.Site],
    export_format: str,
    single_file: bool,
    output_dir: Path,
    start_date: str | None = None,
    end_date: str | None = None,
    export_all_formats: bool = False,
) -> list[Path]:
    """Download tags for each site and export to disk."""
    site_exports: list[dict[str, Any]] = []
    for site in sites:
        data = client.get_tags(site.id, start_date, end_date)
        site_exports.append(
            {
                "site_id": site.id,
                "site_name": site.name,
                "data": data,
            }
        )
    if export_all_formats:
        from customer_tag_downloader.export_data import export_all_formats as write_all

        return write_all(site_exports, single_file, output_dir)
    return export_data(site_exports, export_format, single_file, output_dir)
