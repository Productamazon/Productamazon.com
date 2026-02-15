from __future__ import annotations

import base64
import hmac
import json
import os
import struct
import time
from pathlib import Path
from typing import Tuple
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv

try:
    from fyers_apiv3 import fyersModel
except ImportError as e:  # pragma: no cover
    raise SystemExit("Missing dependency. Run: pip install -r requirements.txt") from e

BASE = Path(__file__).resolve().parents[1]
TOKEN_PATH = BASE / "data" / "fyers_token.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _totp(key: str, time_step: int = 30, digits: int = 6, digest: str = "sha1") -> str:
    key = base64.b32decode(key.upper() + "=" * ((8 - len(key)) % 8))
    counter = struct.pack(">Q", int(time.time() / time_step))
    mac = hmac.new(key, counter, digest).digest()
    offset = mac[-1] & 0x0F
    binary = struct.unpack(">L", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary)[-digits:].zfill(digits)


def refresh_access_token() -> Tuple[bool, str]:
    """Attempt to auto-refresh FYERS access token using TOTP + PIN.

    Requires env vars:
    - FYERS_TOTP_KEY, FYERS_CLIENT_ID, FYERS_PIN
    - FYERS_APP_ID, FYERS_SECRET_KEY, FYERS_REDIRECT_URI

    Returns (ok, message).
    """
    load_dotenv()
    totp_key = os.environ.get("FYERS_TOTP_KEY")
    username = os.environ.get("FYERS_CLIENT_ID")
    pin = os.environ.get("FYERS_PIN")
    app_id = os.environ.get("FYERS_APP_ID")
    secret_key = os.environ.get("FYERS_SECRET_KEY")
    redirect_uri = os.environ.get("FYERS_REDIRECT_URI")

    missing = [
        k
        for k, v in {
            "FYERS_TOTP_KEY": totp_key,
            "FYERS_CLIENT_ID": username,
            "FYERS_PIN": pin,
            "FYERS_APP_ID": app_id,
            "FYERS_SECRET_KEY": secret_key,
            "FYERS_REDIRECT_URI": redirect_uri,
        }.items()
        if not v
    ]
    if missing:
        return False, f"Missing env vars: {', '.join(missing)}"

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": UA,
        }
    )

    # 1) Send OTP
    data1 = {
        "fy_id": base64.b64encode(str(username).encode()).decode(),
        "app_id": "2",
    }
    r1 = session.post("https://api-t2.fyers.in/vagator/v2/send_login_otp_v2", json=data1, timeout=20)
    if r1.status_code != 200 or "request_key" not in r1.json():
        return False, f"OTP request failed: {r1.text[:200]}"

    # 2) Verify OTP
    data2 = {"request_key": r1.json()["request_key"], "otp": int(_totp(totp_key))}
    r2 = session.post("https://api-t2.fyers.in/vagator/v2/verify_otp", json=data2, timeout=20)
    if r2.status_code != 200 or "request_key" not in r2.json():
        return False, f"OTP verify failed: {r2.text[:200]}"

    # 3) Verify PIN
    data3 = {
        "request_key": r2.json()["request_key"],
        "identity_type": "pin",
        "identifier": base64.b64encode(str(pin).encode()).decode(),
    }
    r3 = session.post("https://api-t2.fyers.in/vagator/v2/verify_pin_v2", json=data3, timeout=20)
    if r3.status_code != 200 or "data" not in r3.json():
        return False, f"PIN verify failed: {r3.text[:200]}"

    bearer = r3.json()["data"].get("access_token")
    if not bearer:
        return False, "Missing access_token after PIN verify"

    # 4) Request auth_code (API v3)
    headers = {"authorization": f"Bearer {bearer}", "content-type": "application/json; charset=UTF-8"}
    data4 = {
        "fyers_id": username,
        "app_id": app_id.split("-")[0],
        "redirect_uri": redirect_uri,
        "appType": "100",
        "code_challenge": "",
        "state": "sample_state",
        "scope": "",
        "nonce": "",
        "response_type": "code",
        "create_cookie": True,
    }
    r4 = session.post("https://api-t1.fyers.in/api/v3/token", headers=headers, json=data4, timeout=20)
    try:
        url = r4.json().get("Url") or r4.json().get("url")
    except Exception:
        url = None
    if not url:
        return False, f"Auth code request failed: {r4.text[:200]}"

    auth_code = parse_qs(urlparse(url).query).get("auth_code", [None])[0]
    if not auth_code:
        return False, "auth_code missing in redirect URL"

    # 5) Exchange auth_code for access token
    session_model = fyersModel.SessionModel(
        client_id=app_id,
        secret_key=secret_key,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code",
    )
    session_model.set_token(auth_code)
    resp = session_model.generate_token()
    if not isinstance(resp, dict) or resp.get("access_token") is None:
        return False, f"Token exchange failed: {resp}"

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(resp, indent=2))
    return True, f"Saved token to: {TOKEN_PATH}"


def main() -> None:
    ok, msg = refresh_access_token()
    if ok:
        print(f"FYERS AUTO REFRESH: OK - {msg}")
    else:
        print(f"FYERS AUTO REFRESH: FAIL - {msg}")


if __name__ == "__main__":
    main()
