from __future__ import annotations

import hashlib
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def build_version_stamp() -> dict:
    cfg = BASE / "config" / "config.paper.json"
    parts = {
        "config_sha256": sha256_file(cfg) if cfg.exists() else None,
    }

    # Hash key scripts so we can track changes even without git
    key_files = [
        BASE / "src" / "orb_scanner.py",
        BASE / "src" / "approval_monitor.py",
        BASE / "src" / "paper_orb_execute.py",
        BASE / "src" / "nightly_backtest.py",
        BASE / "src" / "lg_run.py",
    ]
    parts["code_sha256"] = hashlib.sha256(
        "\n".join([sha256_file(p) for p in key_files if p.exists()]).encode("utf-8")
    ).hexdigest()

    return parts
