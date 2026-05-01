"""
Feature pipeline for Phase 2 ML models.

All features are backward-looking only — no look-ahead leakage.
Features at row t use only data available at or before bar t.

Columns produced
────────────────
ret_1, ret_5, ret_15, ret_30     — price return over N bars (pct)
rsi                               — RSI-14 normalised to [0, 1]
macd_line, macd_hist              — MACD line and histogram (ATR-normalised)
macd_cross                        — +1 bullish cross, -1 bearish cross, 0 none
supertrend_dir                    — +1 bullish, -1 bearish
bb_pos                            — Bollinger position: (c−lower)/(upper−lower)
bb_width                          — (upper−lower)/mid
atr_pct                           — ATR-14 / close  (volatility normalised)
ema_cross                         — sign(EMA9 − EMA21)
vol_ratio                         — volume / 20-bar volume MA
time_sin, time_cos                — cyclical hour-of-day (5m data only; 0 for daily)
dow_sin, dow_cos                  — cyclical day-of-week
"""

import numpy as np
import pandas as pd

from indicators.engine import _rsi, _ema, _macd, _supertrend, _bbands

_ATR_PERIOD = 14
_BB_PERIOD  = 20


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = _ATR_PERIOD) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build the full feature matrix from an OHLCV DataFrame.

    Parameters
    ----------
    df : DataFrame with columns o, h, l, c, v and a timezone-aware DatetimeIndex.

    Returns
    -------
    DataFrame of features aligned to df's index (rows with NaN dropped).
    No look-ahead: all indicators use only past + current bar.
    """
    if df.empty or len(df) < 40:
        return pd.DataFrame()

    c, h, l, v = df["c"], df["h"], df["l"], df["v"]

    out = pd.DataFrame(index=df.index)

    # --- Returns ---
    for n in (1, 5, 15, 30):
        out[f"ret_{n}"] = c.pct_change(n)

    # --- RSI ---
    out["rsi"] = _rsi(c) / 100.0          # normalise to [0, 1]

    # --- MACD ---
    atr       = _atr(h, l, c)
    macd_line, macd_sig, macd_hist = _macd(c)
    # normalise by ATR so values are scale-invariant across symbols/times
    out["macd_line"] = macd_line / atr.replace(0, np.nan)
    out["macd_hist"] = macd_hist / atr.replace(0, np.nan)

    # crossover signal: +1 when line crosses above signal, -1 below, else 0
    cross = np.zeros(len(c), dtype=np.float32)
    prev_above = (macd_line.shift(1) > macd_sig.shift(1)).values
    curr_above = (macd_line > macd_sig).values
    cross[~prev_above & curr_above]  =  1.0   # bullish cross
    cross[ prev_above & ~curr_above] = -1.0   # bearish cross
    out["macd_cross"] = cross

    # --- SuperTrend ---
    _, st_dir = _supertrend(h, l, c)
    out["supertrend_dir"] = st_dir.astype(float)   # +1 / -1

    # --- Bollinger Bands ---
    bb_upper, bb_mid, bb_lower = _bbands(c)
    band_width = (bb_upper - bb_lower).replace(0, np.nan)
    out["bb_pos"]   = (c - bb_lower) / band_width
    out["bb_width"] = band_width / bb_mid.replace(0, np.nan)

    # --- ATR % (volatility) ---
    out["atr_pct"] = atr / c.replace(0, np.nan)

    # --- EMA cross ---
    ema9  = _ema(c, 9)
    ema21 = _ema(c, 21)
    out["ema_cross"] = np.sign(ema9 - ema21).astype(float)

    # --- Volume ratio ---
    vol_ma = v.rolling(20, min_periods=1).mean().replace(0, np.nan)
    out["vol_ratio"] = v / vol_ma

    # --- Time features (cyclical; only meaningful for intraday bars) ---
    is_intraday = _is_intraday(df)
    if is_intraday:
        minutes = df.index.hour * 60 + df.index.minute
        market_open_min  = 9 * 60 + 15    # 9:15 IST
        market_close_min = 15 * 60 + 30   # 15:30 IST
        span = market_close_min - market_open_min or 1
        frac = np.clip((minutes - market_open_min) / span, 0, 1)
        out["time_sin"] = np.sin(2 * np.pi * frac).astype(np.float32)
        out["time_cos"] = np.cos(2 * np.pi * frac).astype(np.float32)
    else:
        out["time_sin"] = 0.0
        out["time_cos"] = 0.0

    # --- Day-of-week (cyclical) ---
    dow = df.index.dayofweek.astype(float)
    out["dow_sin"] = np.sin(2 * np.pi * dow / 5).astype(np.float32)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 5).astype(np.float32)

    return out.replace([np.inf, -np.inf], np.nan).dropna()


def build_target(df: pd.DataFrame, horizon: int = 3) -> pd.Series:
    """
    Build binary target: 1 if close N bars ahead > current close, else 0.
    Used only during training — never during inference.

    The returned Series is aligned to df's index but has NaN for the last
    `horizon` rows (future not known).
    """
    future_c = df["c"].shift(-horizon)
    return (future_c > df["c"]).astype(float).where(future_c.notna())


def _is_intraday(df: pd.DataFrame) -> bool:
    """True if the DataFrame looks like sub-daily bars."""
    if len(df) < 2:
        return False
    delta = (df.index[1] - df.index[0]).total_seconds()
    return delta < 86_400
