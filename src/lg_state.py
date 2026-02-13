from __future__ import annotations

from typing import TypedDict, Optional, Any


class TradingState(TypedDict, total=False):
    # Shared
    date: str
    generated_at_ist: str

    # Watchlist
    watchlist_path: str
    watchlist_text: str

    # Approval
    approval_text: str

    # Daily report
    daily_report_text: str

    # Nightly test
    nightly_test_text: str

    # Diagnostics
    info: Any
