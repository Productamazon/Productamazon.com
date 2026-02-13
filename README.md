# trading_bot (Paper Mode)

Owner: Mintu (IST)  
Assistant: Laddu 🔥

This folder is the implementation workspace for **Ultimate plan v2.1 (Paper Mode)**.

## Structure
- `config/` – configuration (paper/live, risk, strategy params)
- `data/` – cached candles / symbol metadata
- `signals/` – generated watchlists and pending trade candidates
- `logs/` – every decision + simulated fills
- `reports/` – daily summaries
- `src/` – code
- `docs/` – notes/specs

## Current status
- Folder structure created.
- Paper config template created: `config/config.paper.json`

## FYERS status
- Auth + token saved: `data/fyers_token.json`
- Candle fetch verified.

Do **not** paste secrets into chat. Prefer storing them in a local `.env` file.

## Cache (fast backtests)
Warm cache for last N trading days:
```bash
python src/cache_warm.py --days 5 --resolution 5
```

Offline backtests (no network):
```bash
FYERS_OFFLINE=1 python src/backtest_30d.py
```

## Next
- Run ORB scanner: `python src/orb_scanner.py`
- This generates `signals/watchlist_YYYY-MM-DD.json`
