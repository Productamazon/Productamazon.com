from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = BASE / "config" / "config.paper.json"


def load_config(path: Path | None = None) -> dict[str, Any]:
    env_path = os.environ.get("TRADINGBOT_CONFIG") or os.environ.get("CONFIG_PATH")
    if env_path:
        p = Path(env_path)
    else:
        p = path or DEFAULT_CONFIG
    return json.loads(p.read_text())
