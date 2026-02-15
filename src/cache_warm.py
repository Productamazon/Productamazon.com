from __future__ import annotations

import argparse
from datetime import date
import zoneinfo

import pandas as pd

from trading_days import last_n_trading_days
from universe import load_universe
from fyers_client import get_fyers
from data_cache import get_intraday, get_daily
from config import load_config

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=5, help="Number of trading days to warm")
    ap.add_argument("--resolution", type=str, default="5", help="Intraday resolution (minutes)")
    args = ap.parse_args()

    fyers = get_fyers()
    dates = last_n_trading_days(args.days)
    symbols = load_universe()
    # include NIFTY index for regime classification
    try:
        cfg = load_config()
        nifty = cfg.get("filters", {}).get("niftySymbol")
        if nifty and nifty not in symbols:
            symbols = [nifty] + symbols
    except Exception:
        pass

    for d in dates:
        d_str = d.isoformat()
        print(f"Warming {d_str}...")
        for sym in symbols:
            def _fetch_intra(sym=sym, d_str=d_str):
                resp = fyers.history({
                    "symbol": sym,
                    "resolution": args.resolution,
                    "date_format": "1",
                    "range_from": d_str,
                    "range_to": d_str,
                    "cont_flag": "1",
                })
                if not isinstance(resp, dict) or resp.get("s") != "ok":
                    return []
                return resp.get("candles") or []

            # intraday
            _ = get_intraday(sym, d_str, args.resolution, _fetch_intra)

            # daily (lookback for swing)
            start = (d - pd.Timedelta(days=120)).isoformat()
            def _fetch_daily(sym=sym, d_str=d_str, start=start):
                resp = fyers.history({
                    "symbol": sym,
                    "resolution": "D",
                    "date_format": "1",
                    "range_from": start,
                    "range_to": d_str,
                    "cont_flag": "1",
                })
                if not isinstance(resp, dict) or resp.get("s") != "ok":
                    return []
                return resp.get("candles") or []

            _ = get_daily(sym, d_str, _fetch_daily)


if __name__ == "__main__":
    main()
