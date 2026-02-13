from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import zoneinfo

from fyers_client import get_fyers
from nifty50_symbols import NIFTY50

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
CACHE = BASE / "data" / "valid_universe.json"


def is_symbol_valid(symbol: str) -> bool:
    """Check via FYERS quotes endpoint (fast) whether a symbol is accepted."""
    fyers = get_fyers()
    resp = fyers.quotes({"symbols": symbol})
    return isinstance(resp, dict) and resp.get("s") == "ok"


def build_valid_universe(symbols: Iterable[str] = NIFTY50) -> list[str]:
    valid = []
    for s in symbols:
        try:
            if is_symbol_valid(s):
                valid.append(s)
        except Exception:
            # network hiccup etc.
            continue
    return valid


def load_universe() -> list[str]:
    if CACHE.exists():
        data = json.loads(CACHE.read_text())
        return list(data.get("symbols", []))
    # build once if missing
    syms = build_valid_universe(NIFTY50)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(
            {
                "generated_at_ist": datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S"),
                "symbols": syms,
            },
            indent=2,
        )
    )
    return syms


if __name__ == "__main__":
    syms = build_valid_universe(NIFTY50)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({"generated_at_ist": datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S"), "symbols": syms}, indent=2))
    print(f"Valid symbols: {len(syms)}/{len(NIFTY50)}")
    print("Sample:", syms[:10])
