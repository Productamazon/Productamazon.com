from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Optional

import pandas as pd
import zoneinfo

from indicators import opening_range, atr, vwap
from fyers_client import get_fyers
from data_quality import clean_ohlcv_df
from indicators import to_ohlcv_df
from data_cache import get_intraday

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


@dataclass
class RegimeResult:
    regime: str  # "trend" or "range"
    trend_dir: str  # "bull" | "bear" | "flat"
    notes: dict


def fetch_intraday(symbol: str, d: date, resolution: str = "5") -> pd.DataFrame:
    fyers = get_fyers()
    d_str = d.strftime("%Y-%m-%d")

    def _fetch():
        resp = fyers.history(
            {
                "symbol": symbol,
                "resolution": resolution,
                "date_format": "1",
                "range_from": d_str,
                "range_to": d_str,
                "cont_flag": "1",
            }
        )
        if not isinstance(resp, dict) or resp.get("s") != "ok":
            return []
        return resp.get("candles") or []

    df = get_intraday(symbol, d_str, resolution, _fetch)
    if df.empty:
        return df
    df, _qr = clean_ohlcv_df(df, symbol=symbol)
    return df


def classify_regime(
    d: date,
    nifty_symbol: str,
    *,
    or_start: str = "09:15",
    or_end: str = "09:30",
    min_or_range_pct: float = 0.18,
    min_or_atr_ratio: float = 0.8,
    rvol_mult: float = 1.2,
) -> RegimeResult:
    """Classify day as trend or range using NIFTY context + opening range expansion."""

    df = fetch_intraday(nifty_symbol, d)
    if df.empty or len(df) < 10:
        return RegimeResult("range", "flat", {"reason": "nifty_data_missing"})

    df = df.copy()
    df["atr"] = atr(df, 14)
    df["vwap"] = vwap(df)
    df["vol_avg10"] = df["volume"].rolling(10).mean()

    or_start_dt = datetime.combine(d, datetime.strptime(or_start, "%H:%M").time()).replace(tzinfo=IST)
    or_end_dt = datetime.combine(d, datetime.strptime(or_end, "%H:%M").time()).replace(tzinfo=IST)
    or_start_utc = pd.Timestamp(or_start_dt.astimezone(timezone.utc))
    or_end_utc = pd.Timestamp(or_end_dt.astimezone(timezone.utc))

    levels = opening_range(df, or_start_utc, or_end_utc)
    if levels is None:
        return RegimeResult("range", "flat", {"reason": "no_opening_range"})

    # Use the first candle after OR to judge trend direction
    after = df.loc[df.index >= or_end_utc]
    if after.empty:
        return RegimeResult("range", "flat", {"reason": "no_post_or"})

    row = after.iloc[0]
    close = float(row["close"])
    vwap_now = float(row["vwap"]) if not pd.isna(row["vwap"]) else close
    atr_now = float(row["atr"]) if not pd.isna(row["atr"]) else 0.0
    vol_avg10 = float(row["vol_avg10"]) if not pd.isna(row["vol_avg10"]) else 0.0

    or_range = float(levels.or_high - levels.or_low)
    or_range_pct = (or_range / close) * 100 if close else 0.0

    # Fallbacks for early-session NaNs (ATR/volume not fully formed yet)
    if atr_now <= 0:
        atr_now = or_range if or_range > 0 else 0.0
    if vol_avg10 <= 0:
        try:
            vol_avg10 = float(df.loc[df.index <= or_end_utc]["volume"].mean())
        except Exception:
            vol_avg10 = 0.0

    or_atr_ratio = (or_range / atr_now) if atr_now else 0.0

    trend_dir = "flat"
    if close > vwap_now:
        trend_dir = "bull"
    elif close < vwap_now:
        trend_dir = "bear"

    # Signals for trend regime
    sig_or_expanding = or_range_pct >= min_or_range_pct and or_atr_ratio >= min_or_atr_ratio
    sig_rvol = vol_avg10 > 0 and float(row["volume"]) >= rvol_mult * vol_avg10
    sig_trend = trend_dir in ("bull", "bear")

    signals_true = sum([sig_or_expanding, sig_rvol, sig_trend])
    regime = "trend" if signals_true >= 2 else "range"

    notes = {
        "trend_dir": trend_dir,
        "or_range_pct": or_range_pct,
        "or_atr_ratio": or_atr_ratio,
        "rvol": float(row["volume"]) / vol_avg10 if vol_avg10 else 0.0,
        "sig_or_expanding": sig_or_expanding,
        "sig_rvol": sig_rvol,
        "sig_trend": sig_trend,
    }

    return RegimeResult(regime=regime, trend_dir=trend_dir, notes=notes)
