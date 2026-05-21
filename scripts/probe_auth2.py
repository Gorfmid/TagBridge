"""Compare web login field names vs API token fields."""
import re
import requests

def get_csrf(session: requests.Session, url: str) -> str:
    r = session.get(url, timeout=20)
    m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
    if not m:
        raise RuntimeError("csrf not found")
    return m.group(1)

def try_web_login(username: str, password: str) -> None:
    s = requests.Session()
    csrf = get_csrf(s, "https://www.biologicsites.com/accounts/login/")
    r = s.post(
        "https://www.biologicsites.com/accounts/login/",
        data={
            "csrfmiddlewaretoken": csrf,
            "username": username,
            "password": password,
            "next": "/",
        },
        headers={"Referer": "https://www.biologicsites.com/accounts/login/"},
        timeout=20,
        allow_redirects=False,
    )
    print("web login:", r.status_code, "location:", r.headers.get("location", "")[:80])
    print("session cookies:", list(s.cookies.keys()))

def try_api_token(value: str, password: str) -> None:
    r = requests.post(
        "https://www.biologicsites.com/api/v1/token/",
        data={"email": value, "password": password},
        headers={"Accept": "application/json"},
        timeout=20,
    )
    print(f"api token (email={value!r}):", r.status_code, r.text[:120])

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: probe_auth2.py <username_or_email> <password>")
        sys.exit(1)
    user, pw = sys.argv[1], sys.argv[2]
    try_web_login(user, pw)
    try_api_token(user, pw)
