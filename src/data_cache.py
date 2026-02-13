from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from indicators import to_ohlcv_df

BASE = Path(__file__).resolve().parents[1]
CACHE_BASE = BASE / "data" / "cache"


def _safe_symbol(symbol: str) -> str:
    return symbol.replace(":", "_")


def _cache_path_intraday(symbol: str, d: str, resolution: str) -> Path:
    return CACHE_BASE / _safe_symbol(symbol) / f"{d}_{resolution}.json"


def _cache_path_daily(symbol: str, d: str) -> Path:
    return CACHE_BASE / _safe_symbol(symbol) / f"daily_{d}.json"


def _offline_enabled() -> bool:
    return os.environ.get("FYERS_OFFLINE", "0") == "1"


def _read_cache(path: Path) -> Optional[list]:
    try:
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        return payload.get("candles") or []
    except Exception:
        return None


def _write_cache(path: Path, *, symbol: str, d: str, resolution: str, candles: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "symbol": symbol,
            "date": d,
            "resolution": resolution,
            "fetched_at": datetime.utcnow().isoformat() + "Z",
        },
        "candles": candles,
    }
    path.write_text(json.dumps(payload, indent=2))


def get_intraday(
    symbol: str,
    d: str,
    resolution: str,
    fetch_fn: Callable[[], list],
) -> pd.DataFrame:
    """Return DataFrame from cached intraday candles or fetch + cache.

    fetch_fn should return raw FYERS candles list.
    """
    path = _cache_path_intraday(symbol, d, resolution)
    candles = _read_cache(path)
    if candles is None:
        if _offline_enabled():
            return pd.DataFrame()
        candles = fetch_fn() or []
        if candles:
            _write_cache(path, symbol=symbol, d=d, resolution=resolution, candles=candles)

    if not candles:
        return pd.DataFrame()
    return to_ohlcv_df(candles)


def get_daily(
    symbol: str,
    d: str,
    fetch_fn: Callable[[], list],
) -> pd.DataFrame:
    """Return DataFrame from cached daily candles or fetch + cache.

    fetch_fn should return raw FYERS candles list.
    """
    path = _cache_path_daily(symbol, d)
    candles = _read_cache(path)
    if candles is None:
        if _offline_enabled():
            return pd.DataFrame()
        candles = fetch_fn() or []
        if candles:
            _write_cache(path, symbol=symbol, d=d, resolution="D", candles=candles)

    if not candles:
        return pd.DataFrame()
    return to_ohlcv_df(candles)
