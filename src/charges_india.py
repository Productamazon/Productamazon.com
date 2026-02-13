from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Charges:
    brokerage: float
    stt: float
    exchange_txn: float
    sebi: float
    stamp: float
    gst: float
    total: float


def estimate_equity_intraday_charges(buy_price: float, sell_price: float, qty: int) -> Charges:
    """Rough India equity intraday cost model.

    NOTE:
    - Exact charges vary by broker plan and exchange schedules.
    - This is a conservative estimate to prevent paper over-optimism.

    Assumptions (typical-ish):
    - Brokerage: 0 (many plans) OR capped; we ignore brokerage here and focus on statutory.
    - STT: 0.025% on SELL turnover (intraday equity)
    - Exchange txn: 0.00325% on total turnover (NSE equity approx)
    - SEBI: 10 per crore on total turnover
    - Stamp: ~0.003% on BUY turnover (varies by state; rough)
    - GST: 18% on (brokerage + exchange_txn + sebi) — here brokerage=0

    Turnover = (buy + sell)*qty
    """

    buy_turn = buy_price * qty
    sell_turn = sell_price * qty
    turnover = buy_turn + sell_turn

    brokerage = 0.0

    stt = 0.00025 * sell_turn
    exchange_txn = 0.0000325 * turnover
    sebi = (10.0 / 1e7) * turnover  # 10 per crore => 10 / 1e7 per rupee
    stamp = 0.00003 * buy_turn

    gst = 0.18 * (brokerage + exchange_txn + sebi)

    total = brokerage + stt + exchange_txn + sebi + stamp + gst

    return Charges(
        brokerage=brokerage,
        stt=stt,
        exchange_txn=exchange_txn,
        sebi=sebi,
        stamp=stamp,
        gst=gst,
        total=total,
    )
