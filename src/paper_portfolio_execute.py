from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, date, time, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import zoneinfo

from config import load_config
from fyers_client import get_fyers
from indicators import to_ohlcv_df, opening_range, atr, vwap
from data_quality import clean_ohlcv_df
from data_cache import get_intraday
from sim_costs import apply_slippage
from charges_india import estimate_equity_intraday_charges
from universe import load_universe
from versioning import build_version_stamp
from regime import classify_regime
from mean_reversion import simulate_mean_reversion, MRTrade
from swing_trend import fetch_daily, swing_breakout_signal, swing_pullback_signal

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
LOG_DIR = BASE / "logs"
REPORT_DIR = BASE / "reports"


@dataclass
class TradeResult:
    symbol: str
    strategy: str
    direction: str
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
    notes: dict


def fetch_intraday(symbol: str, d: date, resolution: str = "5") -> pd.DataFrame:
    fyers = get_fyers()
    d_str = d.strftime("%Y-%m-%d")

    def _fetch():
        data = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": "1",
            "range_from": d_str,
            "range_to": d_str,
            "cont_flag": "1",
        }
        resp = fyers.history(data)
        if not isinstance(resp, dict) or resp.get("s") != "ok":
            return []
        return resp.get("candles") or []

    df = get_intraday(symbol, d_str, resolution, _fetch)
    if df.empty:
        return df
    df, _qr = clean_ohlcv_df(df, symbol=symbol)
    return df


def simulate_orb_trade(
    df: pd.DataFrame,
    d: date,
    *,
    direction: str,
    vol_mult: float,
    tgt_r: float,
    r_inr: float,
    slippage_bps: float,
    fixed_cost_inr: float,
    or_start: str = "09:15",
    or_end: str = "09:30",
    stop_atr_mult: float = 0.5,
) -> Optional[TradeResult]:
    if df.empty or len(df) < 20:
        return None

    or_start_utc = pd.Timestamp(datetime.combine(d, datetime.strptime(or_start, "%H:%M").time()).replace(tzinfo=IST).astimezone(timezone.utc))
    or_end_utc = pd.Timestamp(datetime.combine(d, datetime.strptime(or_end, "%H:%M").time()).replace(tzinfo=IST).astimezone(timezone.utc))

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
    entry_row = None

    for ts, row in window.iterrows():
        if pd.isna(row["vol_avg10"]) or pd.isna(row["atr"]):
            continue
        if direction == "BUY":
            cond = float(row["close"]) > levels.or_high
        else:
            cond = float(row["close"]) < levels.or_low
        vol_ok = float(row["volume"]) >= vol_mult * float(row["vol_avg10"])
        if cond and vol_ok:
            entry_idx = ts
            entry_row = row
            break

    if entry_idx is None or entry_row is None:
        return None

    entry_raw = float(entry_row["close"])
    atr_now = float(entry_row["atr"]) if not pd.isna(entry_row["atr"]) else 0.0
    if atr_now <= 0:
        return None

    if direction == "BUY":
        stop_raw = float(levels.or_high - stop_atr_mult * atr_now)
        target_raw = entry_raw + tgt_r * (entry_raw - stop_raw)
    else:
        stop_raw = float(levels.or_low + stop_atr_mult * atr_now)
        target_raw = entry_raw - tgt_r * (stop_raw - entry_raw)

    entry = apply_slippage(entry_raw, "BUY" if direction == "BUY" else "SELL", slippage_bps)
    risk_per_share = abs(entry - stop_raw)
    if risk_per_share <= 0:
        return None

    qty = int(r_inr // risk_per_share)
    if qty <= 0:
        return None

    after = window.loc[window.index >= entry_idx]
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

    return TradeResult(
        symbol="",
        strategy="ORB",
        direction=direction,
        entry_ts_ist=entry_idx.tz_convert(IST).strftime("%Y-%m-%d %H:%M"),
        entry=float(entry),
        stop=float(stop_raw),
        target=float(target_raw),
        qty=int(qty),
        exit_ts_ist=exit_ts.tz_convert(IST).strftime("%Y-%m-%d %H:%M"),
        exit_price=float(exit_fill),
        pnl_inr=float(pnl_net),
        outcome_r=float(pnl_net / r_inr),
        reason=reason,
        notes={},
    )


def run_day(d: date) -> dict:
    cfg = load_config()
    orb_cfg = cfg.get("strategies", {}).get("ORB", {})
    mr_cfg = cfg.get("strategies", {}).get("MEAN_REVERSION", {})
    swing_cfg = cfg.get("strategies", {}).get("SWING", {})
    risk_cfg = cfg.get("risk", {})
    sim_cfg = cfg.get("executionSim", {})
    flt_cfg = cfg.get("filters", {})

    r_inr_base = float(risk_cfg.get("rPerTradeInr", 125))
    max_trades = int(risk_cfg.get("maxTradesPerDay", 6))

    slippage_bps = float(sim_cfg.get("slippageBpsEachSide", 10))
    fixed_cost_inr = float(sim_cfg.get("roundTripFixedCostInr", 2.0))

    # Regime classification (uses NIFTY)
    nifty_symbol = str(flt_cfg.get("niftySymbol", "NSE:NIFTY50-INDEX"))
    reg = classify_regime(
        d,
        nifty_symbol,
        or_start=orb_cfg.get("openingRange", {}).get("start", "09:15"),
        or_end=orb_cfg.get("openingRange", {}).get("end", "09:30"),
        min_or_range_pct=float(orb_cfg.get("minORRangePct", 0.18)),
        min_or_atr_ratio=float(orb_cfg.get("minORtoATR", 0.8)),
        rvol_mult=float(orb_cfg.get("volumeMultiplier", 1.2)),
    )

    regime_sizing = risk_cfg.get("regimeSizing", {"trend": 1.0, "range": 0.7})
    r_inr = r_inr_base * float(regime_sizing.get(reg.regime, 1.0))

    trades: list[TradeResult] = []
    candidates: list[TradeResult] = []

    # ORB (trend days only)
    if reg.regime == "trend" and bool(orb_cfg.get("enabled", True)):
        allow_long = bool(orb_cfg.get("allowLong", True)) and reg.trend_dir in ("bull", "flat")
        allow_short = bool(orb_cfg.get("allowShort", True)) and reg.trend_dir in ("bear", "flat")

        for sym in load_universe():
            df = fetch_intraday(sym, d)
            if df.empty:
                continue
            if allow_long:
                tr = simulate_orb_trade(
                    df,
                    d,
                    direction="BUY",
                    vol_mult=float(orb_cfg.get("volumeMultiplier", 1.2)),
                    tgt_r=float(orb_cfg.get("targetR", 1.5)),
                    r_inr=r_inr,
                    slippage_bps=slippage_bps,
                    fixed_cost_inr=fixed_cost_inr,
                    or_start=orb_cfg.get("openingRange", {}).get("start", "09:15"),
                    or_end=orb_cfg.get("openingRange", {}).get("end", "09:30"),
                    stop_atr_mult=float(orb_cfg.get("stopAtrMult", 0.5)),
                )
                if tr:
                    tr.symbol = sym
                    tr.notes = {"regime": "trend", "trend_dir": reg.trend_dir}
                    candidates.append(tr)
            if allow_short:
                tr = simulate_orb_trade(
                    df,
                    d,
                    direction="SELL",
                    vol_mult=float(orb_cfg.get("volumeMultiplier", 1.2)),
                    tgt_r=float(orb_cfg.get("targetR", 1.5)),
                    r_inr=r_inr,
                    slippage_bps=slippage_bps,
                    fixed_cost_inr=fixed_cost_inr,
                    or_start=orb_cfg.get("openingRange", {}).get("start", "09:15"),
                    or_end=orb_cfg.get("openingRange", {}).get("end", "09:30"),
                    stop_atr_mult=float(orb_cfg.get("stopAtrMult", 0.5)),
                )
                if tr:
                    tr.symbol = sym
                    tr.notes = {"regime": "trend", "trend_dir": reg.trend_dir}
                    candidates.append(tr)

    # Mean Reversion (range days only)
    if reg.regime == "range" and bool(mr_cfg.get("enabled", True)):
        for sym in load_universe():
            df = fetch_intraday(sym, d)
            if df.empty:
                continue
            tr = simulate_mean_reversion(
                df,
                d,
                r_inr=r_inr,
                slippage_bps=slippage_bps,
                fixed_cost_inr=fixed_cost_inr,
                rsi_period=int(mr_cfg.get("rsiPeriod", 14)),
                rsi_overbought=float(mr_cfg.get("rsiOverbought", 70)),
                rsi_oversold=float(mr_cfg.get("rsiOversold", 30)),
                vwap_atr_dist=float(mr_cfg.get("vwapAtrDistance", 1.2)),
                tgt_r=float(mr_cfg.get("targetR", 1.2)),
                stop_atr=float(mr_cfg.get("stopAtrMult", 0.8)),
            )
            if tr:
                candidates.append(
                    TradeResult(
                        symbol=sym,
                        strategy="MEAN_REVERSION",
                        direction=tr.direction,
                        entry_ts_ist=tr.entry_ts_ist,
                        entry=tr.entry,
                        stop=tr.stop,
                        target=tr.target,
                        qty=tr.qty,
                        exit_ts_ist=tr.exit_ts_ist,
                        exit_price=tr.exit_price,
                        pnl_inr=tr.pnl_inr,
                        outcome_r=tr.outcome_r,
                        reason=tr.reason,
                        notes={"regime": "range", "trend_dir": reg.trend_dir},
                    )
                )

    # Select trades by time, cap to maxTradesPerDay
    candidates.sort(key=lambda t: t.entry_ts_ist)
    trades = candidates[:max_trades]

    # Swing signals (daily) — logged separately (not executed intraday)
    swing_signals = []
    if bool(swing_cfg.get("enabled", True)):
        style = str(swing_cfg.get("style", "pullback"))
        for sym in load_universe():
            df_d = fetch_daily(sym, d)
            if df_d.empty:
                continue
            if style == "breakout":
                sig = swing_breakout_signal(
                    df_d,
                    lookback=int(swing_cfg.get("breakoutLookback", 20)),
                    atr_mult=float(swing_cfg.get("atrMult", 2.0)),
                )
            else:
                sig = swing_pullback_signal(
                    df_d,
                    ema_fast=int(swing_cfg.get("emaFast", 20)),
                    ema_slow=int(swing_cfg.get("emaSlow", 50)),
                    atr_mult=float(swing_cfg.get("atrMult", 2.0)),
                )
            if sig:
                sig.symbol = sym
                swing_signals.append(sig.__dict__)

    payload = {
        "date": d.strftime("%Y-%m-%d"),
        "mode": "paper",
        "strategy": "PORTFOLIO",
        "version": build_version_stamp(),
        "regime": reg.regime,
        "trend_dir": reg.trend_dir,
        "regime_notes": reg.notes,
        "maxTradesPerDay": max_trades,
        "config": {
            "r_inr": r_inr,
            "slippage_bps_each_side": slippage_bps,
            "round_trip_fixed_cost_inr": fixed_cost_inr,
            "orb": orb_cfg,
            "mean_reversion": mr_cfg,
            "swing": swing_cfg,
        },
        "trades": [t.__dict__ for t in trades],
        "swing_signals": swing_signals,
    }

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / f"paper_portfolio_{d.strftime('%Y-%m-%d')}.json").write_text(json.dumps(payload, indent=2))
    return payload


def summarize(payload: dict) -> str:
    lines = []
    lines.append(f"Daily Paper Summary (PORTFOLIO) {payload['date']}")
    lines.append(f"Regime: {payload.get('regime')} | Trend: {payload.get('trend_dir')}")

    trades = payload.get("trades", [])
    if not trades:
        lines.append("No intraday trades triggered.")
    else:
        for t in trades:
            sym = t["symbol"].replace("NSE:", "").replace("-EQ", "")
            lines.append(
                f"{t['strategy']} {sym} {t['direction']} qty {t['qty']} | "
                f"Entry {t['entry']:.2f} @ {t['entry_ts_ist']} | "
                f"Exit {t['exit_price']:.2f} @ {t['exit_ts_ist']} ({t['reason']}) | "
                f"PnL ₹{t['pnl_inr']:.2f} ({t['outcome_r']:.2f}R)"
            )

    swing = payload.get("swing_signals", [])
    if swing:
        lines.append("")
        lines.append(f"Swing signals ({len(swing)}):")
        for s in swing[:5]:
            sym = s["symbol"].replace("NSE:", "").replace("-EQ", "")
            lines.append(f"- {sym} {s['direction']} @ {s['entry']:.2f} | stop {s['stop']:.2f} ({s['reason']})")
        if len(swing) > 5:
            lines.append(f"(+{len(swing) - 5} more)")

    return "\n".join(lines)


if __name__ == "__main__":
    d = datetime.now(tz=IST).date()
    payload = run_day(d)
    text = summarize(payload)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"daily_{d.strftime('%Y-%m-%d')}.txt").write_text(text)
    print(text)
