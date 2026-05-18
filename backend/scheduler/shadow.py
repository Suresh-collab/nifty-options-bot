"""
Shadow logger — records both the current rule's signal and what the tuned
rule WOULD have signaled, side-by-side, for live comparison. Runs every 5
minutes during market hours (Mon-Fri, 09:15-15:30 IST).

The current production signal_engine.py is NOT modified. This job only OBSERVES.
After ~7 days of accumulated rows, compare via GET /api/admin/shadow-report.

If the tuned rule consistently produces better signals on live data, that's
the green light for Phase 3 (promoting it into ai/signal_engine.py).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import text

from db.base import get_session_factory

logger = logging.getLogger(__name__)

SYMBOLS = ("NIFTY", "BANKNIFTY")
INTERVAL = "15m"


def _ist_now_market_open() -> bool:
    """True if current UTC time falls within 09:15-15:30 IST, Mon-Fri."""
    now = datetime.now(timezone.utc)
    ist_hour = (now.hour + 5) % 24
    ist_minute = (now.minute + 30) % 60
    if now.minute >= 30:
        ist_hour = (now.hour + 6) % 24 if (now.minute + 30) >= 60 else ist_hour
    if now.weekday() >= 5:
        return False
    after_open  = (ist_hour > 9) or (ist_hour == 9 and ist_minute >= 15)
    before_close = (ist_hour < 15) or (ist_hour == 15 and ist_minute <= 30)
    return after_open and before_close


def _compute_signals(symbol: str) -> dict | None:
    """Fetch latest bar + indicators, run both rules. Returns dict or None on failure."""
    from data.market_data import get_ohlcv
    from indicators.engine import compute_indicators, _rsi, _macd, _supertrend
    from backtesting.engine import _score_with_weights, _TUNED_RULE
    from ai.signal_engine import generate_signal
    from data.options_chain import get_options_chain

    try:
        df = get_ohlcv(symbol, INTERVAL)
        if df is None or df.empty or len(df) < 50:
            return None
        spot = float(df["Close"].iloc[-1])

        # Current rule: go through the live signal_engine for fidelity
        indicators = compute_indicators(df)
        chain = get_options_chain(symbol) or {}
        current = generate_signal(symbol, spot, chain.get("expiry", ""), indicators, chain)

        # Tuned rule: compute via the parameterised helper directly
        rsi_s = _rsi(df["Close"], 14).values
        macd_l, sig_l, hist = _macd(df["Close"], 12, 26, 9)
        _, st_dir = _supertrend(df["High"], df["Low"], df["Close"], 7, 3.0)
        tuned_dir_arr = _score_with_weights(
            st_dir.values, macd_l.values, sig_l.values, rsi_s,
            w_st=_TUNED_RULE["w_st"], w_macd=_TUNED_RULE["w_macd"],
            w_rsi=_TUNED_RULE["w_rsi"], rsi_lo=_TUNED_RULE["rsi_lo"],
            rsi_hi=_TUNED_RULE["rsi_hi"], threshold=_TUNED_RULE["threshold"],
        )
        latest = int(tuned_dir_arr[-1])
        tuned_signal = {1: "BUY_CE", -1: "BUY_PE", 0: "AVOID"}[latest]

        return {
            "symbol": symbol,
            "interval": INTERVAL,
            "spot": spot,
            "current_signal": current.get("direction", "AVOID"),
            "tuned_signal": tuned_signal,
            "current_score": float(indicators.get("combined_score", 0.0)),
            "tuned_score": None,  # not directly comparable — different weighting
            "rsi": float(rsi_s[-1]) if not np.isnan(rsi_s[-1]) else None,
            "macd_hist": float(hist.values[-1]) if not np.isnan(hist.values[-1]) else None,
            "st_dir": int(st_dir.values[-1]),
        }
    except Exception as exc:
        logger.warning("shadow %s failed: %s", symbol, exc)
        return None


async def shadow_signal_job() -> None:
    """Compute current + tuned signals for each symbol and persist."""
    if not _ist_now_market_open():
        return

    rows = []
    for symbol in SYMBOLS:
        row = _compute_signals(symbol)
        if row is not None:
            row["agree"] = (row["current_signal"] == row["tuned_signal"])
            rows.append(row)

    if not rows:
        return

    sf = get_session_factory()
    async with sf() as sess:
        for r in rows:
            await sess.execute(
                text("""
                    INSERT INTO signal_shadow
                    (symbol, interval, spot, current_signal, tuned_signal, agree,
                     current_score, tuned_score, rsi, macd_hist, st_dir)
                    VALUES
                    (:symbol, :interval, :spot, :current_signal, :tuned_signal, :agree,
                     :current_score, :tuned_score, :rsi, :macd_hist, :st_dir)
                """),
                r,
            )
        await sess.commit()
    logger.info("shadow logged %d rows", len(rows))
