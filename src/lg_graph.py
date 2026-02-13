from __future__ import annotations

"""LangGraph orchestration for the trading_bot pipeline.

Design goals:
- Deterministic, auditable flow (no LLM deciding trades).
- Each node calls existing scripts/modules that already work.
- Cron calls a single entrypoint per workflow (watchlist / approval / daily / nightly).

We keep Telegram delivery in OpenClaw cron, not inside the graph.
"""

from datetime import datetime
from pathlib import Path
import zoneinfo

from langgraph.graph import StateGraph, END

from lg_state import TradingState

# Reuse our existing modules
from orb_scanner import scan_orb_for_date, save_watchlist
from watchlist_format import load_items, fmt
from approval_monitor import main as approval_main
from daily_report import main as daily_main
from nightly_backtest import run as nightly_run

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]


def node_watchlist(state: TradingState) -> TradingState:
    d = datetime.now(tz=IST).date()
    signals = scan_orb_for_date(d)
    out = BASE / "signals" / f"watchlist_{d.strftime('%Y-%m-%d')}.json"
    save_watchlist(signals, out, top_n=15)

    items = load_items(out)
    state["date"] = d.strftime("%Y-%m-%d")
    state["generated_at_ist"] = datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S")
    state["watchlist_path"] = str(out)
    state["watchlist_text"] = fmt(items, top_n=10)
    return state


def node_approval(state: TradingState) -> TradingState:
    # approval_monitor prints approval text or prints nothing.
    # We capture stdout via run wrapper in lg_run.py (not here).
    return state


def node_daily(state: TradingState) -> TradingState:
    # daily_report prints report text.
    return state


def node_nightly(state: TradingState) -> TradingState:
    state["nightly_test_text"] = nightly_run()
    return state


def build_graph(kind: str):
    g = StateGraph(TradingState)

    if kind == "watchlist":
        g.add_node("watchlist", node_watchlist)
        g.set_entry_point("watchlist")
        g.add_edge("watchlist", END)
        return g.compile()

    if kind == "nightly":
        g.add_node("nightly", node_nightly)
        g.set_entry_point("nightly")
        g.add_edge("nightly", END)
        return g.compile()

    # approval and daily are executed via wrappers that capture their print output.
    raise ValueError(f"Unknown graph kind: {kind}")
