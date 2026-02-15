from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import List

import os
import zoneinfo

from fyers_client import get_fyers
from data_cache import get_intraday

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


def _has_market_data(d: date, symbol: str = "NSE:NIFTY50-INDEX") -> bool:
    ds = d.strftime("%Y-%m-%d")
    # Offline mode: rely on cached data if present
    if os.environ.get("FYERS_OFFLINE", "0") == "1":
        df = get_intraday(symbol, ds, "5", lambda: [])
        return not df.empty

    fyers = get_fyers()
    resp = fyers.history(
        {
            "symbol": symbol,
            "resolution": "5",
            "date_format": "1",
            "range_from": ds,
            "range_to": ds,
            "cont_flag": "1",
        }
    )
    return isinstance(resp, dict) and resp.get("s") == "ok" and bool(resp.get("candles"))


def last_n_trading_days(n: int, *, lookback_days: int = 40) -> List[date]:
    """Get last N trading days by probing NIFTY index candles.

    This avoids needing an external holiday calendar.
    """

    today = datetime.now(tz=IST).date()
    days: List[date] = []
    cur = today

    for _ in range(lookback_days):
        cur = cur - timedelta(days=1)
        try:
            if _has_market_data(cur):
                days.append(cur)
                if len(days) >= n:
                    break
        except Exception:
            # ignore transient API/network errors; continue
            continue

    return list(reversed(days))
