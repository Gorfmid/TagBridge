"""Test whether API accepts session cookies after web login (manual credentials)."""
import re
import sys

import requests


def main(username: str, password: str) -> None:
    s = requests.Session()
    page = s.get("https://www.biologicsites.com/accounts/login/", timeout=20)
    csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text).group(1)
    login = s.post(
        "https://www.biologicsites.com/accounts/login/",
        data={
            "csrfmiddlewaretoken": csrf,
            "username": username,
            "password": password,
            "next": "/",
        },
        headers={"Referer": "https://www.biologicsites.com/accounts/login/"},
        allow_redirects=False,
        timeout=20,
    )
    print("web login:", login.status_code, login.headers.get("location"))

    for url in [
        "https://www.biologicsites.com/api/v1/authorized_sites/",
        "https://www.biologicsites.com/api/v1/hello/",
        "https://www.biologicsites.com/api/v1/token/",
    ]:
        r = s.get(url, headers={"Accept": "application/json"}, timeout=20)
        print(url, "->", r.status_code, r.text[:100])


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: probe_session_api.py <user> <pass>")
        raise SystemExit(1)
    main(sys.argv[1], sys.argv[2])
