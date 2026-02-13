from __future__ import annotations

from typing import Iterable


def prefilter_symbols(symbols: Iterable[str]) -> list[str]:
    """Fast prefilter to reduce computation.

    Current rule: keep only NSE: symbols (already true) but allows future extensions.
    This placeholder lets us drop heavy symbols or maintain allow/deny lists.
    """
    out = []
    for s in symbols:
        if s.startswith("NSE:"):
            out.append(s)
    return out
