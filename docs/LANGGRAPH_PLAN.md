# LangGraph migration (Full-in)

We are migrating the trading_bot orchestration to **LangGraph** while keeping:
- deterministic rules (LLM not deciding trades)
- Telegram delivery via OpenClaw cron

## What is already wired

- LangGraph deps installed in `.venv`
- Wrapper runner: `src/lg_run.py`
  - `run_watchlist()`
  - `run_approval_monitor()`
  - `run_daily_report()`
  - `run_nightly()`

Cron jobs now call these wrappers so we have a single stable interface.

## Next improvements (automatic, no user interaction)
- Expand LangGraph state to carry metrics (rolling expectancy, drawdown)
- Add parameter suggestions file and apply changes only after repeated confirmation windows
- Add unit-test style checks on data availability and on signal-generation invariants
