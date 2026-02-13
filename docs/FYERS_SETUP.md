# FYERS API Setup (Paper Bot)

We use FYERS API v3 auth-code flow.

## 1) Install deps

```bash
cd "G:/ClawdBot WorkSpace/New folder/trading_bot"  # Windows
# In WSL:
cd "/mnt/g/ClawdBot WorkSpace/New folder/trading_bot"

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) Create .env

Copy `.env.example` to `.env` and fill:
- `FYERS_SECRET_KEY` (keep private)

## 3) Generate login URL

```bash
python src/fyers_auth_generate_url.py
```
Open the printed URL, login, and you will get an **auth_code**.

## 4) Exchange auth_code for access_token

```bash
python src/fyers_auth_exchange_token.py "<AUTH_CODE>"
```
This saves token to `data/fyers_token.json`.

## 5) Test candle fetch

```bash
python src/fetch_candles_demo.py
```

## Notes
- Do not paste secrets into chat.
- Token refresh / expiry handling will be added next.
