# =============================================================================
# File:        api.py
# Project:     Biomark Tag Manager
# Author:      Keith Abbott
# Version:     1.31
# Description: BioLogic REST API v1.2 client and portal site metadata fetch.
# =============================================================================
"""
BioLogic Sites REST API client (v1.2).

Authenticates with ``POST /api/v1/token/`` (email + password), then uses a JWT
bearer token for ``/hello/``, ``/authorized_sites/``, and ``/tags/<site>/``.
All request URLs use trailing slashes per BioLogic API requirements.

Credentials and tokens are held only in memory for the lifetime of ``BioLogicClient``.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode, urlparse

import certifi
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, RequestException, SSLError, Timeout
from urllib3.util.retry import Retry

from customer_tag_downloader.config import ProviderConfig, get_provider

REQUEST_TIMEOUT = 30
TAGS_CONNECT_TIMEOUT = 30
TAGS_READ_TIMEOUT = 600
TAGS_CHUNK_DAYS = 3
TAGS_FETCH_RETRIES = 3
_NO_RETRIES = Retry(total=0, connect=0, read=0, redirect=0)
_TAGS_TIMEOUT = (TAGS_CONNECT_TIMEOUT, TAGS_READ_TIMEOUT)
ChunkProgressCallback = Callable[[int, int], None]


class ApiError(Exception):
    """API or transport failure (HTTP error body, JSON parse, SSL, or timeout)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class Site:
    """Site authorized for the user. id is the 3-character site slug/code."""

    id: str
    name: str


@dataclass
class BioLogicClient:
    """Authenticated API client using a JWT access token (SimpleJWT ``access`` field)."""

    token: str | None = None
    _session: requests.Session | None = field(default=None, repr=False, compare=False)
    _portal_session: requests.Session | None = field(default=None, repr=False, compare=False)
    _login_email: str = field(default="", repr=False, compare=False)
    _login_password: str = field(default="", repr=False, compare=False)
    auth_method: str = "token"
    verify_ssl: bool = True
    provider: ProviderConfig = field(default_factory=lambda: get_provider("biomark"))

    @classmethod
    def login(
        cls,
        email: str,
        password: str,
        verify_ssl: bool = True,
        provider_id: str = "biomark",
    ) -> BioLogicClient:
        """Sign in with the account email address and password."""
        email = email.strip().lower()
        if not email or not password:
            raise ApiError("Email and password are required.")

        provider = get_provider(provider_id)
        token = _request_access_token(email, password, verify_ssl, provider)
        return cls(
            token=token,
            auth_method="token",
            verify_ssl=verify_ssl,
            provider=provider,
            _login_email=email,
            _login_password=password,
        )

    def test_connection(self) -> bool:
        """Verify API connectivity; returns True when response is 'Hello World!'."""
        response = self._api_get("/hello")
        _raise_for_status(response)

        payload = _parse_json(response)
        message: str | None = None
        if isinstance(payload, str):
            message = payload
        elif isinstance(payload, dict):
            for key in ("message", "result", "data", "hello", "detail"):
                value = payload.get(key)
                if isinstance(value, str):
                    message = value
                    break

        if message is None:
            message = response.text.strip()

        normalized = message.strip().rstrip("!").lower().replace(",", "")
        if normalized not in ("hello world", "hello world!"):
            raise ApiError(f"Unexpected hello response: {message!r}")

        return True

    def get_sites(self) -> list[Site]:
        """Retrieve sites the user is authorized to access."""
        response = self._api_get("/authorized_sites")
        _raise_for_status(response)
        payload = _parse_json(response)

        raw_items: list[Any]
        if isinstance(payload, list):
            raw_items = payload
        elif isinstance(payload, dict):
            for key in ("sites", "authorized_sites", "data", "results", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    raw_items = value
                    break
            else:
                raw_items = [payload]
        else:
            raise ApiError("Unexpected authorized_sites response format.")

        sites: list[Site] = []
        for item in raw_items:
            site = _normalize_site(item)
            if site:
                sites.append(site)

        if not sites:
            raise ApiError("No sites returned for this account.")

        sites.sort(key=lambda s: s.name.lower())
        return sites

    def get_tags(
        self,
        site_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        *,
        on_chunk: ChunkProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve tag detections for a site between begin_dt and end_dt."""
        if not site_id:
            raise ApiError("Site code is required.")

        site_slug = str(site_id).strip().upper()
        if start_date and end_date:
            start = _parse_iso_date(start_date)
            end = _parse_iso_date(end_date)
            if start > end:
                raise ApiError("Start date must be on or before end date.")
            chunks = _iter_date_chunks(start, end, TAGS_CHUNK_DAYS)
            if len(chunks) > 1:
                records: list[dict[str, Any]] = []
                for chunk_index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
                    if on_chunk:
                        on_chunk(chunk_index, len(chunks))
                    records.extend(
                        self._fetch_tags(
                            site_slug,
                            chunk_start.isoformat(),
                            chunk_end.isoformat(),
                        )
                    )
                return _dedupe_tag_records(records)
            if on_chunk:
                on_chunk(1, 1)

        return self._fetch_tags(site_slug, start_date, end_date)

    def _fetch_tags(
        self,
        site_slug: str,
        start_date: str | None,
        end_date: str | None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if start_date:
            params["begin_dt"] = start_date
        if end_date:
            params["end_dt"] = end_date

        path = f"/tags/{site_slug}"
        if params:
            path = f"{path}?{urlencode(params)}"

        last_error: ApiError | None = None
        payload: Any = None
        for attempt in range(1, TAGS_FETCH_RETRIES + 1):
            try:
                response = self._api_get(path, timeout=_TAGS_TIMEOUT)
                _raise_for_status(response)
                payload = _parse_json(response)
                break
            except ApiError as exc:
                last_error = exc
                if attempt >= TAGS_FETCH_RETRIES or not _is_retryable_tag_error(exc):
                    raise
                time.sleep(min(2 ** (attempt - 1), 8))
        else:
            raise last_error or ApiError("Failed to fetch tags.")

        if isinstance(payload, list):
            return [_coerce_record(item) for item in payload]

        if isinstance(payload, dict):
            for key in ("tags", "data", "results", "items", "records"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [_coerce_record(item) for item in value]
            return [_coerce_record(payload)]

        raise ApiError("Unexpected tags response format.")

    def get_site_info(self, site_id: str) -> dict[str, Any] | None:
        """
        Site metadata for IND export and display.

        Tries API v1.2 ``GET /siteinfo/<site>/`` first, then the RIP portal page
        ``GET /sites/<site>`` (Allflex) which includes Premises Number and Type/Specie.
        """
        site_slug = str(site_id).strip().upper()
        if not site_slug:
            return None

        from_api = self._get_site_info_api(site_slug)
        if from_api:
            return from_api
        return self._get_site_info_portal(site_slug)

    def _get_site_info_api(self, site_slug: str) -> dict[str, Any] | None:
        try:
            response = self._api_get(f"/siteinfo/{site_slug}")
            _raise_for_status(response)
            if "page not found" in response.text.lower()[:500]:
                return None
            payload = _parse_json(response)
        except ApiError:
            return None

        if isinstance(payload, list) and payload:
            item = payload[0]
            return dict(item) if isinstance(item, dict) else None
        if isinstance(payload, dict):
            return payload
        return None

    def _ensure_portal_session(self) -> requests.Session:
        if self._portal_session is not None:
            return self._portal_session
        if not self._login_email or not self._login_password:
            raise ApiError("Portal session unavailable. Sign in again.")

        from customer_tag_downloader.portal_site import portal_login

        self._portal_session = portal_login(
            self._login_email,
            self._login_password,
            self.provider,
            verify_ssl=self.verify_ssl,
        )
        return self._portal_session

    def _get_site_info_portal(self, site_slug: str) -> dict[str, Any] | None:
        from customer_tag_downloader.portal_site import fetch_site_from_portal

        try:
            session = self._ensure_portal_session()
            return fetch_site_from_portal(
                session,
                self.provider,
                site_slug,
                verify_ssl=self.verify_ssl,
            )
        except ApiError:
            return None

    def _api_get(
        self,
        path: str,
        *,
        timeout: float | tuple[float, float] | None = None,
    ) -> requests.Response:
        url = _api_url(path, self.provider.api_base_url)
        headers = {"Accept": "application/json"}
        verify = _ssl_verify_option(self.verify_ssl)
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            return _http_get(
                url,
                headers=headers,
                verify=verify,
                timeout=timeout,
                session=self._ensure_api_session(),
            )
        if self._session:
            return _http_get(
                url, headers=headers, verify=verify, session=self._session, timeout=timeout
            )
        raise ApiError("Not authenticated. Sign in first.")

    def _ensure_api_session(self) -> requests.Session:
        if self._session is None:
            self._session = _http_session()
        return self._session


def get_token(email: str, password: str, provider_id: str = "biomark") -> str:
    """Authenticate and return a JWT access token (backward compatible helper)."""
    return BioLogicClient.login(email, password, provider_id=provider_id).token or ""


def test_connection(token: str) -> bool:
    """Backward compatible helper using a bearer token only."""
    client = BioLogicClient(token=token)
    return client.test_connection()


def get_sites(token: str) -> list[Site]:
    """Backward compatible helper using a bearer token only."""
    return BioLogicClient(token=token).get_sites()


def get_tags(
    token: str,
    site_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Backward compatible helper using a bearer token only."""
    return BioLogicClient(token=token).get_tags(site_id, start_date, end_date)


def _ssl_verify_option(verify_ssl: bool) -> bool | str:
    if not verify_ssl:
        return False
    # Packaged builds use certifi; dev installs can use the Windows cert store.
    if getattr(sys, "frozen", False):
        return certifi.where()
    return True


def _http_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=_NO_RETRIES)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _friendly_network_error(exc: RequestException, url: str) -> str:
    host = urlparse(url).hostname or url
    if isinstance(exc, Timeout) or (
        isinstance(exc, ConnectionError) and "timed out" in str(exc).lower()
    ):
        return (
            f"Could not reach {host} (connection timed out).\n\n"
            "The server may be down, blocked by a firewall, or unreachable without VPN. "
            "If you use Allflex RIP, switch the Portal dropdown to Allflex RIP."
        )
    if isinstance(exc, ConnectionError):
        detail = str(exc).strip()
        if "Failed to resolve" in detail or "getaddrinfo" in detail:
            return f"Could not resolve host name {host}. Check the portal URL and DNS."
        if "Max retries exceeded" in detail:
            return (
                f"Could not connect to {host}.\n\n"
                "This is usually a network or firewall issue, not wrong credentials. "
                "Try VPN, check corporate firewall rules, or use the Allflex RIP portal "
                "if your account is on that host."
            )
        return f"Could not connect to {host}: {detail}"
    return f"Network error talking to {host}: {exc}"


def _ssl_error_message() -> str:
    return (
        "SSL certificate verification failed. This is common on corporate networks "
        "that inspect HTTPS traffic.\n\n"
        "Check 'Skip SSL certificate verification' on the login screen and sign in "
        "again (use only on trusted networks)."
    )


def _parse_iso_date(value: str) -> date:
    parsed = date.fromisoformat(value.strip()[:10])
    year = parsed.year
    if 0 <= year < 100:
        parsed = parsed.replace(year=year + 2000)
    return parsed


def _iter_date_chunks(
    start: date,
    end: date,
    chunk_days: int,
) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def _is_retryable_tag_error(exc: ApiError) -> bool:
    message = str(exc).lower()
    if exc.status_code in (408, 429, 500, 502, 503, 504):
        return True
    return any(
        phrase in message
        for phrase in (
            "timed out",
            "timeout",
            "connection terminated",
            "connection reset",
            "temporarily unavailable",
            "max retries exceeded",
        )
    )


def _dedupe_tag_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for record in records:
        tag = str(record.get("tag") or record.get("tag_id") or "")
        detected = str(
            record.get("detected_at")
            or record.get("date")
            or record.get("timestamp")
            or ""
        )
        key = (tag, detected)
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def _http_get(
    url: str,
    *,
    headers: dict[str, str],
    verify: bool | str,
    session: requests.Session | None = None,
    timeout: float | tuple[float, float] | None = None,
) -> requests.Response:
    http = session or _http_session()
    request_timeout = timeout if timeout is not None else REQUEST_TIMEOUT
    try:
        return http.get(url, headers=headers, timeout=request_timeout, verify=verify)
    except SSLError as exc:
        raise ApiError(_ssl_error_message()) from exc
    except RequestException as exc:
        raise ApiError(_friendly_network_error(exc, url)) from exc


def _http_post(
    url: str,
    *,
    data: dict[str, str],
    headers: dict[str, str],
    verify: bool | str,
    session: requests.Session | None = None,
    allow_redirects: bool = True,
) -> requests.Response:
    http = session or _http_session()
    try:
        return http.post(
            url,
            data=data,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            verify=verify,
            allow_redirects=allow_redirects,
        )
    except SSLError as exc:
        raise ApiError(_ssl_error_message()) from exc
    except RequestException as exc:
        raise ApiError(_friendly_network_error(exc, url)) from exc


def _request_access_token(
    email: str, password: str, verify_ssl: bool, provider: ProviderConfig
) -> str:
    verify = _ssl_verify_option(verify_ssl)
    token_url = _api_url("/token", provider.api_base_url)
    response = _http_post(
        token_url,
        data={"email": email, "password": password},
        headers={"Accept": "application/json"},
        verify=verify,
    )
    _raise_for_status(response)
    return _extract_token(_parse_json(response))


def _api_url(path: str, api_base_url: str) -> str:
    path = path if path.startswith("/") else f"/{path}"
    base = api_base_url.rstrip("/")
    if "?" in path:
        route, query = path.split("?", 1)
        if not route.endswith("/"):
            route = f"{route}/"
        return f"{base}{route}?{query}"
    if not path.endswith("/"):
        path = f"{path}/"
    return f"{base}{path}"


def _ensure_json_response(response: requests.Response) -> None:
    content_type = (response.headers.get("content-type") or "").lower()
    if "html" in content_type or response.text.lstrip().startswith("<!"):
        raise ApiError(
            "Unexpected HTML response from API. "
            "Check that endpoints use trailing slashes (e.g. /api/v1/token/).",
            response.status_code,
        )


def _parse_json(response: requests.Response) -> Any:
    _ensure_json_response(response)
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise ApiError(
            f"Invalid JSON response (HTTP {response.status_code}): {response.text[:200]}",
            response.status_code,
        ) from exc


def _api_error_detail(response: requests.Response) -> str:
    try:
        _ensure_json_response(response)
        payload = response.json()
    except (json.JSONDecodeError, ApiError):
        return response.text.strip() or response.reason

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list) and detail:
            first = detail[0]
            if isinstance(first, dict):
                return str(first.get("msg") or first)
            return str(first)
        return (
            payload.get("message")
            or payload.get("error")
            or response.text.strip()
            or response.reason
        )
    return response.text.strip() or response.reason


def _raise_for_status(response: requests.Response) -> None:
    if response.ok:
        return
    raise ApiError(_api_error_detail(response), response.status_code)


def _extract_token(payload: Any) -> str:
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    if not isinstance(payload, dict):
        raise ApiError("Token response was not recognized.")

    for key in ("access", "token", "access_token", "accessToken", "jwt", "id_token"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_token(data)

    raise ApiError("No access token found in authentication response.")


def _normalize_site(item: Any) -> Site | None:
    if isinstance(item, str) and item.strip():
        slug = item.strip().upper()
        return Site(id=slug, name=slug)

    if isinstance(item, dict):
        site_id = (
            item.get("slug")
            or item.get("id")
            or item.get("siteId")
            or item.get("site_id")
            or item.get("code")
        )
        name = (
            item.get("name")
            or item.get("siteName")
            or item.get("site_name")
            or item.get("label")
            or site_id
        )
        if site_id is not None:
            return Site(id=str(site_id).upper(), name=str(name or site_id))

    return None


def _coerce_record(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    return {"value": item}
