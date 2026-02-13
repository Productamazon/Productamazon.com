from __future__ import annotations


def apply_slippage(price: float, side: str, bps_each_side: float) -> float:
    """Apply simple slippage model.

    side:
      - 'BUY'  -> worse (higher)
      - 'SELL' -> worse (lower)
    """
    bps = bps_each_side / 10000.0
    if side.upper() == "BUY":
        return price * (1.0 + bps)
    if side.upper() == "SELL":
        return price * (1.0 - bps)
    raise ValueError(f"unknown side {side}")
