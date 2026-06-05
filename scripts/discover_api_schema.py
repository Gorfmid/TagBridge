#!/usr/bin/env python3
"""
Discover BioLogic API field names using saved Tag Manager settings + keyring password.

No arguments required when you have signed in at least once with "Save credentials".

Writes:
  logs/api_schema_YYYYMMDD_HHMMSS.txt  — human-readable report
  logs/api_schema_YYYYMMDD_HHMMSS.json — raw first site + first tag per site (for dev)
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_tag_downloader import api
from customer_tag_downloader.api_schema import (
    analyze_site_items,
    analyze_tag_records,
    format_report,
    write_schema_json,
    write_schema_report,
)
from customer_tag_downloader.config import logs_dir
from customer_tag_downloader.settings import AppSettings, load_password


def _resolve_email(settings: AppSettings) -> str:
    email = (settings.api_email or settings.login_id or "").strip().lower()
    if not email or "@" not in email:
        raise SystemExit(
            "No saved login email in settings.json. Sign in once in Tag Manager first."
        )
    return email


def main() -> int:
    settings = AppSettings.load()
    email = _resolve_email(settings)
    password = load_password(settings.provider, email)
    if not password:
        raise SystemExit(
            "No saved password in Windows Credential Manager.\n"
            "Open Tag Manager, check 'Save credentials', sign in, then run this script again."
        )

    print(f"Signing in to {settings.provider} as {email}…")
    client = api.BioLogicClient.login(
        email,
        password,
        verify_ssl=not settings.skip_ssl_verify,
        provider_id=settings.provider,
    )
    print("Authenticated.")

    response = client._api_get("/authorized_sites")  # noqa: SLF001 — discovery only
    api._raise_for_status(response)
    payload = api._parse_json(response)

    raw_items: list
    raw_items: list[Any]
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = []
        for key in ("sites", "authorized_sites", "data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                raw_items = value
                break
        if not raw_items:
            raw_items = [payload]
    else:
        raise SystemExit(f"Unexpected authorized_sites format: {type(payload)}")

    sites_report = analyze_site_items(raw_items)
    sites = client.get_sites()
    print(f"Loaded {len(sites)} site(s).")

    probe_site = (settings.selected_site_ids or [s.id for s in sites[:1]])[0]
    site_info = client.get_site_info(probe_site)
    print(f"siteinfo/{probe_site}:", "OK" if site_info else "not available (HTML or error)")
    if site_info:
        print("  keys:", ", ".join(sorted(site_info)))

    site_ids = settings.selected_site_ids or [s.id for s in sites[:3]]
    if not site_ids:
        site_ids = [sites[0].id]

    tags_by_site: dict[str, dict] = {}
    json_payload: dict = {
        "provider": settings.provider,
        "siteinfo_probe": {"site": probe_site, "data": site_info},
        "authorized_sites_analysis": {
            k: v for k, v in sites_report.items() if k != "first_site_raw"
        },
        "authorized_sites_first": sites_report.get("first_site_raw"),
        "tags_by_site": {},
    }

    for site_id in site_ids[:5]:
        print(f"Fetching tags for {site_id}…")
        records = client.get_tags(
            site_id,
            settings.start_date or None,
            settings.end_date or None,
        )
        tag_report = analyze_tag_records(records)
        tags_by_site[site_id] = tag_report
        json_payload["tags_by_site"][site_id] = {
            "analysis": {k: v for k, v in tag_report.items() if k != "first_tag_raw"},
            "first_tag": tag_report.get("first_tag_raw"),
        }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_root = logs_dir()
    txt_path = write_schema_report(
        log_root / f"api_schema_{stamp}.txt",
        format_report(
            provider=settings.provider,
            sites_report=sites_report,
            tags_by_site=tags_by_site,
        ),
    )
    json_path = write_schema_json(log_root / f"api_schema_{stamp}.json", json_payload)

    print(f"\nReport: {txt_path}")
    print(f"JSON:   {json_path}")
    print("\n--- Summary ---")
    print("authorized_sites hint paths:", sites_report["hint_paths"] or "(none)")
    for sid, rep in tags_by_site.items():
        print(f"tags/{sid} hint paths:", rep["hint_paths"] or "(none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
