from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import zoneinfo

from data_cache import get_intraday
from fyers_client import get_fyers
from trading_days import last_n_trading_days
from data_quality import clean_ohlcv_df

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
CACHE_DIR = BASE / "data" / "stocks_in_play"


def _fetch_intraday(symbol: str, d: str, resolution: str = "5") -> pd.DataFrame:
    fyers = get_fyers()

    def _fetch():
        resp = fyers.history(
            {
                "symbol": symbol,
                "resolution": resolution,
                "date_format": "1",
                "range_from": d,
                "range_to": d,
                "cont_flag": "1",
            }
        )
        if not isinstance(resp, dict) or resp.get("s") != "ok":
            return []
        return resp.get("candles") or []

    df = get_intraday(symbol, d, resolution, _fetch)
    if df.empty:
        return df
    df, _qr = clean_ohlcv_df(df, symbol=symbol)
    return df


def _first_candle_volume(df: pd.DataFrame) -> Optional[float]:
    if df.empty:
        return None
    try:
        return float(df.iloc[0]["volume"])
    except Exception:
        return None


def compute_open_rvol(
    symbol: str,
    d: date,
    lookback_days: int = 14,
) -> Optional[float]:
    """Return RVOL = today's first 5m volume / avg first 5m volume over lookback_days."""
    d_str = d.strftime("%Y-%m-%d")
    df_today = _fetch_intraday(symbol, d_str)
    vol_today = _first_candle_volume(df_today)
    if vol_today is None:
        return None

    lb_dates = last_n_trading_days(lookback_days + 1)
    lb_dates = [x for x in lb_dates if x < d]
    vols = []
    for ld in lb_dates[-lookback_days:]:
        df = _fetch_intraday(symbol, ld.strftime("%Y-%m-%d"))
        v = _first_candle_volume(df)
        if v is not None and v > 0:
            vols.append(v)
    if not vols:
        return None

    avg = sum(vols) / len(vols)
    if avg <= 0:
        return None
    return float(vol_today / avg)


def get_stocks_in_play(
    d: date,
    symbols: Iterable[str],
    *,
    lookback_days: int = 14,
    min_rvol: float = 1.5,
    top_n: int = 20,
) -> list[str]:
    """Return symbols ranked by RVOL, optionally cached per day."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"sip_{d.strftime('%Y-%m-%d')}.json"

    if cache_path.exists():
        try:
            payload = json.loads(cache_path.read_text())
            if payload.get("lookback_days") == lookback_days and payload.get("min_rvol") == min_rvol:
                syms = payload.get("symbols") or []
                if syms:
                    return syms[:top_n]
        except Exception:
            pass

    ranked = []
    for sym in symbols:
        rvol = compute_open_rvol(sym, d, lookback_days=lookback_days)
        if rvol is None:
            continue
        ranked.append((sym, rvol))

    ranked.sort(key=lambda x: x[1], reverse=True)
    filtered = [s for s, r in ranked if r >= min_rvol]
    if top_n > 0:
        filtered = filtered[:top_n]

    payload = {
        "generated_at_ist": datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S"),
        "lookback_days": lookback_days,
        "min_rvol": min_rvol,
        "top_n": top_n,
        "symbols": filtered,
    }
    cache_path.write_text(json.dumps(payload, indent=2))
    return filtered
