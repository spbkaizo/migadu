"""Microsoft device-code OAuth2 for Outlook IMAP access.

Uses Thunderbird's registered public client id, so no Azure app registration is
needed. The user signs in via browser; no password passes through this process.
"""

import json
import os
import stat
import subprocess
import time
import urllib.parse
import urllib.request

CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"
TENANT = "consumers"
BASE = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0"
TOKEN_FILE = os.path.expanduser("~/.outlook-oauth-token.json")


def _post(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def _save(tok):
    tok["obtained_at"] = int(time.time())
    with open(TOKEN_FILE, "w") as f:
        json.dump(tok, f)
    os.chmod(TOKEN_FILE, stat.S_IRUSR | stat.S_IWUSR)


def _device_flow():
    d = _post(f"{BASE}/devicecode", {"client_id": CLIENT_ID, "scope": SCOPE})
    if "user_code" not in d:
        raise SystemExit(f"device code request failed: {d}")

    print("\n" + "=" * 68)
    print("  Sign in to Microsoft to authorise IMAP access")
    print("=" * 68)
    print(f"\n  1. Open:  {d['verification_uri']}")
    print(f"  2. Enter code:  {d['user_code']}")
    print(f"\n  (code valid for {d['expires_in'] // 60} minutes)")
    print("=" * 68 + "\n", flush=True)

    try:
        subprocess.run(["open", d["verification_uri"]], check=False, timeout=10)
        print("Opened your browser. Waiting for sign-in ...", flush=True)
    except Exception:
        pass

    interval = d.get("interval", 5)
    deadline = time.time() + d["expires_in"]
    last_note = 0
    while time.time() < deadline:
        time.sleep(interval)
        left = int(deadline - time.time())
        if left // 60 != last_note // 60 and left > 0:
            print(f"  ... {left // 60}m {left % 60}s left, code {d['user_code']}", flush=True)
        last_note = left
        r = _post(
            f"{BASE}/token",
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": CLIENT_ID,
                "device_code": d["device_code"],
            },
        )
        err = r.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        if err:
            raise SystemExit(f"auth failed: {err}: {r.get('error_description', '')[:200]}")
        print("Authorised.\n", flush=True)
        _save(r)
        return r
    raise SystemExit("timed out waiting for sign-in")


def _refresh(tok):
    r = _post(
        f"{BASE}/token",
        {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": tok["refresh_token"],
            "scope": SCOPE,
        },
    )
    if "access_token" not in r:
        return None
    _save(r)
    return r


def get_token():
    """Return a valid access token, reusing or refreshing a cached one."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            tok = json.load(f)
        age = time.time() - tok.get("obtained_at", 0)
        if age < tok.get("expires_in", 3600) - 300:
            return tok["access_token"]
        if "refresh_token" in tok:
            r = _refresh(tok)
            if r:
                return r["access_token"]
    return _device_flow()["access_token"]
