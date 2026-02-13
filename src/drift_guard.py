from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
import zoneinfo

from config import load_config

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
LOG_DIR = BASE / "logs"
RISK_STATE_PATH = BASE / "data" / "risk_state.json"


def _load_logs(lookback_days: int) -> list[dict]:
    today = datetime.now(tz=IST).date()
    logs = []
    for i in range(1, lookback_days + 1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        p = LOG_DIR / f"paper_portfolio_{d}.json"
        if not p.exists():
            continue
        try:
            logs.append(json.loads(p.read_text()))
        except Exception:
            continue
    return logs


def _calc_stats(logs: list[dict]) -> dict:
    daily_r = []
    for payload in logs:
        trades = payload.get("trades", [])
        if not trades:
            continue
        rsum = sum(float(t.get("outcome_r", 0)) for t in trades)
        daily_r.append(rsum)

    if not daily_r:
        return {"days": 0, "avg_r": 0.0, "max_dd": 0.0}

    # equity curve + max drawdown (in R)
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in daily_r:
        eq += r
        if eq > peak:
            peak = eq
        dd = eq - peak
        if dd < max_dd:
            max_dd = dd

    avg_r = sum(daily_r) / len(daily_r)
    return {"days": len(daily_r), "avg_r": avg_r, "max_dd": max_dd}


def _load_risk_state() -> dict:
    if RISK_STATE_PATH.exists():
        try:
            return json.loads(RISK_STATE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_risk_state(state: dict) -> None:
    RISK_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RISK_STATE_PATH.write_text(json.dumps(state, indent=2))


def run() -> str:
    cfg = load_config()
    dg = cfg.get("driftGuard", {})
    lookback = int(dg.get("lookbackDays", 30))
    min_avg_r = float(dg.get("minAvgR", 0.05))
    max_dd_r = float(dg.get("maxDrawdownR", 3.0))
    pause_days = int(dg.get("pauseDays", 2))

    logs = _load_logs(lookback)
    stats = _calc_stats(logs)

    if stats["days"] < max(10, lookback // 3):
        return ""

    should_pause = (stats["avg_r"] < min_avg_r) or (stats["max_dd"] <= -max_dd_r)

    state = _load_risk_state()
    today = datetime.now(tz=IST).date()
    if should_pause:
        paused_until = (today + timedelta(days=pause_days)).strftime("%Y-%m-%d")
        state.update(
            {
                "paused_until": paused_until,
                "reason": "drift_guard",
                "avg_r": stats["avg_r"],
                "max_drawdown_r": stats["max_dd"],
                "updated_at": datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        _save_risk_state(state)
        return (
            f"DRIFT GUARD: PAUSED until {paused_until}\n"
            f"Lookback days: {stats['days']}\n"
            f"Avg R: {stats['avg_r']:.2f} | Max DD: {stats['max_dd']:.2f}R"
        )

    # clear pause if recovering
    if state.get("paused_until"):
        state.pop("paused_until", None)
        state.update(
            {
                "reason": "cleared",
                "avg_r": stats["avg_r"],
                "max_drawdown_r": stats["max_dd"],
                "updated_at": datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        _save_risk_state(state)
        return (
            "DRIFT GUARD: CLEARED\n"
            f"Lookback days: {stats['days']}\n"
            f"Avg R: {stats['avg_r']:.2f} | Max DD: {stats['max_dd']:.2f}R"
        )

    return ""


if __name__ == "__main__":
    out = run()
    if out:
        print(out)
