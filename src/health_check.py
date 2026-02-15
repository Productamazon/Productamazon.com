from __future__ import annotations

from datetime import datetime
from pathlib import Path
import zoneinfo
import os

from fyers_health import check_fyers_token

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]


def main():
    missing = []
    for p in [
        BASE / "config" / "config.paper.json",
        BASE / "data" / "fyers_token.json",
        BASE / "data" / "valid_universe.json",
    ]:
        if not p.exists():
            missing.append(str(p))

    now = datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S")

    if missing:
        print("TRADING_BOT_HEALTH: FAIL")
        print(f"Time(IST): {now}")
        print("Missing:")
        for m in missing:
            print(f"- {m}")
        return

    auth = check_fyers_token()
    if not auth.ok and os.environ.get("FYERS_AUTO_REFRESH", "0") == "1":
        try:
            from fyers_auto_refresh import refresh_access_token

            ok, msg = refresh_access_token()
            if ok:
                auth = check_fyers_token()
            else:
                auth = auth  # keep original
                print(f"FYERS AUTO REFRESH: FAIL - {msg}")
        except Exception as e:
            print(f"FYERS AUTO REFRESH: EXCEPTION - {e}")

    if not auth.ok:
        print("TRADING_BOT_HEALTH: FAIL")
        print(f"Time(IST): {now}")
        print(auth.message)
        return

    print("TRADING_BOT_HEALTH: OK")
    print(f"Time(IST): {now}")
    print("FYERS: OK")
    print("Approval monitor schedule: every 2 min during 09–11 IST (acts 09:30–11:30)")


if __name__ == "__main__":
    main()
