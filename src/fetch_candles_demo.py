"""Demo: fetch candles for a symbol.

Note: FYERS uses symbol format like 'NSE:SBIN-EQ' etc.
"""

from datetime import datetime, timedelta, timezone

from fyers_client import get_fyers


def main():
    fyers = get_fyers()

    symbol = "NSE:RELIANCE-EQ"
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=5)

    data = {
        "symbol": symbol,
        "resolution": "5",  # 5-minute
        "date_format": "1",
        "range_from": from_dt.strftime("%Y-%m-%d"),
        "range_to": to_dt.strftime("%Y-%m-%d"),
        "cont_flag": "1",
    }

    resp = fyers.history(data)
    print(resp)


if __name__ == "__main__":
    main()
