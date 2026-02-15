from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
import zoneinfo

from trading_days import last_n_trading_days
from paper_portfolio_execute import run_day

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
OUT_DIR = BASE / "reports" / "backtests"


def run(days: int = 30) -> dict:
    dates = last_n_trading_days(days)
    payloads = []
    total_r = 0.0
    total_pnl = 0.0
    trades = 0

    for d in dates:
        p = run_day(d)
        payloads.append(p)
        for t in p.get("trades", []):
            total_r += float(t.get("outcome_r", 0))
            total_pnl += float(t.get("pnl_inr", 0))
            trades += 1

    avg_r = total_r / trades if trades else 0.0

    out = {
        "generated_at_ist": datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S"),
        "days": [d.isoformat() for d in dates],
        "trades": trades,
        "total_r": total_r,
        "avg_r": avg_r,
        "total_pnl": total_pnl,
        "payloads": payloads,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg_path = os.environ.get("TRADINGBOT_CONFIG") or os.environ.get("CONFIG_PATH")
    tag = Path(cfg_path).stem if cfg_path else "config.paper"
    tag = tag.replace("config.", "").replace("config_", "").replace("config", "paper")
    out_path = OUT_DIR / f"backtest_30d_{datetime.now(tz=IST).strftime('%Y-%m-%d_%H%M%S')}_{tag}.json"
    out_path.write_text(json.dumps(out, indent=2))
    return {"summary": out, "path": str(out_path)}


if __name__ == "__main__":
    res = run(30)
    s = res["summary"]
    print("30D BACKTEST (PAPER PORTFOLIO)")
    print(f"Trades: {s['trades']} | Total R: {s['total_r']:.2f} | Avg R/trade: {s['avg_r']:.2f} | Total PnL: ₹{s['total_pnl']:.2f}")
    print(f"Saved: {res['path']}")
