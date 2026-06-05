# =============================================================================
# File:        portal_site.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: Fetch and parse RIP portal Site Information for IND export.
# =============================================================================
"""
Fetch site metadata from the Allflex RIP web portal (Site Information table).

The REST ``/api/v1/siteinfo/<site>/`` endpoint returns 404 HTML on Allflex RIP.
The portal exposes Premises Number and Type/Specie at ``GET /sites/<SITE>``.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from requests.exceptions import RequestException

from customer_tag_downloader.api import ApiError, _friendly_network_error, _ssl_verify_option
from customer_tag_downloader.config import ProviderConfig, user_data_dir

_SITE_ROW_RE = re.compile(
    r"<tr><th[^>]*>([^<]+)</th><td[^>]*>(.*?)</td></tr>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")

# Portal fields we never persist (connection credentials).
_SENSITIVE_LABELS = frozenset({"password"})

_LABEL_TO_KEY = {
    "name": "name",
    "site code": "slug",
    "latitude": "latitude",
    "longitude": "longitude",
    "description": "description",
    "type/specie": "type_specie",
    "premises number": "premises_number",
    "location id (lids)": "location_id",
}


def _strip_html(value: str) -> str:
    return _TAG_RE.sub("", value).strip()


def parse_site_information_html(html: str) -> dict[str, str]:
    """Parse the Site Information table from a ``/sites/<code>`` HTML page."""
    if "Site Information" not in html:
        return {}
    start = html.find("Site Information")
    end = html.find("Reader Information", start)
    if end < 0:
        end = start + 4000
    section = html[start:end]

    raw: dict[str, str] = {}
    for match in _SITE_ROW_RE.finditer(section):
        label = _strip_html(match.group(1))
        value = _strip_html(match.group(2))
        if label:
            raw[label] = value

    normalized: dict[str, str] = {}
    for label, value in raw.items():
        key = _LABEL_TO_KEY.get(label.lower())
        if not key:
            continue
        if key == "slug":
            normalized[key] = value.split()[0].upper() if value else ""
        else:
            normalized[key] = value

    if normalized.get("premises_number"):
        normalized["premises_number"] = normalized["premises_number"].upper()
    return normalized


def _site_cache_path(site_code: str) -> Path:
    cache_dir = user_data_dir() / "site_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-]", "_", site_code.upper())
    return cache_dir / f"{safe}.json"


def _read_cache(site_code: str, max_age: timedelta) -> dict[str, str] | None:
    path = _site_cache_path(site_code)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    fetched = payload.get("fetched_at")
    data = payload.get("data")
    if not isinstance(data, dict) or not fetched:
        return None
    try:
        when = datetime.fromisoformat(str(fetched))
    except ValueError:
        return None
    if datetime.now() - when > max_age:
        return None
    return {str(k): str(v) for k, v in data.items()}


def _write_cache(site_code: str, data: dict[str, str]) -> None:
    safe = {k: v for k, v in data.items() if k.lower() not in _SENSITIVE_LABELS}
    path = _site_cache_path(site_code)
    path.write_text(
        json.dumps({"fetched_at": datetime.now().isoformat(timespec="seconds"), "data": safe}, indent=2),
        encoding="utf-8",
    )


def portal_login(
    email: str,
    password: str,
    provider: ProviderConfig,
    verify_ssl: bool = True,
) -> requests.Session:
    """Establish a logged-in portal session (separate from JWT API auth)."""
    email = email.strip().lower()
    if not email or not password:
        raise ApiError("Email and password are required for portal site lookup.")

    base = provider.web_login_url.rsplit("/accounts", 1)[0]
    login_url = provider.web_login_url
    verify = _ssl_verify_option(verify_ssl)
    session = requests.Session()

    try:
        page = session.get(login_url, timeout=30, verify=verify)
        page.raise_for_status()
    except RequestException as exc:
        raise ApiError(_friendly_network_error(exc, login_url)) from exc

    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text)
    if not match:
        raise ApiError("Could not read portal login form (CSRF token missing).")

    try:
        response = session.post(
            login_url,
            data={
                "csrfmiddlewaretoken": match.group(1),
                "username": email,
                "password": password,
                "next": "/sites/",
            },
            headers={"Referer": login_url},
            allow_redirects=True,
            timeout=30,
            verify=verify,
        )
        response.raise_for_status()
    except RequestException as exc:
        raise ApiError(_friendly_network_error(exc, login_url)) from exc

    if "logout" not in response.text.lower():
        raise ApiError("Portal login failed. Check email and password.")
    return session


def fetch_site_from_portal(
    session: requests.Session,
    provider: ProviderConfig,
    site_code: str,
    *,
    verify_ssl: bool = True,
    use_cache: bool = True,
    cache_ttl: timedelta = timedelta(hours=24),
) -> dict[str, str] | None:
    """
    Load Site Information for ``site_code`` from ``/sites/<code>``.

    Returns normalized dict (slug, name, premises_number, type_specie, …) or None
    if the site page is missing.
    """
    site_slug = str(site_code).strip().upper()
    if not site_slug:
        return None

    if use_cache:
        cached = _read_cache(site_slug, cache_ttl)
        if cached and cached.get("type_specie"):
            return cached

    base = provider.web_login_url.rsplit("/accounts", 1)[0]
    url = f"{base}/sites/{site_slug}"
    verify = _ssl_verify_option(verify_ssl)

    try:
        response = session.get(url, timeout=30, verify=verify)
        response.raise_for_status()
    except RequestException as exc:
        raise ApiError(_friendly_network_error(exc, url)) from exc

    if "page not found" in response.text.lower()[:800]:
        return None

    data = parse_site_information_html(response.text)
    if data and use_cache:
        _write_cache(site_slug, data)
    return data or None
