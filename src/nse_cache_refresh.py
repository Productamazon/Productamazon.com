from __future__ import annotations

from trading_days import get_nse_holidays, get_market_status


def main() -> None:
    holidays = get_nse_holidays()
    ms = get_market_status()

    print(f"NSE HOLIDAYS cached: {len(holidays)}")
    if isinstance(ms, dict):
        states = ms.get("marketState", [])
        cm = next((s for s in states if str(s.get("market", "")).lower().startswith("capital")), None)
        if cm:
            print(f"MARKET STATUS: {cm.get('marketStatus')} (tradeDate={cm.get('tradeDate')})")
        else:
            print("MARKET STATUS: OK (no capital market entry found)")
    else:
        print("MARKET STATUS: unavailable")


if __name__ == "__main__":
    main()
