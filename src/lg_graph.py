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
from config import load_config
from trading_days import is_trading_day, is_market_open

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]


def node_watchlist(state: TradingState) -> TradingState:
    now = datetime.now(tz=IST)
    d = now.date()
    cfg = load_config()
    orb = cfg.get("strategies", {}).get("ORB", {})
    vol_mult = float(orb.get("volumeMultiplier", 1.2))
    min_or_pct = float(orb.get("minORRangePct", 0.15))
    min_or_atr = float(orb.get("minORtoATR", 0.0))
    max_or_pct = float(orb.get("maxORRangePct", 0.0))
    max_or_atr = float(orb.get("maxORtoATR", 0.0))

    out = BASE / "signals" / f"watchlist_{d.strftime('%Y-%m-%d')}.json"

    # Market closed guard
    if not is_trading_day(d):
        notes = "Market closed (holiday/weekend) - watchlist skipped"
        save_watchlist([], out, top_n=15, notes=notes)
        state["date"] = d.strftime("%Y-%m-%d")
        state["generated_at_ist"] = now.strftime("%Y-%m-%d %H:%M:%S")
        state["watchlist_path"] = str(out)
        state["watchlist_text"] = notes
        return state
    if not is_market_open(now):
        notes = "Market closed - watchlist skipped"
        save_watchlist([], out, top_n=15, notes=notes)
        state["date"] = d.strftime("%Y-%m-%d")
        state["generated_at_ist"] = now.strftime("%Y-%m-%d %H:%M:%S")
        state["watchlist_path"] = str(out)
        state["watchlist_text"] = notes
        return state

    signals = scan_orb_for_date(
        d,
        volume_multiplier=vol_mult,
        min_or_range_pct=min_or_pct,
        min_or_atr_ratio=min_or_atr,
        max_or_range_pct=max_or_pct,
        max_or_atr_ratio=max_or_atr,
    )
    save_watchlist(signals, out, top_n=15)

    items = load_items(out)
    state["date"] = d.strftime("%Y-%m-%d")
    state["generated_at_ist"] = now.strftime("%Y-%m-%d %H:%M:%S")
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
