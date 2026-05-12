"""
RSI / price divergence detection.

Divergence types
----------------
REGULAR bullish:  price makes lower low,  RSI makes higher low  -> reversal up
REGULAR bearish:  price makes higher high, RSI makes lower high  -> reversal down
HIDDEN  bullish:  price makes higher low,  RSI makes lower low   -> continuation up
HIDDEN  bearish:  price makes lower high,  RSI makes higher high -> continuation down

Pivot detection
---------------
A bar at index i is a pivot HIGH if its value is the maximum of bars
[i - lookback, i + lookback] (a symmetric 2*lookback+1 window). This means
a pivot is only *confirmed* `lookback` bars after it occurs. Signals are
emitted at the confirmation bar (i + lookback) so there is no look-ahead.

Usage
-----
    from indicators.divergence import detect_divergence, _rsi
    signal_arr, meta = detect_divergence(close_series)
    # signal_arr[i]: +1 bullish, -1 bearish, 0 none
"""

from __future__ import annotations

from typing import Literal, TypedDict

import numpy as np
import pandas as pd

from indicators.engine import _rsi


class DivergenceEvent(TypedDict):
    confirm_idx: int          # bar index where divergence is confirmed (tradable)
    pivot_idx: int            # bar index of the actual pivot
    prior_pivot_idx: int      # bar index of the prior matching pivot
    kind: Literal["regular_bullish", "regular_bearish",
                  "hidden_bullish",  "hidden_bearish"]
    price_at_pivot: float
    price_at_prior: float
    rsi_at_pivot: float
    rsi_at_prior: float


def find_pivots(series: pd.Series, lookback: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """
    Find pivot highs and lows using a symmetric `lookback`-bar window.

    Returns
    -------
    (pivot_high_idx, pivot_low_idx) : two ndarrays of integer indices into `series`.
    """
    values = np.asarray(series.values, dtype=float)
    n = len(values)
    if n < 2 * lookback + 1:
        return np.array([], dtype=int), np.array([], dtype=int)

    highs: list[int] = []
    lows: list[int] = []

    for i in range(lookback, n - lookback):
        window = values[i - lookback: i + lookback + 1]
        center = values[i]
        if np.isnan(center) or np.any(np.isnan(window)):
            continue
        if center == window.max() and (window == center).sum() == 1:
            highs.append(i)
        elif center == window.min() and (window == center).sum() == 1:
            lows.append(i)

    return np.array(highs, dtype=int), np.array(lows, dtype=int)


def detect_divergence(
    close: pd.Series,
    rsi: pd.Series | None = None,
    pivot_lookback: int = 5,
    max_lookback_bars: int = 60,
    rsi_length: int = 14,
    include_hidden: bool = False,
) -> tuple[np.ndarray, list[DivergenceEvent]]:
    """
    Scan a price series for RSI divergences.

    Parameters
    ----------
    close             : closing prices (pd.Series)
    rsi               : pre-computed RSI series; computed from `close` if None
    pivot_lookback    : bars on each side of a pivot used for confirmation
    max_lookback_bars : max distance (in bars) between two pivots for divergence to count
    rsi_length        : RSI window when computing RSI inline
    include_hidden    : also report hidden (trend-continuation) divergences

    Returns
    -------
    signal_arr : int8 ndarray of length len(close);
                 +1 at the confirmation bar of a bullish divergence,
                 -1 at the confirmation bar of a bearish divergence,
                  0 otherwise.
    events     : list of DivergenceEvent dicts in chronological order.
    """
    if rsi is None:
        rsi = _rsi(close, length=rsi_length)

    n = len(close)
    signal_arr = np.zeros(n, dtype=np.int8)

    if n < 2 * pivot_lookback + 1:
        return signal_arr, []

    p_highs, p_lows = find_pivots(close, lookback=pivot_lookback)
    r_highs, r_lows = find_pivots(rsi.fillna(50.0), lookback=pivot_lookback)

    close_v = close.values
    rsi_v = rsi.values
    events: list[DivergenceEvent] = []

    # --- Bullish divergences: look at consecutive price LOWS ---
    for k in range(1, len(p_lows)):
        cur = p_lows[k]
        prev = p_lows[k - 1]
        if cur - prev > max_lookback_bars:
            continue

        # Find the RSI pivot low closest to each price pivot low (within +/- pivot_lookback bars)
        cur_r = _nearest_pivot(r_lows, cur, pivot_lookback)
        prev_r = _nearest_pivot(r_lows, prev, pivot_lookback)
        if cur_r is None or prev_r is None or cur_r == prev_r:
            continue

        confirm_idx = cur + pivot_lookback
        if confirm_idx >= n:
            continue

        price_lower_low = close_v[cur] < close_v[prev]
        rsi_higher_low = rsi_v[cur_r] > rsi_v[prev_r]

        kind: str | None = None
        if price_lower_low and rsi_higher_low:
            kind = "regular_bullish"
        elif include_hidden and (close_v[cur] > close_v[prev]) and (rsi_v[cur_r] < rsi_v[prev_r]):
            kind = "hidden_bullish"

        if kind:
            signal_arr[confirm_idx] = 1
            events.append({
                "confirm_idx":      int(confirm_idx),
                "pivot_idx":        int(cur),
                "prior_pivot_idx":  int(prev),
                "kind":             kind,           # type: ignore[typeddict-item]
                "price_at_pivot":   float(close_v[cur]),
                "price_at_prior":   float(close_v[prev]),
                "rsi_at_pivot":     float(rsi_v[cur_r]),
                "rsi_at_prior":     float(rsi_v[prev_r]),
            })

    # --- Bearish divergences: look at consecutive price HIGHS ---
    for k in range(1, len(p_highs)):
        cur = p_highs[k]
        prev = p_highs[k - 1]
        if cur - prev > max_lookback_bars:
            continue

        cur_r = _nearest_pivot(r_highs, cur, pivot_lookback)
        prev_r = _nearest_pivot(r_highs, prev, pivot_lookback)
        if cur_r is None or prev_r is None or cur_r == prev_r:
            continue

        confirm_idx = cur + pivot_lookback
        if confirm_idx >= n:
            continue

        price_higher_high = close_v[cur] > close_v[prev]
        rsi_lower_high = rsi_v[cur_r] < rsi_v[prev_r]

        kind = None
        if price_higher_high and rsi_lower_high:
            kind = "regular_bearish"
        elif include_hidden and (close_v[cur] < close_v[prev]) and (rsi_v[cur_r] > rsi_v[prev_r]):
            kind = "hidden_bearish"

        if kind:
            # If a bullish signal was already set on this bar (rare overlap), keep the
            # first one — divergence events on the same bar are unreliable.
            if signal_arr[confirm_idx] == 0:
                signal_arr[confirm_idx] = -1
            events.append({
                "confirm_idx":      int(confirm_idx),
                "pivot_idx":        int(cur),
                "prior_pivot_idx":  int(prev),
                "kind":             kind,           # type: ignore[typeddict-item]
                "price_at_pivot":   float(close_v[cur]),
                "price_at_prior":   float(close_v[prev]),
                "rsi_at_pivot":     float(rsi_v[cur_r]),
                "rsi_at_prior":     float(rsi_v[prev_r]),
            })

    events.sort(key=lambda e: e["confirm_idx"])
    return signal_arr, events


def _nearest_pivot(pivot_idx: np.ndarray, target: int, tol: int) -> int | None:
    """Return the pivot index closest to `target` within +/- tol bars, or None."""
    if len(pivot_idx) == 0:
        return None
    diffs = np.abs(pivot_idx - target)
    j = int(diffs.argmin())
    if diffs[j] <= tol:
        return int(pivot_idx[j])
    return None
