"""Quick check that BioLogic API hosts are reachable from this PC."""
from __future__ import annotations

import sys

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HOSTS = {
    "Biomark": "https://www.biologicsites.com/api/v1/token/",
    "Allflex RIP": "https://allflexrip.biologicsites.com/api/v1/token/",
}


def probe(name: str, url: str) -> None:
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=0)))
    try:
        response = session.post(
            url,
            data={"email": "probe@example.com", "password": "probe"},
            headers={"Accept": "application/json"},
            timeout=15,
            verify=False,
        )
        print(f"{name}: OK (HTTP {response.status_code}) — host is reachable")
        if response.status_code == 401:
            print("  (401 expected with dummy credentials)")
    except requests.exceptions.SSLError as exc:
        print(f"{name}: SSL error — try Skip SSL in the app or fix certs")
        print(f"  {exc}")
    except requests.exceptions.Timeout:
        print(f"{name}: TIMEOUT — host not reachable (firewall/VPN/outage)")
    except requests.exceptions.ConnectionError as exc:
        print(f"{name}: CONNECTION FAILED")
        print(f"  {exc}")


def main() -> int:
    print("Probing BioLogic token endpoints (dummy login, 15s timeout)…\n")
    for name, url in HOSTS.items():
        probe(name, url)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
