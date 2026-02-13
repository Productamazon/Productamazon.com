"""Print health FAIL output only; stay silent on OK."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import zoneinfo

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
    if not auth.ok:
        print("TRADING_BOT_HEALTH: FAIL")
        print(f"Time(IST): {now}")
        print(auth.message)
        return

    # OK -> silent


if __name__ == "__main__":
    main()
