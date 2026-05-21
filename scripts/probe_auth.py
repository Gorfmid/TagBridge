"""Probe BioLogic auth endpoints (no credentials stored)."""
import re
import sys

import requests  # noqa: E402

def main() -> None:
    r = requests.get("https://www.biologicsites.com/", timeout=20)
    print("login page:", r.status_code)
    forms = re.findall(r"<form[^>]*action=[\"']([^\"']*)[\"']", r.text, re.I)
    print("form actions:", forms)
    inputs = re.findall(r'name=["\']([^"\']+)["\']', r.text)
    print("input names:", sorted(set(inputs)))

    # OPTIONS on token shows schema sometimes
    r2 = requests.options(
        "https://www.biologicsites.com/api/v1/token/",
        headers={"Accept": "application/json"},
        timeout=20,
    )
    print("token OPTIONS body:", r2.text[:500])


def web_login_result(username: str, password: str) -> tuple[int, str | None]:
    session = requests.Session()
    r = session.get("https://www.biologicsites.com/accounts/login/", timeout=20)
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
    if not m:
        return 0, None
    csrf = m.group(1)
    r2 = session.post(
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
    return r2.status_code, r2.headers.get("location")


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        code, loc = web_login_result(sys.argv[1], sys.argv[2])
        print("web login:", code, "location:", loc)
        r = requests.post(
            "https://www.biologicsites.com/api/v1/token/",
            data={"email": sys.argv[1], "password": sys.argv[2]},
            headers={"Accept": "application/json"},
            timeout=20,
        )
        print("api token:", r.status_code, r.text[:150])
    else:
        main()
