"""Alert when FYERS access token is near expiry (JWT exp)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import zoneinfo
import base64

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
TOKEN_PATH = BASE / "data" / "fyers_token.json"


def _jwt_exp(token: str) -> datetime | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        exp = data.get("exp")
        if not exp:
            return None
        return datetime.fromtimestamp(int(exp), tz=timezone.utc)
    except Exception:
        return None


def main():
    if not TOKEN_PATH.exists():
        print("FYERS token missing: data/fyers_token.json")
        return

    data = json.loads(TOKEN_PATH.read_text())
    token = data.get("access_token")
    if not token:
        print("FYERS token file missing access_token")
        return

    exp_utc = _jwt_exp(token)
    if not exp_utc:
        print("FYERS token expiry not found in JWT")
        return

    now_utc = datetime.now(tz=timezone.utc)
    soon = now_utc + timedelta(hours=6)

    if exp_utc <= soon:
        exp_ist = exp_utc.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
        print(
            "FYERS token expiring soon. "
            f"Expiry(IST): {exp_ist}. "
            "Run auth flow to refresh."
        )


if __name__ == "__main__":
    main()
