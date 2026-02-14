#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .venv/bin/activate ]; then
  echo "❌ .venv not found. Run scripts/bootstrap.sh first." >&2
  exit 1
fi

source .venv/bin/activate

python src/cache_warm.py --days 5 --resolution 5
python src/orb_scanner.py
python src/watchlist_format.py
python src/approval_monitor.py
python src/paper_portfolio_execute.py
python src/daily_report.py

echo "✅ daily pipeline complete"
