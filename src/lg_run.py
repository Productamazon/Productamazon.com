from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout

from lg_graph import build_graph
from fyers_health import check_fyers_token


def run_watchlist() -> str:
    h = check_fyers_token()
    if not h.ok:
        return f"ALERT: {h.message}"
    try:
        app = build_graph("watchlist")
        out = app.invoke({})
        return out.get("watchlist_text", "").strip()
    except Exception as e:
        return f"ALERT: watchlist failed: {e}"


def run_nightly() -> str:
    h = check_fyers_token()
    if not h.ok:
        return f"ALERT: {h.message}"
    try:
        app = build_graph("nightly")
        out = app.invoke({})
        return out.get("nightly_test_text", "").strip()
    except Exception as e:
        return f"ALERT: nightly failed: {e}"


def run_approval_monitor() -> str:
    h = check_fyers_token()
    if not h.ok:
        return f"ALERT: {h.message}"
    try:
        sys.path.append("src")
        from approval_monitor import main

        buf = io.StringIO()
        with redirect_stdout(buf):
            main()
        return buf.getvalue().strip()
    except Exception as e:
        return f"ALERT: approval monitor failed: {e}"


def run_daily_report() -> str:
    h = check_fyers_token()
    if not h.ok:
        return f"ALERT: {h.message}"
    try:
        sys.path.append("src")
        from daily_report import main

        buf = io.StringIO()
        with redirect_stdout(buf):
            main()
        return buf.getvalue().strip()
    except Exception as e:
        return f"ALERT: daily report failed: {e}"


def run_swing_alerts() -> str:
    h = check_fyers_token()
    if not h.ok:
        return f"ALERT: {h.message}"
    try:
        sys.path.append("src")
        from swing_alerts import run

        return run().strip()
    except Exception as e:
        return f"ALERT: swing alerts failed: {e}"


def run_drift_guard() -> str:
    try:
        sys.path.append("src")
        from drift_guard import run

        return run().strip()
    except Exception as e:
        return f"ALERT: drift guard failed: {e}"


def run_weekly_report() -> str:
    try:
        sys.path.append("src")
        from archive_weekly import main

        return main().strip()
    except Exception as e:
        return f"ALERT: weekly report failed: {e}"


if __name__ == "__main__":
    # manual test
    print(run_watchlist())
