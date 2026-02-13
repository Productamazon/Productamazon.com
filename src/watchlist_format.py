from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Item:
    symbol: str
    score: float
    breakout: bool
    vol_ok: bool
    last_close: float
    or_high: float


def load_items(path: Path) -> list[Item]:
    data: dict[str, Any] = json.loads(path.read_text())
    items = []
    for it in data.get("items", []):
        items.append(
            Item(
                symbol=str(it.get("symbol")),
                score=float(it.get("score", 0)),
                breakout=bool(it.get("breakout")),
                vol_ok=bool(it.get("vol_ok")),
                last_close=float(it.get("last_close", 0)),
                or_high=float(it.get("or_high", 0)),
            )
        )
    return items


def fmt(items: list[Item], top_n: int = 10) -> str:
    lines = []
    lines.append("LADDU_ORB_TOP — Ranked Watchlist (PAPER)")
    lines.append(f"Top {top_n}")
    lines.append("")

    for i, it in enumerate(items[:top_n], 1):
        sym = it.symbol.replace("NSE:", "").replace("-EQ", "")
        flags = []
        if it.breakout:
            flags.append("breakout")
        if it.vol_ok:
            flags.append("vol✅")
        flag_txt = ", ".join(flags) if flags else "—"
        lines.append(
            f"{i:02d}) {sym} | score {it.score:.1f} | close {it.last_close:.2f} | ORH {it.or_high:.2f} | {flag_txt}"
        )

    lines.append("")
    lines.append("Trade approvals will come as a separate message. Reply YES or NO only.")
    return "\n".join(lines)


if __name__ == "__main__":
    base = Path(__file__).resolve().parents[1]
    # pick latest watchlist file if exists
    sig_dir = base / "signals"
    files = sorted(sig_dir.glob("watchlist_*.json"))
    if not files:
        raise SystemExit("No watchlist files found in signals/")
    path = files[-1]
    items = load_items(path)
    print(fmt(items, top_n=10))
