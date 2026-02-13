# FYERS Watchlist Sync

Goal: automatically push the bot's ranked symbols into a FYERS UI watchlist (e.g., `LADDU_ORB_TOP`).

## Current status (as of this setup)

- The official `fyers-apiv3` Python SDK does **not** expose any watchlist create/update endpoints.
- A quick search inside the installed package also shows **no watchlist** implementation.

## Implication

- We can reliably do:
  - Telegram watchlist updates (ranked list)
  - Alerts and paper-trade approvals

- FYERS UI watchlist auto-sync may require one of these:
  1) Direct REST endpoint support (if FYERS provides it) + custom `requests` calls
  2) Browser automation to click the FYERS UI (fragile; not recommended for trading)

We will only implement (1) if we can confirm a documented, stable endpoint.
