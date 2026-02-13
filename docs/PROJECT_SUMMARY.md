# Project Summary — Laddu ORB Paper Trading System

Owner: **Mintu** (IST)  
Assistant: **Laddu 🔥**  
Mode: **Paper only** (no real orders)

## Goal
Build a robust, testable intraday trading system that can eventually be profitable by:
- using rule-based signals (start simple)
- enforcing safety filters
- simulating realistic costs/slippage
- collecting paper-trade samples
- iterating via nightly tests + metrics

## Where everything lives
Root folder (2nd workspace):
- `G:\New folder\New folder\trading_bot\`

Key subfolders:
- `config/` settings
- `src/` code
- `data/` tokens + cached universe + approval state
- `signals/` ranked watchlists
- `logs/` paper trade logs
- `reports/` daily + nightly summaries
- `docs/` documentation

## Data source
- Broker API: **FYERS API v3**
- Token stored at: `data/fyers_token.json`

## Universe
- Start: **NIFTY50 equities**
- Symbols are validated via FYERS `quotes()` and cached:
  - `data/valid_universe.json`

## Strategy (v2 Portfolio)
### ORB (Opening Range Breakout) — Long + Short
- Candles: **5-minute**
- Opening range: **09:15–09:30 IST**
- Trade window focus: **09:30–11:30 IST**
- Trigger: close above OR-high (long) / below OR-low (short) + volume confirmation
- Regime: **Trend days only**

### Intraday Mean Reversion — Range Days
- Trigger: VWAP distance in ATR + RSI extremes
- Regime: **Range days only**

### Swing Trend (Daily)
- Pullback or breakout style (config-driven)
- Separate signal stream for smoother equity

## Filters / Safety
- Regime classifier (trend vs range) using NIFTY VWAP + OR expansion + RVOL
- Max 6 trades/day (paper)
- Hard daily loss limit enforced in config
- Approval cooldown to avoid alert spam

## Paper realism
- Slippage model (bps each side)
- India intraday charges estimate:
  - STT, exchange txn, SEBI, stamp, GST
- Extra fixed buffer cost (config)

## Telegram automation (active cron jobs)
All messages delivered to Telegram chat id: **815275272**

1) **Health ping** — 09:29 IST (Mon–Fri)
2) **Top-10 watchlist** — 09:31 IST (Mon–Fri)
3) **Approvals** — checks every 2 minutes during 09–11 IST (Mon–Fri)
   - Script sends only if fresh signal exists
   - Reply with **YES/NO** when approval message arrives
4) **Daily paper report** — 15:20 IST (Mon–Fri)
   - Profit/Loss in ₹ and result in R
5) **Nightly test loop** — 20:00 IST (Mon–Fri)
   - Micro-sweep on ORB volumeMultiplier (1.1/1.2/1.3)
   - Sends recommendation (does not auto-apply)

## Key scripts
- Watchlist: `src/orb_scanner.py` → `signals/watchlist_YYYY-MM-DD.json`
- Telegram formatting: `src/watchlist_format.py`
- Approval generation: `src/approval_monitor.py`
- Paper execution + daily summary: `src/daily_report.py` / `src/paper_orb_execute.py`
- Nightly tests: `src/nightly_backtest.py`
- Health check: `src/health_check.py`

## Learning mode
Learning mode is ON. Meaning:
- prioritize collecting clean samples
- iterate slowly with guardrails
- no uncontrolled self-modification of rules

## If a new chat/session starts
This project persists because:
- code/config/data are saved in the folder above
- schedules are stored in OpenClaw cron

Reference docs:
- `docs/ENGINE_STATUS.md`
- `docs/SESSION_PERSISTENCE.md`

---
Last updated (UTC): 2026-02-06
