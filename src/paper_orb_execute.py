from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, date, time, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import zoneinfo

from fyers_client import get_fyers
from indicators import to_ohlcv_df, opening_range, atr, vwap
from config import load_config
from sim_costs import apply_slippage
from universe import load_universe
from charges_india import estimate_equity_intraday_charges
from data_quality import clean_ohlcv_df
from versioning import build_version_stamp

IST = zoneinfo.ZoneInfo("Asia/Kolkata")

BASE = Path(__file__).resolve().parents[1]
LOG_DIR = BASE / "logs"
REPORT_DIR = BASE / "reports"


@dataclass
class TradeResult:
    symbol: str
    direction: str  # BUY only for now
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
    nifty_ok: bool


def fetch_intraday(symbol: str, d: date, resolution: str = "5") -> pd.DataFrame:
    fyers = get_fyers()
    data = {
        "symbol": symbol,
        "resolution": resolution,
        "date_format": "1",
        "range_from": d.strftime("%Y-%m-%d"),
        "range_to": d.strftime("%Y-%m-%d"),
        "cont_flag": "1",
    }
    resp = fyers.history(data)
    if not isinstance(resp, dict) or resp.get("s") != "ok":
        return pd.DataFrame()
    candles = resp.get("candles") or []
    if not candles:
        return pd.DataFrame()
    df = to_ohlcv_df(candles)
    df, _qr = clean_ohlcv_df(df, symbol=symbol)
    return df


def simulate_orb_trade(
    df: pd.DataFrame,
    d: date,
    *,
    vol_mult: float = 1.2,
    tgt_r: float = 1.5,
    r_inr: float = 10.0,
    slippage_bps: float = 10.0,
    fixed_cost_inr: float = 2.0,
    require_nifty_bullish: bool = False,
    nifty_df: Optional[pd.DataFrame] = None,
) -> Optional[TradeResult]:
    """Simulate one ORB trade per symbol:

    - Opening range 9:15–9:30
    - First breakout close above ORH after 9:30 with volume confirmation triggers entry at that close.
    - Stop: ORH - 0.5*ATR (at entry candle)
    - Target: entry + tgt_r*(entry-stop)
    - Exit: first hit of stop/target (in candle extremes) OR time stop at 15:20 IST (exit at close of last candle before).

    This is for PAPER evaluation.
    """

    if df.empty or len(df) < 20:
        return None

    or_start_utc = pd.Timestamp(datetime.combine(d, time(9, 15)).replace(tzinfo=IST).astimezone(timezone.utc))
    or_end_utc = pd.Timestamp(datetime.combine(d, time(9, 30)).replace(tzinfo=IST).astimezone(timezone.utc))

    levels = opening_range(df, or_start_utc, or_end_utc)
    if levels is None:
        return None

    df = df.copy()
    df["atr"] = atr(df, 14)
    df["vol_avg10"] = df["volume"].rolling(10).mean()

    start_trade_utc = or_end_utc
    end_trade_utc = pd.Timestamp(datetime.combine(d, time(15, 20)).replace(tzinfo=IST).astimezone(timezone.utc))

    window = df.loc[(df.index >= start_trade_utc) & (df.index <= end_trade_utc)]
    if window.empty:
        return None

    entry_idx = None
    for ts, row in window.iterrows():
        if pd.isna(row["vol_avg10"]) or pd.isna(row["atr"]):
            continue
        if float(row["close"]) > levels.or_high and float(row["volume"]) >= vol_mult * float(row["vol_avg10"]):
            entry_idx = ts
            entry_row = row
            break

    if entry_idx is None:
        return None

    # Optional NIFTY context filter (bullish only)
    nifty_ok = True
    if require_nifty_bullish:
        nifty_ok = False
        if nifty_df is not None and not nifty_df.empty:
            ndf = nifty_df.copy()
            ndf["vwap"] = vwap(ndf)
            if entry_idx in ndf.index:
                row = ndf.loc[entry_idx]
                # If duplicate timestamps exist, `row` will be a DataFrame.
                if hasattr(row, "iloc") and not isinstance(row, pd.Series):
                    row = row.iloc[-1]
                nifty_ok = float(row["close"]) >= float(row["vwap"])
            else:
                # align by nearest timestamp <= entry
                ndf2 = ndf.loc[ndf.index <= entry_idx]
                if not ndf2.empty:
                    row = ndf2.iloc[-1]
                    nifty_ok = float(row["close"]) >= float(row["vwap"])
        if not nifty_ok:
            return None

    entry_raw = float(entry_row["close"])
    atr_now = float(entry_row["atr"]) if not pd.isna(entry_row["atr"]) else 0.0
    stop_raw = float(levels.or_high - 0.5 * atr_now)
    if stop_raw >= entry_raw:
        return None

    # Slippage-adjusted fills
    entry = apply_slippage(entry_raw, "BUY", slippage_bps)
    stop = stop_raw  # trigger level

    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return None

    qty = int(r_inr // risk_per_share)
    if qty <= 0:
        return None

    target = entry_raw + tgt_r * (entry_raw - stop_raw)

    # walk forward to find exit
    after = window.loc[window.index >= entry_idx]
    for ts, row in after.iterrows():
        lo = float(row["low"])
        hi = float(row["high"])
        if lo <= stop:
            exit_price_raw = stop
            exit_ts = ts
            reason = "stop_hit"
            break
        if hi >= target:
            exit_price_raw = target
            exit_ts = ts
            reason = "target_hit"
            break
    else:
        exit_ts = after.index[-1]
        exit_price_raw = float(after.iloc[-1]["close"])
        reason = "time_exit"

    exit_price = apply_slippage(float(exit_price_raw), "SELL", slippage_bps)

    pnl_gross = (exit_price - entry) * qty

    # Replace simplistic fixed cost with an India intraday estimate.
    # Keep fixed_cost_inr as an extra safety buffer (can be 0 later).
    ch = estimate_equity_intraday_charges(buy_price=entry, sell_price=exit_price, qty=qty)
    pnl_net = pnl_gross - float(ch.total) - float(fixed_cost_inr)

    outcome_r = pnl_net / float(r_inr)

    entry_ts_ist = entry_idx.tz_convert(IST).strftime("%Y-%m-%d %H:%M")
    exit_ts_ist = exit_ts.tz_convert(IST).strftime("%Y-%m-%d %H:%M")

    return TradeResult(
        symbol="",
        direction="BUY",
        entry_ts_ist=entry_ts_ist,
        entry=float(entry),
        stop=float(stop),
        target=float(target),
        qty=int(qty),
        exit_ts_ist=exit_ts_ist,
        exit_price=float(exit_price),
        pnl_inr=float(pnl_net),
        outcome_r=float(outcome_r),
        reason=reason,
        nifty_ok=bool(nifty_ok),
    )


def run_day(d: date) -> dict:
    """Generate candidates, pick best one (1 trade/day), simulate, and log."""

    cfg = load_config()
    orb_cfg = cfg.get("strategies", {}).get("ORB", {})
    risk_cfg = cfg.get("risk", {})
    sim_cfg = cfg.get("executionSim", {})
    flt_cfg = cfg.get("filters", {})

    vol_mult = float(orb_cfg.get("volumeMultiplier", 1.2))
    tgt_r = float(orb_cfg.get("targetR", 1.5))
    r_inr = float(risk_cfg.get("rPerTradeInr", 10))
    slippage_bps = float(sim_cfg.get("slippageBpsEachSide", 10))
    fixed_cost_inr = float(sim_cfg.get("roundTripFixedCostInr", 2.0))
    require_nifty = bool(flt_cfg.get("requireNiftyBullish", False))
    nifty_symbol = str(flt_cfg.get("niftySymbol", "NSE:NIFTY50-INDEX"))

    trades: list[TradeResult] = []
    candidates: list[TradeResult] = []

    nifty_df = fetch_intraday(nifty_symbol, d) if require_nifty else None

    for sym in load_universe():
        df = fetch_intraday(sym, d)
        if df.empty:
            continue
        tr = simulate_orb_trade(
            df,
            d,
            vol_mult=vol_mult,
            tgt_r=tgt_r,
            r_inr=r_inr,
            slippage_bps=slippage_bps,
            fixed_cost_inr=fixed_cost_inr,
            require_nifty_bullish=require_nifty,
            nifty_df=nifty_df,
        )
        if tr is None:
            continue
        tr.symbol = sym
        candidates.append(tr)

    # pick best by outcome in hindsight for now? No—must pick by signal time.
    # We'll pick the earliest valid signal across symbols (realistic for 1-trade/day).
    if candidates:
        candidates.sort(key=lambda t: t.entry_ts_ist)
        trades.append(candidates[0])

    payload = {
        "date": d.strftime("%Y-%m-%d"),
        "mode": "paper",
        "strategy": "ORB",
        "version": build_version_stamp(),
        "maxTradesPerDay": int(risk_cfg.get("maxTradesPerDay", 1)),
        "config": {
            "vol_mult": vol_mult,
            "tgt_r": tgt_r,
            "r_inr": r_inr,
            "slippage_bps_each_side": slippage_bps,
            "round_trip_fixed_cost_inr": fixed_cost_inr,
            "require_nifty_bullish": require_nifty,
            "nifty_symbol": nifty_symbol,
        },
        "trades": [t.__dict__ for t in trades],
        "notes": "Simulated using 5m candles: slippage applied to buy/sell fills; India intraday charges estimated (STT/txn/SEBI/stamp/GST) + extra fixed buffer; NIFTY bullish filter optionally enforced.",
    }

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / f"paper_orb_{d.strftime('%Y-%m-%d')}.json").write_text(json.dumps(payload, indent=2))
    return payload


def summarize(payload: dict) -> str:
    trades = payload.get("trades", [])
    if not trades:
        return f"Daily Paper Summary (ORB) {payload['date']}\nNo trades triggered."
    t = trades[0]
    sym = t["symbol"].replace("NSE:", "").replace("-EQ", "")
    return (
        f"Daily Paper Summary (ORB) {payload['date']}\n"
        f"Trade: {sym} BUY (qty {t['qty']})\n"
        f"Entry(fill): {t['entry']:.2f} @ {t['entry_ts_ist']} IST\n"
        f"SL(trigger): {t['stop']:.2f} | TGT(trigger): {t['target']:.2f}\n"
        f"Exit(fill): {t['exit_price']:.2f} @ {t['exit_ts_ist']} IST ({t['reason']})\n"
        f"PnL: ₹{t['pnl_inr']:.2f} | Result: {t['outcome_r']:.2f}R"
    )


if __name__ == "__main__":
    d = datetime.now(tz=IST).date()
    payload = run_day(d)
    text = summarize(payload)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"daily_{d.strftime('%Y-%m-%d')}.txt").write_text(text)
    print(text)
