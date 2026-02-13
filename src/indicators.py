from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


def to_ohlcv_df(candles: list[list[float]]) -> pd.DataFrame:
    """FYERS history candles → DataFrame.

    FYERS candle format: [epoch, open, high, low, close, volume]
    """
    df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    df = df.set_index("ts").sort_index()
    return df


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = tp * df["volume"]
    return pv.cumsum() / df["volume"].cumsum()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


@dataclass
class ORBLevels:
    or_high: float
    or_low: float


def opening_range(df: pd.DataFrame, start_utc: pd.Timestamp, end_utc: pd.Timestamp) -> Optional[ORBLevels]:
    dfor = df.loc[(df.index >= start_utc) & (df.index < end_utc)]
    if dfor.empty:
        return None
    return ORBLevels(or_high=float(dfor["high"].max()), or_low=float(dfor["low"].min()))
