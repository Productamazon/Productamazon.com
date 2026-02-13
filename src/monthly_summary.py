from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import zoneinfo

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
LOG_DIR = BASE / "logs"
REPORTS_DIR = BASE / "reports"


def load_month(month_prefix: str) -> Tuple[List[Tuple[str, float, float]], Dict[str, float]]:
    trades: List[Tuple[str, float, float]] = []
    daily: Dict[str, float] = {}

    for p in sorted(LOG_DIR.glob(f"paper_portfolio_{month_prefix}-*.json")):
        date_str = p.stem.replace("paper_portfolio_", "")
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            continue
        payload = json.loads(p.read_text())
        day_r = 0.0
        for t in payload.get("trades", []):
            r = float(t.get("outcome_r", 0))
            pnl = float(t.get("pnl_inr", 0))
            trades.append((date_str, r, pnl))
            day_r += r
        daily[date_str] = day_r

    return trades, daily


def summarize(month_prefix: str | None = None) -> str:
    if month_prefix is None:
        today = datetime.now(tz=IST).date()
        month_prefix = today.strftime("%Y-%m")

    trades, daily = load_month(month_prefix)

    if not trades:
        return f"Monthly Summary ({month_prefix})\nNo trades yet."

    total_r = sum(r for _, r, _ in trades)
    total_pnl = sum(p for _, _, p in trades)
    n = len(trades)
    avg_r = total_r / n if n else 0.0

    wins = [r for _, r, _ in trades if r > 0]
    losses = [r for _, r, _ in trades if r <= 0]
    win_rate = len(wins) / n if n else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0

    # drawdown (trade-level)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for _, r, _ in trades:
        equity += r
        peak = max(peak, equity)
        dd = equity - peak
        if dd < max_dd:
            max_dd = dd

    best_day = max(daily.items(), key=lambda x: x[1]) if daily else ("", 0.0)
    worst_day = min(daily.items(), key=lambda x: x[1]) if daily else ("", 0.0)

    lines = []
    lines.append(f"Monthly Summary ({month_prefix})")
    lines.append(f"Trades: {n} | Total R: {total_r:.2f} | Total PnL: ₹{total_pnl:.2f}")
    lines.append(
        f"Avg R/trade: {avg_r:.2f} | Win rate: {win_rate:.0%} | Avg win: {avg_win:.2f}R | Avg loss: {avg_loss:.2f}R"
    )
    lines.append(f"Max drawdown: {max_dd:.2f}R")
    lines.append(f"Best day: {best_day[0]} ({best_day[1]:+.2f}R)")
    lines.append(f"Worst day: {worst_day[0]} ({worst_day[1]:+.2f}R)")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"monthly_summary_{month_prefix}.txt"
    out_path.write_text("\n".join(lines))

    return "\n".join(lines)


if __name__ == "__main__":
    print(summarize())
