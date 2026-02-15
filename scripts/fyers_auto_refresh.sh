#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"

if [[ ! -d .venv ]]; then
  echo "[fyers_refresh] .venv not found. Run scripts/bootstrap.sh first."
  exit 1
fi

source .venv/bin/activate
python src/fyers_auto_refresh.py
