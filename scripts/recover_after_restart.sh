#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"

if [[ ! -d .venv ]]; then
  echo "[recover] .venv not found. Run scripts/bootstrap.sh first."
  exit 1
fi

source .venv/bin/activate

mkdir -p logs

echo "[recover] $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

# Try to ensure OpenClaw gateway is running (if installed)
if command -v openclaw >/dev/null 2>&1; then
  openclaw gateway start >/dev/null 2>&1 || true
fi

# 1) Health check (token + config)
python src/health_check.py

# 2) Warm cache (last 5 trading days)
python src/cache_warm.py --days 5 --resolution 5

# 3) If within market window, regenerate watchlist + check approvals (safe/no spam)
python - <<'PY'
from datetime import datetime, time
from pathlib import Path
import zoneinfo
import sys

sys.path.append('src')
from lg_run import run_watchlist, run_approval_monitor

IST = zoneinfo.ZoneInfo('Asia/Kolkata')
now = datetime.now(IST)

if now.weekday() >= 5:
    print('[recover] Weekend: skip watchlist/approvals')
    raise SystemExit(0)

# Only run during active window (approx 09:30–11:30 IST)
if not (time(9, 30) <= now.time() <= time(11, 30)):
    print('[recover] Outside 09:30–11:30 IST window: skip watchlist/approvals')
    raise SystemExit(0)

signals = Path('signals') / f"watchlist_{now.date().isoformat()}.json"
if not signals.exists():
    out = run_watchlist().strip()
    if out:
        print(out)
else:
    print('[recover] Watchlist already exists for today')

out2 = run_approval_monitor().strip()
if out2:
    print(out2)
PY

echo "[recover] done"
