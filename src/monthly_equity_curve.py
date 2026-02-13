from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
import zoneinfo

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
LOG_DIR = BASE / "logs"
REPORTS_DIR = BASE / "reports"


DailyPoint = Tuple[str, float]


def load_daily(month_prefix: str | None = None) -> List[DailyPoint]:
    today = datetime.now(tz=IST).date()
    if month_prefix is None:
        month_prefix = today.strftime("%Y-%m")

    daily: List[DailyPoint] = []
    for p in sorted(LOG_DIR.glob(f"paper_portfolio_{month_prefix}-*.json")):
        date_str = p.stem.replace("paper_portfolio_", "")
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            continue
        payload = json.loads(p.read_text())
        rsum = sum(float(t.get("outcome_r", 0)) for t in payload.get("trades", []))
        daily.append((d.isoformat(), rsum))

    return daily


def run() -> str:
    daily = load_daily()
    if not daily:
        return "MTD Equity Curve: no data."

    month_prefix = daily[0][0][:7]

    # build equity curve
    eq = 0.0
    lines = [f"MTD Equity Curve ({month_prefix})"]
    for d, r in daily:
        eq += r
        lines.append(f"{d}: {r:+.2f}R | equity {eq:.2f}R")

    return "\n".join(lines)


def plot_png(out_path: Path | None = None, month_prefix: str | None = None) -> Path | None:
    daily = load_daily(month_prefix=month_prefix)
    if not daily:
        return None

    try:
        import matplotlib.pyplot as plt
    except Exception:
        return None

    dates = [d for d, _ in daily]
    rs = [r for _, r in daily]
    eq = []
    running = 0.0
    for r in rs:
        running += r
        eq.append(running)

    if out_path is None:
        month_prefix = month_prefix or dates[0][:7]
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = REPORTS_DIR / f"mtd_equity_curve_{month_prefix}.png"

    plt.figure(figsize=(8, 4.5), dpi=150)
    plt.plot(dates, eq, marker="o", linewidth=2)
    plt.title(f"MTD Equity Curve ({dates[0][:7]})")
    plt.xlabel("Date")
    plt.ylabel("Cumulative R")
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(out_path, format="png")
    plt.close()

    return out_path


if __name__ == "__main__":
    print(run())
