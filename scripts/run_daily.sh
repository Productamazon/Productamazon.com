#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .venv/bin/activate ]; then
  echo "❌ .venv not found. Run scripts/bootstrap.sh first." >&2
  exit 1
fi

source .venv/bin/activate

echo "[1/6] cache_warm"
python src/cache_warm.py --days 5 --resolution 5

echo "[2/6] orb_scanner"
python src/orb_scanner.py

echo "[3/6] watchlist_format"
python src/watchlist_format.py

echo "[4/6] approval_monitor"
python src/approval_monitor.py

echo "[5/6] paper_portfolio_execute"
python src/paper_portfolio_execute.py

echo "[6/6] daily_report"
python src/daily_report.py

echo "✅ daily pipeline complete"
