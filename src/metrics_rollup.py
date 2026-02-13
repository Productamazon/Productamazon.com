from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
LOG_DIR = BASE / "logs"
OUT_PATH = BASE / "reports" / "metrics_rollup.json"


@dataclass
class Metrics:
    trades: int
    total_r: float
    avg_r: float
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    max_drawdown_r: float


def load_all_trades() -> List[dict]:
    trades = []
    for p in sorted(LOG_DIR.glob("paper_orb_*.json")):
        data = json.loads(p.read_text())
        for t in data.get("trades", []):
            t2 = dict(t)
            t2["date"] = data.get("date")
            trades.append(t2)
    return trades


def compute_metrics(trades: List[dict]) -> Metrics:
    if not trades:
        return Metrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    r = pd.Series([float(t.get("outcome_r", 0.0)) for t in trades])
    total_r = float(r.sum())
    avg_r = float(r.mean())

    wins = r[r > 0]
    losses = r[r <= 0]

    win_rate = float((r > 0).mean())
    avg_win_r = float(wins.mean()) if len(wins) else 0.0
    avg_loss_r = float(losses.mean()) if len(losses) else 0.0

    # drawdown in R
    equity = r.cumsum()
    peak = equity.cummax()
    dd = equity - peak
    max_dd = float(dd.min())

    return Metrics(
        trades=len(r),
        total_r=total_r,
        avg_r=avg_r,
        win_rate=win_rate,
        avg_win_r=avg_win_r,
        avg_loss_r=avg_loss_r,
        max_drawdown_r=max_dd,
    )


def main() -> str:
    trades = load_all_trades()
    m = compute_metrics(trades)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(m.__dict__, indent=2))

    if m.trades == 0:
        return "Metrics Rollup (PAPER)\nNo trades yet."

    return (
        "Metrics Rollup (PAPER)\n"
        f"Trades: {m.trades}\n"
        f"Total: {m.total_r:.2f}R | Avg: {m.avg_r:.2f}R\n"
        f"Win rate: {m.win_rate*100:.0f}% | Avg win: {m.avg_win_r:.2f}R | Avg loss: {m.avg_loss_r:.2f}R\n"
        f"Max drawdown: {m.max_drawdown_r:.2f}R"
    )


if __name__ == "__main__":
    print(main())
