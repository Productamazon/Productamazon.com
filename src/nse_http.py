from __future__ import annotations

import time
from typing import Any, Optional

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def fetch_json(url: str, *, timeout: int = 10, retries: int = 2, backoff: float = 1.5) -> Optional[Any]:
    """Fetch JSON from NSE with browser-like headers + cookie warmup.

    Returns parsed JSON or None on failure.
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": UA,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-IN,en;q=0.9",
            "Connection": "keep-alive",
            "Referer": "https://www.nseindia.com/",
        }
    )

    # Warm up cookies (NSE often blocks direct API calls)
    try:
        session.get("https://www.nseindia.com", timeout=timeout)
    except Exception:
        pass

    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:  # pragma: no cover - network-dependent
            last_err = e
        time.sleep(backoff * (attempt + 1))

    return None
