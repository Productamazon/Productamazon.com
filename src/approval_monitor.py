from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import zoneinfo

from config import load_config
from fyers_client import get_fyers
from indicators import to_ohlcv_df, opening_range, atr, vwap, rsi
from sim_costs import apply_slippage
from data_cache import get_intraday
from universe import load_universe
from pending_approval import PendingApproval, save_pending
from regime import classify_regime
from speed_filters import prefilter_symbols
from pathlib import Path
from trading_days import is_trading_day, is_market_open
from stocks_in_play import get_stocks_in_play

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
STATE_PATH = BASE / "data" / "last_approval.json"
RISK_STATE_PATH = BASE / "data" / "risk_state.json"
APPROVAL_LOG_PATH = BASE / "data" / "approval_log.jsonl"
SECTOR_MAP_PATH = BASE / "data" / "sector_map.json"


def fetch_intraday(symbol: str, d: str) -> pd.DataFrame:
    fyers = get_fyers()

    def _fetch():
        resp = fyers.history(
            {
                "symbol": symbol,
                "resolution": "5",
                "date_format": "1",
                "range_from": d,
                "range_to": d,
                "cont_flag": "1",
            }
        )
        if not isinstance(resp, dict) or resp.get("s") != "ok":
            return []
        return resp.get("candles") or []

    return get_intraday(symbol, d, "5", _fetch)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def load_risk_state() -> dict:
    if RISK_STATE_PATH.exists():
        return json.loads(RISK_STATE_PATH.read_text())
    return {}


def save_risk_state(state: dict) -> None:
    RISK_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RISK_STATE_PATH.write_text(json.dumps(state, indent=2))


def append_approval_log(cand: dict, decision: str = "sent") -> None:
    APPROVAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts_ist": datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": cand.get("symbol"),
        "strategy": cand.get("strategy"),
        "side": cand.get("side"),
        "grade": cand.get("grade"),
        "score": cand.get("score"),
        "regime": cand.get("regime"),
        "trend_dir": cand.get("trend_dir"),
        "decision": decision,
        "entry": cand.get("entry"),
        "stop": cand.get("stop"),
        "target": cand.get("target"),
        "sector": cand.get("sector"),
    }
    with APPROVAL_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def load_sector_map() -> dict:
    if SECTOR_MAP_PATH.exists():
        try:
            return json.loads(SECTOR_MAP_PATH.read_text())
        except Exception:
            return {}
    return {}


def sector_count_today(sector: str, d: str) -> int:
    if not APPROVAL_LOG_PATH.exists():
        return 0
    try:
        cnt = 0
        for line in APPROVAL_LOG_PATH.read_text().splitlines():
            if not line:
                continue
            row = json.loads(line)
            if row.get("decision") != "sent":
                continue
            if row.get("sector") == sector and str(row.get("ts_ist", ""))[:10] == d:
                cnt += 1
        return cnt
    except Exception:
        return 0


def in_trade_window(now: datetime, start: str = "09:30", end: str = "11:30") -> bool:
    st_h, st_m = map(int, start.split(":"))
    en_h, en_m = map(int, end.split(":"))
    t = now.timetz().replace(tzinfo=None)
    return time(st_h, st_m) <= t <= time(en_h, en_m)


def get_today_pnl_losses_trades(d: str) -> tuple[float, int, int]:
    """Return (pnl_inr, consecutive_losses, trades_count) based on today's portfolio log if present."""
    log_path = BASE / "logs" / f"paper_portfolio_{d}.json"
    if not log_path.exists():
        return 0.0, 0, 0
    try:
        payload = json.loads(log_path.read_text())
        trades = payload.get("trades", [])
        pnl = sum(float(t.get("pnl_inr", 0)) for t in trades)
        # consecutive losses from end
        consec = 0
        for t in reversed(trades):
            if float(t.get("pnl_inr", 0)) < 0:
                consec += 1
            else:
                break
        return pnl, consec, len(trades)
    except Exception:
        return 0.0, 0, 0


def grade_from_score(score: float, thresholds: dict) -> str:
    aplus = float(thresholds.get("Aplus", 2.0))
    a = float(thresholds.get("A", 1.2))
    if score >= aplus:
        return "A+"
    if score >= a:
        return "A"
    return "B"


def grade_rank(g: str) -> int:
    order = {"B": 0, "A": 1, "A+": 2}
    return order.get(str(g).upper().strip(), 0)


def find_best_signal(now_ist: datetime) -> Optional[dict]:
    cfg = load_config()
    orb = cfg["strategies"]["ORB"]
    mr = cfg["strategies"].get("MEAN_REVERSION", {})
    risk = cfg["risk"]
    sim = cfg["executionSim"]
    flt = cfg.get("filters", {})

    vol_mult = float(orb.get("volumeMultiplier", 1.2))
    tgt_r = float(orb.get("targetR", 1.5))
    min_or_pct = float(orb.get("minORRangePct", 0.18))
    min_or_atr = float(orb.get("minORtoATR", 0.8))
    max_or_pct = float(orb.get("maxORRangePct", 0.0))
    max_or_atr = float(orb.get("maxORtoATR", 0.0))
    r_inr_base = float(risk.get("rPerTradeInr", 125))
    slip_bps = float(sim.get("slippageBpsEachSide", 10))
    fixed_cost = float(sim.get("roundTripFixedCostInr", 2.0))

    nifty_symbol = str(flt.get("niftySymbol", "NSE:NIFTY50-INDEX"))
    require_nifty_vwap = bool(flt.get("requireNiftyVwap", False))
    nifty_df = fetch_intraday(nifty_symbol, d) if require_nifty_vwap else None
    if require_nifty_vwap and nifty_df is not None and not nifty_df.empty:
        nifty_df = nifty_df.copy()
        nifty_df["vwap"] = vwap(nifty_df)

    grade_thresholds = cfg.get("telegram", {}).get("gradeThresholds", {"Aplus": 2.0, "A": 1.2})
    vol_clamp = cfg.get("volatilityClamp", {"maxAtrPct": 4.0})
    sector_cfg = cfg.get("sectorFilter", {"enabled": False})
    sector_map = load_sector_map()

    d = now_ist.strftime("%Y-%m-%d")

    # Regime classification decides ORB vs MR
    reg = classify_regime(
        now_ist.date(),
        nifty_symbol,
        or_start=orb.get("openingRange", {}).get("start", "09:15"),
        or_end=orb.get("openingRange", {}).get("end", "09:30"),
        min_or_range_pct=float(orb.get("minORRangePct", 0.18)),
        min_or_atr_ratio=float(orb.get("minORtoATR", 0.8)),
        rvol_mult=float(orb.get("volumeMultiplier", 1.2)),
    )

    regime_sizing = risk.get("regimeSizing", {"trend": 1.0, "range": 0.7})
    r_inr = r_inr_base * float(regime_sizing.get(reg.regime, 1.0))

    best = None

    # Opening range timestamps
    or_start_ist = datetime.strptime(d + " 09:15", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    or_end_ist = datetime.strptime(d + " 09:30", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    or_start_utc = pd.Timestamp(or_start_ist.astimezone(timezone.utc))
    or_end_utc = pd.Timestamp(or_end_ist.astimezone(timezone.utc))

    universe = prefilter_symbols(load_universe())
    sip_cfg = flt.get("stocksInPlay", {})
    if bool(sip_cfg.get("enabled", False)):
        universe = get_stocks_in_play(
            now_ist.date(),
            universe,
            lookback_days=int(sip_cfg.get("lookbackDays", 14)),
            min_rvol=float(sip_cfg.get("minRvol", 1.5)),
            top_n=int(sip_cfg.get("topN", 20)),
        )

    for sym in universe:
        df = fetch_intraday(sym, d)
        if df.empty or len(df) < 20:
            continue

        df = df.copy()
        df["atr"] = atr(df, 14)
        df["vol_avg10"] = df["volume"].rolling(10).mean()
        df["vwap"] = vwap(df)
        df["rsi"] = rsi(df["close"], int(mr.get("rsiPeriod", 14)))

        now_utc = pd.Timestamp(now_ist.astimezone(timezone.utc))

        if reg.regime == "trend" and bool(orb.get("enabled", True)):
            levels = opening_range(df, or_start_utc, or_end_utc)
            if levels is None:
                continue

            # OR filters
            try:
                or_close = float(df.loc[df.index <= or_end_utc].iloc[-1]["close"])
            except Exception:
                or_close = 0.0
            or_range = float(levels.or_high - levels.or_low)
            if or_close > 0:
                if min_or_pct > 0 and (or_range / or_close) * 100 < min_or_pct:
                    continue
                if max_or_pct > 0 and (or_range / or_close) * 100 > max_or_pct:
                    continue
            if min_or_atr > 0 or max_or_atr > 0:
                try:
                    or_row = df.loc[df.index >= or_end_utc].iloc[0]
                    atr_now = float(or_row.get("atr", 0.0))
                except Exception:
                    atr_now = 0.0
                if atr_now <= 0:
                    continue
                if min_or_atr > 0 and (or_range / atr_now) < min_or_atr:
                    continue
                if max_or_atr > 0 and (or_range / atr_now) > max_or_atr:
                    continue

            window = df.loc[(df.index >= or_end_utc) & (df.index <= now_utc)]
            if window.empty:
                continue

            # Most recent valid entry signal (real-time)
            for ts, row in window[::-1].iterrows():
                if pd.isna(row["vol_avg10"]) or pd.isna(row["atr"]):
                    continue
                # Volatility clamp
                atr_pct = (float(row["atr"]) / float(row["close"])) * 100 if float(row["close"]) else 0.0
                if atr_pct > float(vol_clamp.get("maxAtrPct", 4.0)):
                    continue

                # NIFTY VWAP filter (optional)
                nifty_ok_long = True
                nifty_ok_short = True
                if require_nifty_vwap and nifty_df is not None and not nifty_df.empty:
                    ndf2 = nifty_df.loc[nifty_df.index <= ts]
                    if ndf2.empty:
                        continue
                    nrow = ndf2.iloc[-1]
                    nifty_ok_long = float(nrow["close"]) >= float(nrow["vwap"])
                    nifty_ok_short = float(nrow["close"]) <= float(nrow["vwap"])

                # Long ORB
                if bool(orb.get("allowLong", True)) and nifty_ok_long and float(row["close"]) > levels.or_high and float(row["volume"]) >= vol_mult * float(row["vol_avg10"]):
                    entry_raw = float(row["close"])
                    atr_now = float(row["atr"])
                    stop = float(levels.or_high - float(orb.get("stopAtrMult", 0.5)) * atr_now)
                    if stop < entry_raw:
                        entry_fill = apply_slippage(entry_raw, "BUY", slip_bps)
                        risk_per_share = entry_fill - stop
                        qty = int(r_inr // risk_per_share)
                        if qty > 0:
                            target = entry_raw + tgt_r * (entry_raw - stop)
                            breakout_dist = (entry_raw - levels.or_high) / entry_raw
                            vol_strength = float(row["volume"]) / float(row["vol_avg10"])
                            score = 50.0 * breakout_dist + 10.0 * min(vol_strength, 3.0)
                            grade = grade_from_score(score, grade_thresholds)
                            sector = sector_map.get(sym, "UNKNOWN")
                            if bool(sector_cfg.get("enabled", False)) and sector_count_today(sector, d) >= int(sector_cfg.get("maxPerSectorPerDay", 1)):
                                continue
                            cand = {
                                "symbol": sym,
                                "sector": sector,
                                "entry_ts_ist": ts.tz_convert(IST).strftime("%Y-%m-%d %H:%M"),
                                "entry": entry_raw,
                                "stop": stop,
                                "target": target,
                                "qty": qty,
                                "r_inr": r_inr,
                                "fixed_cost_inr": fixed_cost,
                                "score": score,
                                "grade": grade,
                                "vol_strength": vol_strength,
                                "breakout_dist_pct": breakout_dist * 100,
                                "strategy": "ORB",
                                "side": "BUY",
                                "regime": reg.regime,
                                "trend_dir": reg.trend_dir,
                            }
                            if best is None or cand["score"] > best["score"]:
                                best = cand
                    break

                # Short ORB
                if bool(orb.get("allowShort", True)) and nifty_ok_short and float(row["close"]) < levels.or_low and float(row["volume"]) >= vol_mult * float(row["vol_avg10"]):
                    entry_raw = float(row["close"])
                    atr_now = float(row["atr"])
                    stop = float(levels.or_low + float(orb.get("stopAtrMult", 0.5)) * atr_now)
                    if stop > entry_raw:
                        entry_fill = apply_slippage(entry_raw, "SELL", slip_bps)
                        risk_per_share = stop - entry_fill
                        qty = int(r_inr // risk_per_share)
                        if qty > 0:
                            target = entry_raw - tgt_r * (stop - entry_raw)
                            breakout_dist = (levels.or_low - entry_raw) / entry_raw
                            vol_strength = float(row["volume"]) / float(row["vol_avg10"])
                            score = 50.0 * breakout_dist + 10.0 * min(vol_strength, 3.0)
                            grade = grade_from_score(score, grade_thresholds)
                            sector = sector_map.get(sym, "UNKNOWN")
                            if bool(sector_cfg.get("enabled", False)) and sector_count_today(sector, d) >= int(sector_cfg.get("maxPerSectorPerDay", 1)):
                                continue
                            cand = {
                                "symbol": sym,
                                "sector": sector,
                                "entry_ts_ist": ts.tz_convert(IST).strftime("%Y-%m-%d %H:%M"),
                                "entry": entry_raw,
                                "stop": stop,
                                "target": target,
                                "qty": qty,
                                "r_inr": r_inr,
                                "fixed_cost_inr": fixed_cost,
                                "score": score,
                                "grade": grade,
                                "vol_strength": vol_strength,
                                "breakout_dist_pct": breakout_dist * 100,
                                "strategy": "ORB",
                                "side": "SELL",
                                "regime": reg.regime,
                                "trend_dir": reg.trend_dir,
                            }
                            if best is None or cand["score"] > best["score"]:
                                best = cand
                    break

        if reg.regime == "range" and bool(mr.get("enabled", True)):
            window = df.loc[(df.index <= now_utc)]
            if window.empty:
                continue
            # check most recent candle only
            row = window.iloc[-1]
            if pd.isna(row["atr"]) or pd.isna(row["vwap"]) or pd.isna(row["rsi"]):
                continue
            # Volatility clamp
            atr_pct = (float(row["atr"]) / float(row["close"])) * 100 if float(row["close"]) else 0.0
            if atr_pct > float(vol_clamp.get("maxAtrPct", 4.0)):
                continue
            dist = float(row["close"]) - float(row["vwap"])
            atr_now = float(row["atr"])
            if atr_now <= 0:
                continue
            rsi_overbought = float(mr.get("rsiOverbought", 70))
            rsi_oversold = float(mr.get("rsiOversold", 30))
            vwap_dist = float(mr.get("vwapAtrDistance", 1.2))
            tgt_r_mr = float(mr.get("targetR", 1.2))
            stop_atr = float(mr.get("stopAtrMult", 0.8))

            if dist >= vwap_dist * atr_now and float(row["rsi"]) >= rsi_overbought:
                # MR short
                entry_raw = float(row["close"])
                stop = entry_raw + stop_atr * atr_now
                entry_fill = apply_slippage(entry_raw, "SELL", slip_bps)
                risk_per_share = stop - entry_fill
                qty = int(r_inr // risk_per_share)
                if qty > 0:
                    target = entry_raw - tgt_r_mr * (stop - entry_raw)
                    score = abs(dist) / atr_now
                    grade = grade_from_score(score, grade_thresholds)
                    sector = sector_map.get(sym, "UNKNOWN")
                    if bool(sector_cfg.get("enabled", False)) and sector_count_today(sector, d) >= int(sector_cfg.get("maxPerSectorPerDay", 1)):
                        continue
                    cand = {
                        "symbol": sym,
                        "sector": sector,
                        "entry_ts_ist": window.index[-1].tz_convert(IST).strftime("%Y-%m-%d %H:%M"),
                        "entry": entry_raw,
                        "stop": stop,
                        "target": target,
                        "qty": qty,
                        "r_inr": r_inr,
                        "fixed_cost_inr": fixed_cost,
                        "score": score,
                        "grade": grade,
                        "strategy": "MEAN_REVERSION",
                        "side": "SELL",
                        "regime": reg.regime,
                        "trend_dir": reg.trend_dir,
                        "vwap_dist_atr": abs(dist) / atr_now,
                        "rsi": float(row["rsi"]),
                    }
                    if best is None or cand["score"] > best["score"]:
                        best = cand
            if dist <= -vwap_dist * atr_now and float(row["rsi"]) <= rsi_oversold:
                # MR long
                entry_raw = float(row["close"])
                stop = entry_raw - stop_atr * atr_now
                entry_fill = apply_slippage(entry_raw, "BUY", slip_bps)
                risk_per_share = entry_fill - stop
                qty = int(r_inr // risk_per_share)
                if qty > 0:
                    target = entry_raw + tgt_r_mr * (entry_raw - stop)
                    score = abs(dist) / atr_now
                    grade = grade_from_score(score, grade_thresholds)
                    sector = sector_map.get(sym, "UNKNOWN")
                    if bool(sector_cfg.get("enabled", False)) and sector_count_today(sector, d) >= int(sector_cfg.get("maxPerSectorPerDay", 1)):
                        continue
                    cand = {
                        "symbol": sym,
                        "sector": sector,
                        "entry_ts_ist": window.index[-1].tz_convert(IST).strftime("%Y-%m-%d %H:%M"),
                        "entry": entry_raw,
                        "stop": stop,
                        "target": target,
                        "qty": qty,
                        "r_inr": r_inr,
                        "fixed_cost_inr": fixed_cost,
                        "score": score,
                        "grade": grade,
                        "strategy": "MEAN_REVERSION",
                        "side": "BUY",
                        "regime": reg.regime,
                        "trend_dir": reg.trend_dir,
                        "vwap_dist_atr": abs(dist) / atr_now,
                        "rsi": float(row["rsi"]),
                    }
                    if best is None or cand["score"] > best["score"]:
                        best = cand

    return best


def format_approval(cand: dict) -> str:
    now = datetime.now(tz=IST)
    cfg = load_config()
    exp = int(cfg.get("telegram", {}).get("approvalExpirySeconds", 90))
    expires = (now + pd.Timedelta(seconds=exp)).to_pydatetime().strftime("%H:%M:%S")

    sym = cand["symbol"].replace("NSE:", "").replace("-EQ", "")

    rr = abs(cand["target"] - cand["entry"]) / abs(cand["entry"] - cand["stop"]) if cand["entry"] != cand["stop"] else 0.0

    approval_id = cand.get("approval_id", "")
    side = cand.get("side", "BUY")
    strat = cand.get("strategy", "ORB")

    why_lines = []
    if strat == "ORB":
        why_lines.append(f"- ORB breakout (dist {cand.get('breakout_dist_pct', 0):.2f}%)")
        why_lines.append(f"- Volume strength {cand.get('vol_strength', 0):.2f}x")
    else:
        why_lines.append(f"- VWAP stretch {cand.get('vwap_dist_atr', 0):.2f} ATR")
        why_lines.append(f"- RSI {cand.get('rsi', 0):.1f}")

    return (
        "MODE: PAPER\n"
        f"Strategy: {strat}\n"
        f"Approval ID: {approval_id}\n"
        f"Symbol: {sym}\n"
        f"Side: {side}\n"
        f"Grade: {cand.get('grade','-')}\n"
        f"Entry: ₹{cand['entry']:.2f}\n"
        f"Stop:  ₹{cand['stop']:.2f}\n"
        f"Target: ₹{cand['target']:.2f}\n"
        f"Qty (sim): {cand['qty']}\n"
        f"Risk: ₹{cand['r_inr']:.0f} | R:R: {rr:.2f}\n"
        "Why now:\n"
        + "\n".join(why_lines)
        + f"\nApproval expires at: {expires} IST\n"
        "Reply: YES or NO"
    )


def main():
    now = datetime.now(tz=IST)
    if not is_trading_day(now.date()):
        return
    if not is_market_open(now):
        return
    if not in_trade_window(now):
        return

    orb_cfg = load_config().get("strategies", {}).get("ORB", {})
    entry_end = str(orb_cfg.get("entryEnd", "11:30"))
    try:
        end_h, end_m = map(int, entry_end.split(":"))
        if now.timetz().replace(tzinfo=None) > time(end_h, end_m):
            return
    except Exception:
        pass

    # Drift guard (pause if flagged)
    rs = load_risk_state()
    paused_until = rs.get("paused_until")
    if paused_until:
        try:
            if now.strftime("%Y-%m-%d") <= paused_until:
                # log the block if we had a candidate
                cand = find_best_signal(now)
                if cand:
                    append_approval_log(cand, decision="paused_guard")
                return
        except Exception:
            pass

    cand = find_best_signal(now)
    if not cand:
        return

    # Risk engine gate
    risk_cfg = load_config().get("risk", {})
    max_daily_loss = float(risk_cfg.get("maxDailyLossInr", 700))
    soft_stop = float(risk_cfg.get("softStopLossInr", 500))
    pnl, consec_losses, trades_count = get_today_pnl_losses_trades(now.strftime("%Y-%m-%d"))

    # Hard stop
    if pnl <= -max_daily_loss:
        append_approval_log(cand, decision="blocked_hard_stop")
        return

    # Max trades per day
    max_trades = int(risk_cfg.get("maxTradesPerDay", 3))
    if trades_count >= max_trades:
        append_approval_log(cand, decision="blocked_max_trades")
        return

    # Cooldown after N consecutive losses
    stop_after = int(risk_cfg.get("stopAfterLosses", 2))
    if consec_losses >= stop_after:
        append_approval_log(cand, decision="blocked_consec_losses")
        return

    # Minimum approval grade
    min_grade = load_config().get("telegram", {}).get("minApprovalGrade", "B")
    if grade_rank(cand.get("grade")) < grade_rank(min_grade):
        append_approval_log(cand, decision="blocked_min_grade")
        return

    # Soft stop: only A+ in trend regime
    if pnl <= -soft_stop:
        if not (cand.get("grade") == "A+" and cand.get("regime") == "trend"):
            append_approval_log(cand, decision="blocked_soft_stop")
            return

    # A+ only mode during drawdown (from drift guard state)
    dg_cfg = load_config().get("driftGuard", {})
    dd_aonly = float(dg_cfg.get("drawdownAplusOnlyR", 2.0))
    rs = load_risk_state()
    max_dd = float(rs.get("max_drawdown_r", 0.0)) if rs else 0.0
    if max_dd <= -dd_aonly:
        if cand.get("grade") != "A+":
            append_approval_log(cand, decision="blocked_drawdown_aonly")
            return

    # Build deterministic approval id
    cand["approval_id"] = f"{cand['symbol']}|{cand['entry_ts_ist']}"

    state = load_state()

    # Cooldown to avoid spam
    cooldown_min = int(load_config().get("telegram", {}).get("approvalCooldownMinutes", 20))
    last_sent = state.get("last_sent_ist")
    if last_sent:
        try:
            last_dt = datetime.strptime(last_sent, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            if (now - last_dt).total_seconds() < cooldown_min * 60:
                return
        except Exception:
            pass

    key = f"{cand['symbol']}|{cand['entry_ts_ist']}"
    if state.get("last_key") == key and state.get("last_date") == now.strftime("%Y-%m-%d"):
        return

    # mark as sent
    state["last_date"] = now.strftime("%Y-%m-%d")
    state["last_key"] = key
    state["last_sent_ist"] = now.strftime("%Y-%m-%d %H:%M:%S")
    save_state(state)

    # write pending approval so chat replies can be logged later
    save_pending(
        PendingApproval(
            approval_id=cand["approval_id"],
            created_at_ist=now.strftime("%Y-%m-%d %H:%M:%S"),
            symbol=cand["symbol"],
            entry_ts_ist=cand["entry_ts_ist"],
            entry=float(cand["entry"]),
            stop=float(cand["stop"]),
            target=float(cand["target"]),
            qty=int(cand["qty"]),
        )
    )

    append_approval_log(cand, decision="sent")
    print(format_approval(cand))


if __name__ == "__main__":
    main()
