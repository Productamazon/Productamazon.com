from __future__ import annotations

from datetime import datetime
from pathlib import Path
import zoneinfo

from weekly_report import run

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
ARCHIVE_DIR = BASE / "reports" / "weekly_archive"


def main() -> str:
    text = run()
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    out = ARCHIVE_DIR / f"weekly_{datetime.now(tz=IST).strftime('%Y-%m-%d_%H%M')}.txt"
    out.write_text(text)
    return text


if __name__ == "__main__":
    print(main())
