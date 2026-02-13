from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import json
import zoneinfo

from metrics_rollup import main as metrics_main
from monthly_equity_curve import run as mtd_curve

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
LOG_DIR = BASE / "logs"


def run() -> str:
    today = datetime.now(tz=IST).date()
    since = today - timedelta(days=7)

    total_r = 0.0
    total_pnl = 0.0
    trades = 0
    r_list = []

    for p in LOG_DIR.glob("paper_portfolio_*.json"):
        try:
            date_str = p.stem.replace("paper_portfolio_", "")
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            continue
        if d < since:
            continue
        payload = json.loads(p.read_text())
        for t in payload.get("trades", []):
            r = float(t.get("outcome_r", 0))
            total_r += r
            total_pnl += float(t.get("pnl_inr", 0))
            trades += 1
            r_list.append((d.isoformat(), r))

    # Health score (0–100)
    avg_r = total_r / trades if trades else 0.0
    hit_rate = 0.0
    wins = 0
    for _, r in r_list:
        if r > 0:
            wins += 1
    hit_rate = wins / trades if trades else 0.0

    # max drawdown (trade-level)
    max_dd = 0.0
    if r_list:
        equity = 0.0
        peak = 0.0
        for _, r in r_list:
            equity += r
            peak = max(peak, equity)
            dd = equity - peak
            if dd < max_dd:
                max_dd = dd

    health = 50.0
    # Avg R/trade impact (cap ±25)
    health += max(-25, min(25, avg_r * 25))
    # Hit rate impact (cap ±20)
    health += max(-20, min(20, (hit_rate - 0.5) * 80))
    # Total R impact (cap ±10)
    health += max(-10, min(10, total_r * 2))
    # Drawdown penalty (up to -25)
    health -= min(25, abs(max_dd) * 6)

    health = max(0, min(100, health))

    lines = []
    lines.append(f"Weekly Report (last 7 days) — {today.isoformat()}")
    lines.append(f"Trades: {trades} | Total R: {total_r:.2f} | Total PnL: ₹{total_pnl:.2f}")
    lines.append(
        f"Health Score: {health:.0f}/100 | Avg R/trade: {avg_r:.2f} | Hit rate: {hit_rate:.0%} | Max DD: {max_dd:.2f}R"
    )
    lines.append("")
    try:
        lines.append(metrics_main())
    except Exception:
        pass
    lines.append("")
    lines.append(mtd_curve())
    return "\n".join(lines)


if __name__ == "__main__":
    print(run())
