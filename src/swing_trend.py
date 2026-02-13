from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd

from fyers_client import get_fyers
from indicators import atr, ema, to_ohlcv_df
from data_quality import clean_ohlcv_df
from data_cache import get_daily


@dataclass
class SwingSignal:
    symbol: str
    direction: str  # BUY/SELL
    entry: float
    stop: float
    trail_atr: float
    reason: str


def fetch_daily(symbol: str, d: date, lookback_days: int = 120) -> pd.DataFrame:
    fyers = get_fyers()
    d_str = d.isoformat()
    start = (d - pd.Timedelta(days=lookback_days)).isoformat()

    def _fetch():
        resp = fyers.history(
            {
                "symbol": symbol,
                "resolution": "D",
                "date_format": "1",
                "range_from": start,
                "range_to": d_str,
                "cont_flag": "1",
            }
        )
        if not isinstance(resp, dict) or resp.get("s") != "ok":
            return []
        return resp.get("candles") or []

    df = get_daily(symbol, d_str, _fetch)
    if df.empty:
        return df
    df, _qr = clean_ohlcv_df(df, symbol=symbol)
    return df


def swing_breakout_signal(
    df: pd.DataFrame,
    *,
    lookback: int = 20,
    atr_mult: float = 2.0,
) -> Optional[SwingSignal]:
    if df.empty or len(df) < lookback + 2:
        return None
    df = df.copy()
    df["atr"] = atr(df, 14)

    recent = df.iloc[-(lookback + 1):-1]
    last = df.iloc[-1]
    high_break = float(last["close"]) > float(recent["high"].max())
    low_break = float(last["close"]) < float(recent["low"].min())

    if not high_break and not low_break:
        return None

    direction = "BUY" if high_break else "SELL"
    entry = float(last["close"])
    atr_now = float(last["atr"]) if not pd.isna(last["atr"]) else 0.0
    if atr_now <= 0:
        return None

    if direction == "BUY":
        stop = entry - atr_mult * atr_now
    else:
        stop = entry + atr_mult * atr_now

    return SwingSignal(symbol="", direction=direction, entry=entry, stop=stop, trail_atr=atr_mult, reason="breakout")


def swing_pullback_signal(
    df: pd.DataFrame,
    *,
    ema_fast: int = 20,
    ema_slow: int = 50,
    atr_mult: float = 2.0,
) -> Optional[SwingSignal]:
    if df.empty or len(df) < ema_slow + 2:
        return None
    df = df.copy()
    df["ema_fast"] = ema(df["close"], ema_fast)
    df["ema_slow"] = ema(df["close"], ema_slow)
    df["atr"] = atr(df, 14)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    trend_up = float(last["ema_fast"]) > float(last["ema_slow"])
    trend_dn = float(last["ema_fast"]) < float(last["ema_slow"])

    if trend_up and float(prev["close"]) <= float(prev["ema_fast"]) and float(last["close"]) > float(last["ema_fast"]):
        direction = "BUY"
    elif trend_dn and float(prev["close"]) >= float(prev["ema_fast"]) and float(last["close"]) < float(last["ema_fast"]):
        direction = "SELL"
    else:
        return None

    entry = float(last["close"])
    atr_now = float(last["atr"]) if not pd.isna(last["atr"]) else 0.0
    if atr_now <= 0:
        return None

    if direction == "BUY":
        stop = entry - atr_mult * atr_now
    else:
        stop = entry + atr_mult * atr_now

    return SwingSignal(symbol="", direction=direction, entry=entry, stop=stop, trail_atr=atr_mult, reason="pullback")
