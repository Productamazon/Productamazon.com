SHELL := /bin/bash
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: venv install cache orb watchlist approvals paper report backtest backtest-offline daily

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

cache:
	$(PY) src/cache_warm.py --days 5 --resolution 5

orb:
	$(PY) src/orb_scanner.py

watchlist:
	$(PY) src/watchlist_format.py

approvals:
	$(PY) src/approval_monitor.py

paper:
	$(PY) src/paper_portfolio_execute.py

report:
	$(PY) src/daily_report.py

backtest:
	$(PY) src/backtest_30d.py

backtest-offline:
	FYERS_OFFLINE=1 $(PY) src/backtest_30d.py

daily:
	bash scripts/run_daily.sh
