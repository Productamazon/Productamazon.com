from __future__ import annotations

from datetime import datetime
import zoneinfo

from config import load_config
from swing_trend import fetch_daily, swing_breakout_signal, swing_pullback_signal
from universe import load_universe

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


def run() -> str:
    cfg = load_config()
    swing_cfg = cfg.get("strategies", {}).get("SWING", {})
    if not bool(swing_cfg.get("enabled", True)):
        return "Swing alerts: disabled."

    style = str(swing_cfg.get("style", "pullback"))
    d = datetime.now(tz=IST).date()

    signals = []
    for sym in load_universe():
        df = fetch_daily(sym, d)
        if df.empty:
            continue
        if style == "breakout":
            sig = swing_breakout_signal(
                df,
                lookback=int(swing_cfg.get("breakoutLookback", 20)),
                atr_mult=float(swing_cfg.get("atrMult", 2.0)),
            )
        else:
            sig = swing_pullback_signal(
                df,
                ema_fast=int(swing_cfg.get("emaFast", 20)),
                ema_slow=int(swing_cfg.get("emaSlow", 50)),
                atr_mult=float(swing_cfg.get("atrMult", 2.0)),
            )
        if sig:
            sig.symbol = sym
            signals.append(sig)

    if not signals:
        return "Swing alerts: no signals today."

    lines = [f"Swing Alerts ({style}) — {d.isoformat()}"]
    for s in signals[:10]:
        sym = s.symbol.replace("NSE:", "").replace("-EQ", "")
        lines.append(f"- {sym} {s.direction} @ {s.entry:.2f} | stop {s.stop:.2f} ({s.reason})")
    if len(signals) > 10:
        lines.append(f"(+{len(signals)-10} more)")
    return "\n".join(lines)


if __name__ == "__main__":
    print(run())
