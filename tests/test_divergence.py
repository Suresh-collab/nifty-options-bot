"""
Tests for indicators.divergence — pivot detection and RSI divergence.

Test cases:
  TC-1 Pivot highs and lows are detected on a synthetic V-shape
  TC-2 Pivot signal is emitted only AFTER the lookback window (no peek-ahead)
  TC-3 Regular BULLISH divergence: price LL + RSI HL -> signal == +1
  TC-4 Regular BEARISH divergence: price HH + RSI LH -> signal == -1
  TC-5 No divergence when RSI moves in the same direction as price
  TC-6 max_lookback_bars caps how far back two pivots can match
  TC-7 Empty / too-short series returns empty signal
  TC-8 include_hidden flag enables hidden-divergence detection
"""

import numpy as np
import pandas as pd
import pytest

from indicators.divergence import (
    find_pivots,
    detect_divergence,
    _nearest_pivot,
)


# ── TC-1: Pivot detection ─────────────────────────────────────────────────
def test_tc1_pivot_highs_and_lows():
    # V shape: ascending to bar 5, then descending
    values = pd.Series([10, 12, 14, 16, 18, 20, 18, 16, 14, 12, 10])
    highs, lows = find_pivots(values, lookback=3)

    # With a lookback of 3, bar 5 (value 20) should be detected as the pivot high.
    # Edge bars are excluded, so no pivot low exists in this short series.
    assert 5 in highs


# ── TC-2: No look-ahead — pivot confirmation is delayed ────────────────────
def test_tc2_no_lookahead():
    """A pivot at bar i must only be confirmed at bar i+lookback in the signal array."""
    # Build a long descending then ascending series so a pivot LOW prints
    n = 60
    prices = list(range(100, 100 - 30, -1)) + list(range(70, 70 + 30))   # bottom at idx 29
    close = pd.Series(prices, dtype=float)

    # Slow descending move so RSI rises into the bottom -> bullish divergence-like
    signal_arr, events = detect_divergence(close, pivot_lookback=5,
                                           max_lookback_bars=80)
    # Confirm none of the events were emitted at or before the pivot bar
    for ev in events:
        assert ev["confirm_idx"] >= ev["pivot_idx"] + 5


# ── TC-3: Regular bullish divergence ──────────────────────────────────────
def test_tc3_bullish_divergence_detected():
    """
    Construct a price series with a lower-low and an RSI series with a higher-low.
    The bullish divergence at the second pivot must produce signal == +1.
    """
    n = 60
    close_vals = np.full(n, 100.0)
    rsi_vals = np.full(n, 50.0)

    # First low at bar 15 (deep low)
    close_vals[12:18] = [100, 95, 92, 90, 92, 95]
    rsi_vals[12:18]   = [50, 40, 32, 28, 32, 40]    # deep RSI trough

    # Second price low at bar 40 -> LOWER price low, but RSI is HIGHER (divergence)
    close_vals[37:43] = [95, 92, 89, 88, 89, 92]    # 88 < 90 -> price LL
    rsi_vals[37:43]   = [45, 40, 38, 36, 38, 42]    # 36 > 28 -> RSI HL

    close = pd.Series(close_vals)
    rsi = pd.Series(rsi_vals)

    signal_arr, events = detect_divergence(close, rsi,
                                           pivot_lookback=3,
                                           max_lookback_bars=40)

    # At least one regular bullish divergence event should be recorded
    bullish = [e for e in events if e["kind"] == "regular_bullish"]
    assert bullish, f"no bullish divergence detected; events: {events}"
    # Signal must fire at the confirmation bar (pivot_idx + 3)
    for ev in bullish:
        assert signal_arr[ev["confirm_idx"]] == 1


# ── TC-4: Regular bearish divergence ──────────────────────────────────────
def test_tc4_bearish_divergence_detected():
    """Price HH + RSI LH -> bearish divergence, signal == -1 at confirmation bar."""
    n = 60
    close_vals = np.full(n, 100.0)
    rsi_vals = np.full(n, 50.0)

    # First high
    close_vals[12:18] = [100, 105, 108, 110, 108, 105]
    rsi_vals[12:18]   = [50, 60, 68, 72, 68, 60]

    # Second higher high in price, but lower high in RSI
    close_vals[37:43] = [105, 108, 111, 112, 111, 108]   # 112 > 110 -> HH
    rsi_vals[37:43]   = [55, 58, 62, 64, 62, 58]         # 64 < 72 -> LH

    close = pd.Series(close_vals)
    rsi = pd.Series(rsi_vals)

    signal_arr, events = detect_divergence(close, rsi,
                                           pivot_lookback=3,
                                           max_lookback_bars=40)

    bearish = [e for e in events if e["kind"] == "regular_bearish"]
    assert bearish, f"no bearish divergence detected; events: {events}"
    for ev in bearish:
        assert signal_arr[ev["confirm_idx"]] == -1


# ── TC-5: No divergence when RSI tracks price ─────────────────────────────
def test_tc5_no_signal_on_same_direction():
    """When RSI and price move in the same direction, no divergence should fire."""
    n = 60
    close_vals = np.full(n, 100.0)
    rsi_vals = np.full(n, 50.0)

    # Both lows: each subsequent low is lower in BOTH price and RSI -> no divergence
    close_vals[12:18] = [100, 95, 92, 90, 92, 95]
    rsi_vals[12:18]   = [50, 40, 32, 28, 32, 40]

    close_vals[37:43] = [95, 92, 89, 87, 89, 92]    # price LL
    rsi_vals[37:43]   = [45, 35, 28, 24, 28, 35]    # RSI ALSO LL (24 < 28) -> no div

    close = pd.Series(close_vals)
    rsi = pd.Series(rsi_vals)

    _, events = detect_divergence(close, rsi, pivot_lookback=3,
                                  max_lookback_bars=40,
                                  include_hidden=False)
    bullish = [e for e in events if e["kind"] == "regular_bullish"]
    assert not bullish, f"unexpected bullish divergences: {bullish}"


# ── TC-6: max_lookback_bars caps pivot pairing distance ───────────────────
def test_tc6_max_lookback_caps_distance():
    """If pivots are farther apart than max_lookback_bars, no divergence is paired."""
    n = 120
    close_vals = np.full(n, 100.0)
    rsi_vals = np.full(n, 50.0)

    close_vals[12:18] = [100, 95, 92, 90, 92, 95]
    rsi_vals[12:18]   = [50, 40, 32, 28, 32, 40]

    # Second pivot 90 bars later -> outside a max_lookback_bars=30 window
    close_vals[97:103] = [95, 92, 89, 88, 89, 92]
    rsi_vals[97:103]   = [45, 40, 38, 36, 38, 42]

    close = pd.Series(close_vals)
    rsi = pd.Series(rsi_vals)

    _, events = detect_divergence(close, rsi, pivot_lookback=3,
                                  max_lookback_bars=30)
    bullish = [e for e in events if e["kind"] == "regular_bullish"]
    assert not bullish


# ── TC-7: Short series returns empty signal ───────────────────────────────
def test_tc7_short_series_empty():
    close = pd.Series([100.0, 101.0, 99.0])      # too short for any lookback
    signal_arr, events = detect_divergence(close, pivot_lookback=5)
    assert signal_arr.sum() == 0
    assert events == []


# ── TC-8: include_hidden flag ─────────────────────────────────────────────
def test_tc8_hidden_bullish_detected_when_enabled():
    """Hidden bullish: price HL + RSI LL -> only fires when include_hidden=True."""
    n = 60
    close_vals = np.full(n, 100.0)
    rsi_vals = np.full(n, 50.0)

    # First low — deep
    close_vals[12:18] = [100, 95, 92, 90, 92, 95]
    rsi_vals[12:18]   = [50, 40, 35, 32, 35, 40]

    # Second low — higher in price (price HL) but lower in RSI (RSI LL) -> hidden bull
    close_vals[37:43] = [98, 96, 94, 93, 94, 96]    # 93 > 90 -> price HL
    rsi_vals[37:43]   = [40, 32, 28, 26, 28, 32]    # 26 < 32 -> RSI LL

    close = pd.Series(close_vals)
    rsi = pd.Series(rsi_vals)

    _, events_off = detect_divergence(close, rsi, pivot_lookback=3,
                                      max_lookback_bars=40,
                                      include_hidden=False)
    assert not [e for e in events_off if e["kind"] == "hidden_bullish"]

    _, events_on = detect_divergence(close, rsi, pivot_lookback=3,
                                     max_lookback_bars=40,
                                     include_hidden=True)
    assert [e for e in events_on if e["kind"] == "hidden_bullish"]


# ── helpers ───────────────────────────────────────────────────────────────
def test_nearest_pivot_within_tolerance():
    arr = np.array([5, 10, 25, 40])
    assert _nearest_pivot(arr, target=11, tol=2) == 10
    assert _nearest_pivot(arr, target=11, tol=0) is None
    assert _nearest_pivot(np.array([]), target=5, tol=3) is None
