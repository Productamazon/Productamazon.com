from __future__ import annotations

from datetime import datetime, timedelta, date, time
from typing import List, Optional

import json
import os
from pathlib import Path
import zoneinfo

from fyers_client import get_fyers
from data_cache import get_intraday
from nse_http import fetch_json

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
NSE_CACHE_DIR = BASE / "data" / "nse"
HOLIDAYS_PATH = NSE_CACHE_DIR / "holidays_trading.json"
MARKET_STATUS_PATH = NSE_CACHE_DIR / "market_status.json"


def _has_market_data(d: date, symbol: str = "NSE:NIFTY50-INDEX") -> bool:
    ds = d.strftime("%Y-%m-%d")

    # Always check cache first (cheap)
    df_cached = get_intraday(symbol, ds, "5", lambda: [])
    if not df_cached.empty:
        return True

    # Offline mode: rely on cached data only
    if os.environ.get("FYERS_OFFLINE", "0") == "1":
        return False

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


def _load_cache(path: Path, max_age_minutes: int) -> Optional[dict]:
    try:
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        fetched = payload.get("fetched_at")
        if not fetched:
            return None
        fetched_dt = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
        age_min = (datetime.utcnow() - fetched_dt).total_seconds() / 60
        if age_min > max_age_minutes:
            return None
        return payload
    except Exception:
        return None


def _write_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "data": data,
    }
    path.write_text(json.dumps(payload, indent=2))


def get_nse_holidays(max_age_hours: int = 24 * 7) -> set[date]:
    cached = _load_cache(HOLIDAYS_PATH, max_age_minutes=max_age_hours * 60)
    if cached:
        return _parse_holidays(cached.get("data") or {})

    data = fetch_json("https://www.nseindia.com/api/holiday-master?type=trading")
    if isinstance(data, dict):
        _write_cache(HOLIDAYS_PATH, data)
        return _parse_holidays(data)

    # fallback to stale cache if available
    if HOLIDAYS_PATH.exists():
        try:
            payload = json.loads(HOLIDAYS_PATH.read_text())
            return _parse_holidays(payload.get("data") or {})
        except Exception:
            pass
    return set()


def _parse_holidays(payload: dict) -> set[date]:
    out: set[date] = set()
    items = payload.get("CBM") or []
    for row in items:
        try:
            d = datetime.strptime(row.get("tradingDate", ""), "%d-%b-%Y").date()
            out.add(d)
        except Exception:
            continue
    return out


def get_market_status(max_age_minutes: int = 5) -> Optional[dict]:
    cached = _load_cache(MARKET_STATUS_PATH, max_age_minutes=max_age_minutes)
    if cached:
        return cached.get("data")

    data = fetch_json("https://www.nseindia.com/api/marketStatus")
    if isinstance(data, dict):
        _write_cache(MARKET_STATUS_PATH, data)
        return data

    # fallback to stale cache if available
    if MARKET_STATUS_PATH.exists():
        try:
            payload = json.loads(MARKET_STATUS_PATH.read_text())
            return payload.get("data")
        except Exception:
            return None
    return None


def is_trading_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    holidays = get_nse_holidays()
    if holidays and d in holidays:
        return False
    return True


def is_market_open(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(tz=IST)
    # Use NSE market status when available
    data = get_market_status()
    if isinstance(data, dict):
        for st in data.get("marketState", []):
            if str(st.get("market", "")).lower().startswith("capital"):
                status = str(st.get("marketStatus", "")).lower()
                if status.startswith("open"):
                    return True
                if status.startswith("close"):
                    return False

    # Fallback: trading day + time window
    if not is_trading_day(now.date()):
        return False
    t = now.timetz().replace(tzinfo=None)
    return time(9, 15) <= t <= time(15, 30)


def last_n_trading_days(n: int, *, lookback_days: int = 40) -> List[date]:
    """Get last N trading days by probing NIFTY index candles.

    This avoids needing an external holiday calendar.
    """

    today = datetime.now(tz=IST).date()
    days: List[date] = []
    cur = today

    for _ in range(lookback_days):
        cur = cur - timedelta(days=1)
        if not is_trading_day(cur):
            continue
        try:
            if _has_market_data(cur):
                days.append(cur)
                if len(days) >= n:
                    break
        except Exception:
            # ignore transient API/network errors; continue
            continue

    return list(reversed(days))
