from __future__ import annotations

from datetime import datetime
import zoneinfo

from paper_portfolio_execute import run_day, summarize

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


def main():
    d = datetime.now(tz=IST).date()
    payload = run_day(d)
    print(summarize(payload))


if __name__ == "__main__":
    main()
