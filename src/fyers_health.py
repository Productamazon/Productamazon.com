from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from fyers_client import get_fyers

BASE = Path(__file__).resolve().parents[1]
TOKEN_PATH = BASE / "data" / "fyers_token.json"


@dataclass
class FyersHealth:
    ok: bool
    message: str


def check_fyers_token() -> FyersHealth:
    if not TOKEN_PATH.exists():
        return FyersHealth(False, "Missing token file: data/fyers_token.json")

    try:
        fyers = get_fyers()
        resp = fyers.get_profile()
        if isinstance(resp, dict) and resp.get("s") == "ok":
            return FyersHealth(True, "FYERS token OK")
        # Common token failures
        msg = ""
        if isinstance(resp, dict):
            msg = resp.get("message") or str(resp)
        else:
            msg = str(resp)
        return FyersHealth(False, f"FYERS auth failed: {msg}")
    except Exception as e:
        return FyersHealth(False, f"FYERS check exception: {e}")
