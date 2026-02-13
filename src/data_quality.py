from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class QualityReport:
    symbol: str
    rows_in: int
    rows_out: int
    had_duplicates: bool
    had_nans: bool
    is_monotonic: bool
    notes: str = ""


def clean_ohlcv_df(df: pd.DataFrame, *, symbol: str = "") -> tuple[pd.DataFrame, QualityReport]:
    if df is None or df.empty:
        return df, QualityReport(symbol=symbol, rows_in=0, rows_out=0, had_duplicates=False, had_nans=False, is_monotonic=True, notes="empty")

    rows_in = len(df)

    # Ensure sorted index
    df2 = df.sort_index()

    had_duplicates = bool(df2.index.duplicated().any())
    if had_duplicates:
        df2 = df2[~df2.index.duplicated(keep="last")]

    # Coerce numeric
    cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df2.columns]
    for c in cols:
        df2[c] = pd.to_numeric(df2[c], errors="coerce")

    had_nans = bool(df2[cols].isna().any().any()) if cols else False
    if had_nans:
        df2 = df2.dropna(subset=cols)

    is_monotonic = bool(df2.index.is_monotonic_increasing)

    rows_out = len(df2)
    notes = []
    if had_duplicates:
        notes.append("dropped_duplicate_timestamps")
    if had_nans:
        notes.append("dropped_nan_rows")
    if not is_monotonic:
        notes.append("index_not_monotonic")

    return df2, QualityReport(
        symbol=symbol,
        rows_in=rows_in,
        rows_out=rows_out,
        had_duplicates=had_duplicates,
        had_nans=had_nans,
        is_monotonic=is_monotonic,
        notes=",".join(notes),
    )
