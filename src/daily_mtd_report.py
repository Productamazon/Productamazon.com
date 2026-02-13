from __future__ import annotations

from datetime import datetime
from pathlib import Path
import zoneinfo

from monthly_equity_curve import plot_png
from monthly_summary import summarize

IST = zoneinfo.ZoneInfo("Asia/Kolkata")
BASE = Path(__file__).resolve().parents[1]
REPORTS_DIR = BASE / "reports"


def run() -> tuple[str, Path | None]:
    today = datetime.now(tz=IST).date()
    month_prefix = today.strftime("%Y-%m")

    summary = summarize(month_prefix)
    png_path = plot_png(month_prefix=month_prefix)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_txt = REPORTS_DIR / f"daily_mtd_summary_{today.isoformat()}.txt"
    out_txt.write_text(summary)

    return summary, png_path


if __name__ == "__main__":
    summary, png = run()
    print(summary)
    if png:
        print(f"PNG: {png}")
