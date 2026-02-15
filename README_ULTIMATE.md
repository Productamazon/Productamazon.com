# Ultimate README — Trading Bot (Paper Mode)

Last updated: 2026-02-15 14:28 UTC
Owner: Mintu (IST) • Assistant: Laddu 🔥

This file is the **handoff summary** for the next session so it can pick up immediately.

---

## 1) Project purpose (Paper only)
A rule‑based intraday trading system using FYERS API, with realistic costs/slippage, risk gates, and daily/weekly reporting. **No live orders.**

## 2) Repo locations
- **WSL/Linux path:** `/mnt/g/New folder/New folder/trading_bot`
- **Windows path:** `G:\New folder\New folder\trading_bot`

## 3) Quick start (venv + run)
```bash
cd "/mnt/g/New folder/New folder/trading_bot"
source .venv/bin/activate
```

### Common runs
- Warm cache:
  ```bash
  python src/cache_warm.py --days 5 --resolution 5
  ```
- ORB watchlist:
  ```bash
  python src/orb_scanner.py
  ```
  → outputs `signals/watchlist_YYYY-MM-DD.json`
- Watchlist formatter:
  ```bash
  python src/watchlist_format.py
  ```
- Approvals (Telegram):
  ```bash
  python src/approval_monitor.py
  ```
- Paper execution (portfolio engine):
  ```bash
  python src/paper_portfolio_execute.py
  ```
- Daily report:
  ```bash
  python src/daily_report.py
  ```
- 30‑day backtest:
  ```bash
  python src/backtest_30d.py
  ```
  (Offline mode: `FYERS_OFFLINE=1 python src/backtest_30d.py`)

### Makefile / scripts (new)
```bash
make install
make daily
make backtest
make backtest-offline

bash scripts/bootstrap.sh
bash scripts/run_daily.sh
bash scripts/run_backtest.sh        # online
bash scripts/run_backtest.sh offline

# Recovery after laptop restart/power loss
bash scripts/recover_after_restart.sh
```

## 4) Current configuration snapshot
File: `config/config.paper.json`
- **Mode:** paper
- **Timezone:** Asia/Kolkata
- **Universe:** NIFTY50
- **Candle interval:** 5m
- **Trading windows:**
  - No trade: 09:15–09:30
  - Primary: 09:30–11:30
  - No new entries after 15:00
  - Force exit by 15:25
- **Risk:**
  - ₹100 per trade
  - Max 2 trades/day
  - Hard daily loss ₹500, soft stop ₹350
  - Regime sizing: trend 1.0 / range 0.6
- **Execution sim:** 10 bps each side + ₹2 fixed
- **Strategies enabled:** ORB (tuned), Swing (Mean Reversion disabled)
- **ORB tuned:** minORRangePct 0.25, minORtoATR 1.0, volumeMultiplier 1.5
- **Learning mode:** ON
- **Drift guard:** lookback 30d, pause 2 days on poor stats
- **Volatility clamp:** max ATR% 3.5
- **Sector filter:** max 1 per sector/day

## 5) Key folders
- `src/` — all code
- `config/` — config (paper/live, risk, strategy params)
- `data/` — FYERS token, cached universe, approval state
- `signals/` — watchlists + trade candidates
- `logs/` — simulated fills + decisions
- `reports/` — daily/weekly/backtest outputs
- `docs/` — design + persistence notes

## 6) FYERS status
- Token stored: `data/fyers_token.json`
- Validated universe cache: `data/valid_universe.json`
- Optional auto-refresh: `FYERS_AUTO_REFRESH=1` + TOTP/PIN vars (local only)

**Do not paste secrets into chat.** Use `.env` locally.

## 7) Automations (OpenClaw cron)
From `docs/PROJECT_SUMMARY.md`:
- 09:29 IST Mon–Fri: Health ping
- 09:31 IST Mon–Fri: Top‑10 watchlist to Telegram
- 09:00–11:00 IST: approval checks every 2 minutes
- 15:20 IST Mon–Fri: Daily paper report
- 20:00 IST Mon–Fri: nightly test loop (ORB volumeMultiplier sweep)

Cron jobs live in OpenClaw Gateway state (use `openclaw cron list` to confirm).

## 7.1) Recovery plan (laptop restart/power loss)
Run this once after the laptop comes back online:
```bash
bash scripts/recover_after_restart.sh
```
What it does:
- Starts OpenClaw gateway if available
- Health check (token + config)
- Warm last 5 trading days cache
- If within 09:30–11:30 IST and market is open (NSE holiday + market status), regenerates watchlist and checks approvals
- NSE cache refresh script: `scripts/refresh_nse_cache.sh`
- FYERS auto-refresh script: `scripts/fyers_auto_refresh.sh`

Auto-start on Windows login (created):
- Startup file: `C:\Users\acer\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\tradingbot_start.cmd`
- Runs `scripts/recover_after_restart.sh` on login and logs to `logs/recover_startup.log`

## 8) What happened in *this* session (2026‑02‑15)
- Disabled Mean Reversion in paper config.
- ORB tuned (minORRangePct 0.25, minORtoATR 1.0). Tested volumeMultiplier:
  - **vMult 1.5 (current):** 30D backtest 24 trades, **-7.51R**, PnL ₹-750.51
    Saved: /mnt/g/New folder/New folder/trading_bot/reports/backtests/backtest_30d_2026-02-15_071901_paper.json
  - **vMult 1.3:** 30D backtest 24 trades, **-11.46R**, PnL ₹-1146.19
    Saved: /mnt/g/New folder/New folder/trading_bot/reports/backtests/backtest_30d_2026-02-15_064357_paper.json
- Candidate test (not applied): minORRangePct 0.2, vMult 1.3 → 30 trades, **-16.15R**, PnL ₹-1614.97
  Saved: /mnt/g/New folder/New folder/trading_bot/reports/backtests/backtest_30d_2026-02-15_065402_paper_orb_candidate.json
- FYERS token refreshed; health_check OK (07:38 IST). Cache warmed for last 5 trading days (2026‑02‑09…13).
- Recovery + auto‑start: `scripts/recover_after_restart.sh` + Windows Startup task `tradingbot_start.cmd` (logs to `logs/recover_startup.log`).
- Deep debug fixes:
  - Watchlist now uses ORB config (minORRangePct, minORtoATR, volumeMultiplier) instead of hardcoded defaults.
  - ORB scanner now uses cached intraday data (offline-friendly) and applies OR/ATR filter.
- Market-closed guards + NSE cache:
  - NSE holiday calendar cache + market status cache (UA helper).
  - Watchlist/approval monitor skip when market closed/holiday.
- Optional FYERS auto-refresh:
  - `src/fyers_auto_refresh.py` (TOTP + PIN) and `FYERS_AUTO_REFRESH=1` in health_check.
  - Fixed to use **API v3 token endpoint**; auto-refresh tested OK.
- Profitability extension (learning mode):
  - Nightly sweep now supports multi-parameter grid (vol_mult, min OR %, min OR/ATR, stop ATR, targetR, entry_end).
  - Controlled by env vars: SWEEP_VOL_MULT, SWEEP_MIN_OR_PCT, SWEEP_MIN_OR_ATR, SWEEP_STOP_ATR, SWEEP_TGT_R, SWEEP_ENTRY_END.
  - Fixed entry-window bug in sweep (exit window now defined correctly).
- Git hygiene:
  - Added `data/nse/` cache to `.gitignore` (avoid committing live cache).
- Pushed changes to GitHub (main updated).
- Adobe Express research links saved:
  - https://developer.adobe.com/express/
  - https://developer.adobe.com/express/add-ons/
  - https://helpx.adobe.com/in/express/web/add-ons-and-integrations/add-ons-overview.html
  - https://github.com/AdobeDocs/express-add-on-samples

## 9) Useful docs for next session
- `docs/PROJECT_SUMMARY.md`
- `docs/ENGINE_STATUS.md`
- `docs/SESSION_PERSISTENCE.md`
- `docs/FYERS_SETUP.md`

---

If anything changes (strategy rules, cron schedule, config), update this file.
