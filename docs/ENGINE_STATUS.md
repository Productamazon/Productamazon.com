# Engine Status (Best Version Roadmap)

## Implemented
- FYERS auth + token storage (`data/fyers_token.json`)
- Candle fetch verified
- Valid universe cache (`data/valid_universe.json`) via quotes validation
- ORB ranked watchlist generator (`src/orb_scanner.py`) using validated universe
- Watchlist formatter for Telegram (`src/watchlist_format.py`) Top 10
- Portfolio paper engine (ORB + Mean Reversion + Swing signals): `src/paper_portfolio_execute.py`
  - slippage model
  - India charges estimate
  - regime classifier (trend vs range)
  - long + short ORB (trend days)
  - intraday mean reversion (range days)
  - swing trend signals (daily)
  - logs to `logs/paper_portfolio_YYYY-MM-DD.json`
  - daily report text to `reports/daily_YYYY-MM-DD.txt`
- Approval monitor (Telegram YES/NO template) now supports ORB long/short + Mean Reversion based on regime, with stricter A+/A grades, risk gates + cooldown, and logs approvals: `src/approval_monitor.py`
- Added speed prefilter: `src/speed_filters.py`
- Drift guard + kill-switch (auto pause on poor stats) + A+-only during drawdown: `src/drift_guard.py` (daily cron)
- Volatility clamp + sector filter in approvals: `src/approval_monitor.py`
- Weekly performance report + auto-archive + health score + MTD equity curve: `src/weekly_report.py`, `src/archive_weekly.py`, `src/monthly_equity_curve.py` (weekly cron)
- 30-day portfolio backtest script: `src/backtest_30d.py`
- Swing alerts generator: `src/swing_alerts.py`

## Automated via OpenClaw cron
- 09:31 IST Mon–Fri: Send Top-10 watchlist on Telegram
- 15:20 IST Mon–Fri: Send daily paper report on Telegram

## Next (optional)
- Add full India equity charges model (STT, exchange txn, SEBI, GST, stamp duty) instead of fixed cost
- Add smarter trade selection (avoid overlapping signals; add cooldown)
- Add second strategy (Pullback) after enough ORB trades
