#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"

if [[ ! -d .venv ]]; then
  echo "[nse_cache] .venv not found. Run scripts/bootstrap.sh first."
  exit 1
fi

source .venv/bin/activate
python src/nse_cache_refresh.py
