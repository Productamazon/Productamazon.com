from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, date, time, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import zoneinfo

from fyers_client import get_fyers
from indicators import to_ohlcv_df, atr, opening_range
from universe import load_universe
from data_quality import clean_ohlcv_df
from data_cache import get_intraday

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


@dataclass
class ORBSignal:
    symbol: str
    ts_ist: str
    or_high: float
    or_low: float
    last_close: float
    last_volume: float
    vol_avg10: float
    vol_ok: bool
    breakout: bool
    score: float


def _utc_ts(d: date, t: time) -> pd.Timestamp:
    dt_ist = datetime.combine(d, t).replace(tzinfo=IST)
    return pd.Timestamp(dt_ist.astimezone(timezone.utc))


def fetch_intraday_5m(symbol: str, d: date) -> pd.DataFrame:
    fyers = get_fyers()
    d_str = d.strftime("%Y-%m-%d")

    def _fetch():
        data = {
            "symbol": symbol,
            "resolution": "5",
            "date_format": "1",
            "range_from": d_str,
            "range_to": d_str,
            "cont_flag": "1",
        }
        resp = fyers.history(data)
        if not isinstance(resp, dict) or resp.get("s") != "ok":
            # Common: invalid symbol for FYERS; skip gracefully.
            return []
        return resp.get("candles") or []

    df = get_intraday(symbol, d_str, "5", _fetch)
    if df.empty:
        return df
    df, _qr = clean_ohlcv_df(df, symbol=symbol)
    return df


def scan_orb_for_date(
    d: date,
    volume_multiplier: float = 1.2,
    min_or_range_pct: float = 0.15,
    min_or_atr_ratio: float = 0.0,
) -> list[ORBSignal]:
    """Scan NIFTY50 for ORB breakout candidates.

    min_or_range_pct: minimum opening range size (% of price) to avoid ultra-tight noisy ranges.
    min_or_atr_ratio: minimum OR/ATR ratio to avoid ultra-tight ranges vs volatility.
    """

    or_start = _utc_ts(d, time(9, 15))
    or_end = _utc_ts(d, time(9, 30))

    results: list[ORBSignal] = []

    for symbol in load_universe():
        df = fetch_intraday_5m(symbol, d)
        if df.empty or len(df) < 5:
            continue

        levels = opening_range(df, or_start, or_end)
        if levels is None:
            continue

        df = df.copy()
        df["atr"] = atr(df, 14)

        last = df.iloc[-1]
        last_close = float(last["close"])
        last_vol = float(last["volume"])

        # avoid tiny opening range
        or_range = levels.or_high - levels.or_low
        if last_close > 0:
            if (or_range / last_close) * 100 < min_or_range_pct:
                continue

        # OR/ATR filter (use ATR at or_end; fallback to OR range if ATR not formed)
        if min_or_atr_ratio > 0:
            try:
                or_row = df.loc[df.index >= or_end].iloc[0]
                atr_now = float(or_row.get("atr", 0.0))
            except Exception:
                atr_now = 0.0
            if atr_now <= 0:
                atr_now = or_range if or_range > 0 else 0.0
            or_atr_ratio = (or_range / atr_now) if atr_now else 0.0
            if or_atr_ratio < min_or_atr_ratio:
                continue

        vol_avg10 = float(df["volume"].tail(10).mean())
        vol_ok = last_vol >= volume_multiplier * vol_avg10
        breakout = last_close > levels.or_high

        # simple score: prioritize breakout + volume strength + range size
        score = 0.0
        if breakout:
            score += 50
        if vol_ok:
            score += 30
        score += min(20.0, (or_range / last_close) * 1000)  # scaled range contribution

        ts_ist = df.index[-1].tz_convert(IST).strftime("%Y-%m-%d %H:%M")

        results.append(
            ORBSignal(
                symbol=symbol,
                ts_ist=ts_ist,
                or_high=levels.or_high,
                or_low=levels.or_low,
                last_close=last_close,
                last_volume=last_vol,
                vol_avg10=vol_avg10,
                vol_ok=vol_ok,
                breakout=breakout,
                score=score,
            )
        )

    results.sort(key=lambda x: x.score, reverse=True)
    return results


def save_watchlist(signals: list[ORBSignal], out_path: Path, top_n: int = 15) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_ist": datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S"),
        "strategy": "ORB",
        "top_n": top_n,
        "items": [s.__dict__ for s in signals[:top_n]],
    }
    out_path.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    d = datetime.now(tz=IST).date()
    signals = scan_orb_for_date(d)
    base = Path(__file__).resolve().parents[1]
    out = base / "signals" / f"watchlist_{d.strftime('%Y-%m-%d')}.json"
    save_watchlist(signals, out)
    print(f"Saved: {out}")
    for i, s in enumerate(signals[:10], 1):
        print(f"{i:02d}. {s.symbol} score={s.score:.1f} breakout={s.breakout} vol_ok={s.vol_ok} close={s.last_close} ORH={s.or_high}")
