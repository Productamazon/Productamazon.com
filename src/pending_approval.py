from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import zoneinfo

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
PENDING_PATH = BASE / "data" / "pending_approval.json"
HISTORY_PATH = BASE / "logs" / "approvals.jsonl"


@dataclass
class PendingApproval:
    approval_id: str
    created_at_ist: str
    symbol: str
    entry_ts_ist: str
    entry: float
    stop: float
    target: float
    qty: int


def save_pending(p: PendingApproval) -> None:
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(json.dumps(p.__dict__, indent=2))


def load_pending() -> PendingApproval | None:
    if not PENDING_PATH.exists():
        return None
    data = json.loads(PENDING_PATH.read_text())
    return PendingApproval(**data)


def clear_pending() -> None:
    if PENDING_PATH.exists():
        PENDING_PATH.unlink()


def log_decision(approval_id: str, decision: str, source: str = "telegram") -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts_ist": datetime.now(tz=IST).strftime("%Y-%m-%d %H:%M:%S"),
        "approval_id": approval_id,
        "decision": decision.upper(),
        "source": source,
    }
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
