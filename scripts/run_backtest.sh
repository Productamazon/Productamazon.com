#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .venv/bin/activate ]; then
  echo "❌ .venv not found. Run scripts/bootstrap.sh first." >&2
  exit 1
fi

source .venv/bin/activate

if [ "${1:-}" = "offline" ]; then
  FYERS_OFFLINE=1 python src/backtest_30d.py
else
  python src/backtest_30d.py
fi

echo "✅ backtest complete"
