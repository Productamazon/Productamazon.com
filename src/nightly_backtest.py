from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

import pandas as pd
import zoneinfo

from config import load_config
from fyers_client import get_fyers
from indicators import opening_range, atr, vwap
from sim_costs import apply_slippage
from charges_india import estimate_equity_intraday_charges
from universe import load_universe
from trading_days import last_n_trading_days
from data_quality import clean_ohlcv_df
from versioning import build_version_stamp
from data_cache import get_intraday as get_intraday_cached

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
OUT_DIR = BASE / "reports" / "nightly"


def fetch_intraday(symbol: str, d: date) -> pd.DataFrame:
    fyers = get_fyers()
    d_str = d.strftime("%Y-%m-%d")

    def _fetch():
        try:
            resp = fyers.history(
                {
                    "symbol": symbol,
                    "resolution": "5",
                    "date_format": "1",
                    "range_from": d_str,
                    "range_to": d_str,
                    "cont_flag": "1",
                }
            )
            if not isinstance(resp, dict) or resp.get("s") != "ok":
                return []
            return resp.get("candles") or []
        except Exception:
            return []

    df = get_intraday_cached(symbol, d_str, "5", _fetch)
    if df.empty:
        return df
    df, _qr = clean_ohlcv_df(df, symbol=symbol)
    return df


def simulate_one_trade(
    df: pd.DataFrame,
    d: date,
    *,
    vol_mult: float,
    tgt_r: float,
    r_inr: float,
    slippage_bps: float,
    fixed_cost_inr: float,
    require_nifty: bool,
    nifty_df: Optional[pd.DataFrame],
    min_or_range_pct: float = 0.0,
    min_or_atr_ratio: float = 0.0,
    stop_atr_mult: float = 0.5,
    entry_end_ist: str = "11:30",
) -> Optional[tuple[pd.Timestamp, float]]:
    """Return (entry_ts_utc, outcome_r) for this symbol for the day, or None if no trade."""

    if df.empty or len(df) < 30:
        return None

    or_start_ist = datetime.combine(d, datetime.strptime("09:15", "%H:%M").time()).replace(tzinfo=IST)
    or_end_ist = datetime.combine(d, datetime.strptime("09:30", "%H:%M").time()).replace(tzinfo=IST)
    or_start_utc = pd.Timestamp(or_start_ist.astimezone(zoneinfo.ZoneInfo("UTC")))
    or_end_utc = pd.Timestamp(or_end_ist.astimezone(zoneinfo.ZoneInfo("UTC")))

    levels = opening_range(df, or_start_utc, or_end_utc)
    if levels is None:
        return None

    df = df.copy()
    df["atr"] = atr(df, 14)
    df["vol_avg10"] = df["volume"].rolling(10).mean()

    # OR filters
    try:
        or_close = float(df.loc[df.index <= or_end_utc].iloc[-1]["close"])
    except Exception:
        or_close = 0.0
    or_range = float(levels.or_high - levels.or_low)
    if min_or_range_pct > 0 and or_close > 0:
        if (or_range / or_close) * 100 < min_or_range_pct:
            return None
    if min_or_atr_ratio > 0:
        try:
            or_row = df.loc[df.index >= or_end_utc].iloc[0]
            atr_now = float(or_row.get("atr", 0.0))
        except Exception:
            atr_now = 0.0
        if atr_now <= 0:
            return None
        if (or_range / atr_now) < min_or_atr_ratio:
            return None

    start_trade_utc = or_end_utc
    entry_end_time = datetime.strptime(entry_end_ist, "%H:%M").time()
    entry_end_utc = pd.Timestamp(datetime.combine(d, entry_end_time).replace(tzinfo=IST).astimezone(zoneinfo.ZoneInfo("UTC")))
    end_trade_ist = datetime.combine(d, datetime.strptime("15:20", "%H:%M").time()).replace(tzinfo=IST)
    end_trade_utc = pd.Timestamp(end_trade_ist.astimezone(zoneinfo.ZoneInfo("UTC")))

    entry_window = df.loc[(df.index >= start_trade_utc) & (df.index <= entry_end_utc)]
    if entry_window.empty:
        return None

    # full window for exits
    window = df.loc[(df.index >= start_trade_utc) & (df.index <= end_trade_utc)]

    entry_ts = None
    entry_row = None

    for ts, row in entry_window.iterrows():
        if pd.isna(row["vol_avg10"]) or pd.isna(row["atr"]):
            continue
        if float(row["close"]) > levels.or_high and float(row["volume"]) >= vol_mult * float(row["vol_avg10"]):
            entry_ts = ts
            entry_row = row
            break

    if entry_ts is None:
        return None

    if require_nifty and nifty_df is not None and not nifty_df.empty:
        ndf = nifty_df.copy()
        ndf["vwap"] = vwap(ndf)
        ndf2 = ndf.loc[ndf.index <= entry_ts]
        if ndf2.empty:
            return None
        nrow = ndf2.iloc[-1]
        if float(nrow["close"]) < float(nrow["vwap"]):
            return None

    entry_raw = float(entry_row["close"])
    stop = float(levels.or_high - stop_atr_mult * float(entry_row["atr"]))
    if stop >= entry_raw:
        return None

    entry_fill = apply_slippage(entry_raw, "BUY", slippage_bps)
    risk_per_share = entry_fill - stop
    if risk_per_share <= 0:
        return None

    qty = int(r_inr // risk_per_share)
    if qty <= 0:
        return None

    target = entry_raw + tgt_r * (entry_raw - stop)

    after = window.loc[window.index >= entry_ts]
    for ts, row in after.iterrows():
        if float(row["low"]) <= stop:
            exit_raw = stop
            break
        if float(row["high"]) >= target:
            exit_raw = target
            break
    else:
        exit_raw = float(after.iloc[-1]["close"])

    exit_fill = apply_slippage(float(exit_raw), "SELL", slippage_bps)
    pnl_gross = (exit_fill - entry_fill) * qty
    charges = estimate_equity_intraday_charges(entry_fill, exit_fill, qty)
    pnl_net = pnl_gross - charges.total - fixed_cost_inr
    return entry_ts, float(pnl_net / r_inr)


def last_n_dates(n: int) -> list[date]:
    # naive: last n calendar days; weekends/holidays will just yield no data.
    today = datetime.now(tz=IST).date()
    ds = []
    cur = today
    while len(ds) < n:
        cur = cur - timedelta(days=1)
        ds.append(cur)
    return list(reversed(ds))


def run():
    cfg = load_config()
    orb_cfg = cfg.get("strategies", {}).get("ORB", {})
    risk_cfg = cfg.get("risk", {})
    sim_cfg = cfg.get("executionSim", {})
    flt_cfg = cfg.get("filters", {})

    tgt_r = float(orb_cfg.get("targetR", 1.5))
    r_inr = float(risk_cfg.get("rPerTradeInr", 10))
    slippage_bps = float(sim_cfg.get("slippageBpsEachSide", 10))
    fixed_cost_inr = float(sim_cfg.get("roundTripFixedCostInr", 2.0))

    require_nifty = bool(flt_cfg.get("requireNiftyBullish", True))
    nifty_symbol = str(flt_cfg.get("niftySymbol", "NSE:NIFTY50-INDEX"))

    # Learning mode: micro-sweep only a few options to avoid overfitting.
    def _grid(env_key: str, default: str) -> list[float]:
        raw = os.environ.get(env_key, default)
        return [float(x.strip()) for x in raw.split(",") if x.strip()]

    vol_mult_grid = _grid("SWEEP_VOL_MULT", "1.3,1.5")
    min_or_pct_grid = _grid("SWEEP_MIN_OR_PCT", "0.2,0.25")
    min_or_atr_grid = _grid("SWEEP_MIN_OR_ATR", "0.8,1.0")
    stop_atr_grid = _grid("SWEEP_STOP_ATR", "0.5,0.6")
    tgt_r_grid = _grid("SWEEP_TGT_R", f"{tgt_r}")
    entry_end_grid = [x.strip() for x in os.environ.get("SWEEP_ENTRY_END", "10:45,11:30").split(",") if x.strip()]

    sweep_days = int(os.environ.get("SWEEP_DAYS", "7"))
    max_syms = int(os.environ.get("SWEEP_MAX_SYMBOLS", "0"))

    dates = last_n_trading_days(sweep_days)
    universe = load_universe()
    if max_syms > 0:
        universe = universe[:max_syms]

    best = None
    results = []

    for vol_mult in vol_mult_grid:
        for min_or_pct in min_or_pct_grid:
            for min_or_atr in min_or_atr_grid:
                for stop_atr in stop_atr_grid:
                    for tgt_r_sweep in tgt_r_grid:
                        for entry_end in entry_end_grid:
                            total_r = 0.0
                            trades = 0
                            for d in dates:
                                nifty_df = fetch_intraday(nifty_symbol, d) if require_nifty else None

                                # choose 1 trade/day: earliest valid signal across symbols
                                candidates: list[tuple[pd.Timestamp, float]] = []
                                for sym in universe:
                                    df = fetch_intraday(sym, d)
                                    out = simulate_one_trade(
                                        df,
                                        d,
                                        vol_mult=vol_mult,
                                        tgt_r=tgt_r_sweep,
                                        r_inr=r_inr,
                                        slippage_bps=slippage_bps,
                                        fixed_cost_inr=fixed_cost_inr,
                                        require_nifty=require_nifty,
                                        nifty_df=nifty_df,
                                        min_or_range_pct=min_or_pct,
                                        min_or_atr_ratio=min_or_atr,
                                        stop_atr_mult=stop_atr,
                                        entry_end_ist=entry_end,
                                    )
                                    if out is None:
                                        continue
                                    candidates.append(out)

                                if candidates:
                                    # Realistic 1-trade/day selection: earliest valid signal across symbols
                                    candidates.sort(key=lambda x: x[0])
                                    day_r = float(candidates[0][1])
                                    total_r += day_r
                                    trades += 1

                            avg_r = total_r / trades if trades else 0.0
                            row = {
                                "vol_mult": vol_mult,
                                "min_or_pct": min_or_pct,
                                "min_or_atr": min_or_atr,
                                "stop_atr": stop_atr,
                                "tgt_r": tgt_r_sweep,
                                "entry_end": entry_end,
                                "total_r": total_r,
                                "trades": trades,
                                "avg_r": avg_r,
                            }
                            results.append(row)
                            if best is None or row["avg_r"] > best["avg_r"]:
                                best = row

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / f"nightly_sweep_{datetime.now(tz=IST).strftime('%Y-%m-%d_%H%M')}.json"
    out_json.write_text(json.dumps({"version": build_version_stamp(), "dates": [d.isoformat() for d in dates], "results": results, "best": best}, indent=2))

    # Telegram-friendly summary
    lines = []
    lines.append("Nightly Test Loop (PAPER) — ORB")
    lines.append(f"Window: last {len(dates)} trading days · Universe: {len(universe)}")
    lines.append("Multi-parameter sweep (earliest-signal selection):")
    for r in results:
        lines.append(f"- vol_mult {r['vol_mult']}: avg {r['avg_r']:.2f}R over {r['trades']} days")
    if best:
        lines.append(f"Best avg: vol_mult {best['vol_mult']} ({best['avg_r']:.2f}R)")
        current = float(orb_cfg.get('volumeMultiplier', 1.2))
        if abs(best['vol_mult'] - current) >= 0.09:
            lines.append(f"Suggestion: consider switching volumeMultiplier {current} → {best['vol_mult']} (not auto-applied)")
    # Include overall rollup (based on stored logs)
    try:
        from metrics_rollup import main as metrics_main
        lines.append("")
        lines.append(metrics_main())
    except Exception:
        pass

    return "\n".join(lines)


if __name__ == "__main__":
    print(run())
