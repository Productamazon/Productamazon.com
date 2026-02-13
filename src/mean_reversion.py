from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Optional

import pandas as pd
import zoneinfo

from indicators import atr, vwap, rsi
from sim_costs import apply_slippage
from charges_india import estimate_equity_intraday_charges

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


@dataclass
class MRTrade:
    symbol: str
    direction: str  # BUY/SELL
    entry_ts_ist: str
    entry: float
    stop: float
    target: float
    qty: int
    exit_ts_ist: str
    exit_price: float
    pnl_inr: float
    outcome_r: float
    reason: str


def simulate_mean_reversion(
    df: pd.DataFrame,
    d: date,
    *,
    r_inr: float,
    slippage_bps: float,
    fixed_cost_inr: float,
    rsi_period: int = 14,
    rsi_overbought: float = 70,
    rsi_oversold: float = 30,
    vwap_atr_dist: float = 1.2,
    tgt_r: float = 1.2,
    stop_atr: float = 0.8,
) -> Optional[MRTrade]:
    if df.empty or len(df) < 30:
        return None

    df = df.copy()
    df["atr"] = atr(df, 14)
    df["vwap"] = vwap(df)
    df["rsi"] = rsi(df["close"], rsi_period)

    start_utc = pd.Timestamp(datetime.combine(d, time(9, 30)).replace(tzinfo=IST).astimezone(timezone.utc))
    end_utc = pd.Timestamp(datetime.combine(d, time(15, 0)).replace(tzinfo=IST).astimezone(timezone.utc))
    window = df.loc[(df.index >= start_utc) & (df.index <= end_utc)]
    if window.empty:
        return None

    entry_ts = None
    direction = None
    entry_row = None

    for ts, row in window.iterrows():
        if pd.isna(row["atr"]) or pd.isna(row["vwap"]) or pd.isna(row["rsi"]):
            continue
        dist = (float(row["close"]) - float(row["vwap"]))
        atr_now = float(row["atr"])
        if atr_now <= 0:
            continue
        if dist >= vwap_atr_dist * atr_now and float(row["rsi"]) >= rsi_overbought:
            direction = "SELL"
            entry_ts = ts
            entry_row = row
            break
        if dist <= -vwap_atr_dist * atr_now and float(row["rsi"]) <= rsi_oversold:
            direction = "BUY"
            entry_ts = ts
            entry_row = row
            break

    if entry_ts is None or entry_row is None or direction is None:
        return None

    entry_raw = float(entry_row["close"])
    atr_now = float(entry_row["atr"])

    if direction == "BUY":
        stop_raw = entry_raw - stop_atr * atr_now
        target_raw = entry_raw + tgt_r * (entry_raw - stop_raw)
    else:
        stop_raw = entry_raw + stop_atr * atr_now
        target_raw = entry_raw - tgt_r * (stop_raw - entry_raw)

    entry = apply_slippage(entry_raw, "BUY" if direction == "BUY" else "SELL", slippage_bps)
    risk_per_share = abs(entry - stop_raw)
    if risk_per_share <= 0:
        return None

    qty = int(r_inr // risk_per_share)
    if qty <= 0:
        return None

    after = window.loc[window.index >= entry_ts]
    reason = "time_exit"
    exit_ts = after.index[-1]
    exit_raw = float(after.iloc[-1]["close"])

    for ts, row in after.iterrows():
        lo = float(row["low"])
        hi = float(row["high"])
        if direction == "BUY":
            if lo <= stop_raw:
                exit_raw = stop_raw
                exit_ts = ts
                reason = "stop_hit"
                break
            if hi >= target_raw:
                exit_raw = target_raw
                exit_ts = ts
                reason = "target_hit"
                break
        else:
            if hi >= stop_raw:
                exit_raw = stop_raw
                exit_ts = ts
                reason = "stop_hit"
                break
            if lo <= target_raw:
                exit_raw = target_raw
                exit_ts = ts
                reason = "target_hit"
                break

    exit_fill = apply_slippage(exit_raw, "SELL" if direction == "BUY" else "BUY", slippage_bps)
    pnl_gross = (exit_fill - entry) * qty if direction == "BUY" else (entry - exit_fill) * qty
    charges = estimate_equity_intraday_charges(entry, exit_fill, qty)
    pnl_net = pnl_gross - charges.total - fixed_cost_inr

    return MRTrade(
        symbol="",
        direction=direction,
        entry_ts_ist=entry_ts.tz_convert(IST).strftime("%Y-%m-%d %H:%M"),
        entry=float(entry),
        stop=float(stop_raw),
        target=float(target_raw),
        qty=int(qty),
        exit_ts_ist=exit_ts.tz_convert(IST).strftime("%Y-%m-%d %H:%M"),
        exit_price=float(exit_fill),
        pnl_inr=float(pnl_net),
        outcome_r=float(pnl_net / r_inr),
        reason=reason,
    )
