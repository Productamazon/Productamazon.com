from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

import zoneinfo


IST = zoneinfo.ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class SessionWindow:
    start: time
    end: time

    def contains(self, t: time) -> bool:
        return self.start <= t <= self.end


def now_ist() -> datetime:
    return datetime.now(tz=timezone.utc).astimezone(IST)


def ist_date_str(dt: datetime) -> str:
    return dt.astimezone(IST).strftime("%Y-%m-%d")


def parse_hhmm(s: str) -> time:
    hh, mm = s.split(":")
    return time(hour=int(hh), minute=int(mm))
