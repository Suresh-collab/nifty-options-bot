import pandas as pd
import numpy as np


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _supertrend(high: pd.Series, low: pd.Series, close: pd.Series,
                length: int = 7, multiplier: float = 3.0):
    hl2 = (high + low) / 2
    # ATR
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=length).mean()

    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend = pd.Series(np.nan, index=close.index)
    direction = pd.Series(1, index=close.index)

    for i in range(length, len(close)):
        if close.iloc[i] > upper_band.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < lower_band.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
            if direction.iloc[i] == 1 and lower_band.iloc[i] < lower_band.iloc[i - 1]:
                lower_band.iloc[i] = lower_band.iloc[i - 1]
            if direction.iloc[i] == -1 and upper_band.iloc[i] > upper_band.iloc[i - 1]:
                upper_band.iloc[i] = upper_band.iloc[i - 1]

        supertrend.iloc[i] = lower_band.iloc[i] if direction.iloc[i] == 1 else upper_band.iloc[i]

    return supertrend, direction


def _bbands(close: pd.Series, length: int = 20, std: float = 2.0):
    mid = close.rolling(window=length).mean()
    std_dev = close.rolling(window=length).std()
    upper = mid + std * std_dev
    lower = mid - std * std_dev
    return upper, mid, lower


def compute_indicators(df: pd.DataFrame, pcr: float = 1.0, iv: float = 20.0) -> dict:
    """
    Compute all technical indicators from OHLCV DataFrame.
    Returns a structured dict with values, signals, and combined score.
    """
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # --- RSI ---
    rsi_series = _rsi(close, length=14)
    rsi_val = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0
    if rsi_val < 35:
        rsi_signal = "BUY"
    elif rsi_val > 65:
        rsi_signal = "SELL"
    else:
        rsi_signal = "NEUTRAL"

    # --- MACD ---
    macd_line, signal_line, _ = _macd(close, fast=12, slow=26, signal=9)
    if len(macd_line) >= 2:
        macd_val = float(macd_line.iloc[-1])
        signal_val = float(signal_line.iloc[-1])
        macd_prev = float(macd_line.iloc[-2])
        sig_prev = float(signal_line.iloc[-2])
        if macd_val > signal_val and macd_prev <= sig_prev:
            macd_signal = "BUY"
        elif macd_val < signal_val and macd_prev >= sig_prev:
            macd_signal = "SELL"
        elif macd_val > signal_val:
            macd_signal = "BULLISH"
        else:
            macd_signal = "BEARISH"
    else:
        macd_val, signal_val, macd_signal = 0, 0, "NEUTRAL"

    # --- SuperTrend ---
    _, st_direction = _supertrend(high, low, close, length=7, multiplier=3)
    st_dir = int(st_direction.iloc[-1])
    supertrend_signal = "BUY" if st_dir == 1 else "SELL"

    # --- Bollinger Bands ---
    bb_upper_s, bb_mid_s, bb_lower_s = _bbands(close, length=20, std=2)
    bb_upper = float(bb_upper_s.iloc[-1])
    bb_lower = float(bb_lower_s.iloc[-1])
    bb_mid = float(bb_mid_s.iloc[-1])
    bb_width = (bb_upper - bb_lower) / bb_mid if bb_mid != 0 else 0
    last_close = float(close.iloc[-1])
    if last_close > bb_upper:
        bb_signal = "OVERBOUGHT"
    elif last_close < bb_lower:
        bb_signal = "OVERSOLD"
    elif bb_width < 0.02:
        bb_signal = "SQUEEZE"
    else:
        bb_signal = "NEUTRAL"

    # --- PCR Sentiment ---
    if pcr > 1.2:
        pcr_signal = "BULLISH"
    elif pcr < 0.8:
        pcr_signal = "BEARISH"
    else:
        pcr_signal = "NEUTRAL"

    # --- Combined Score (-100 to +100) ---
    def to_score(signal, weight):
        mapping = {
            "BUY": 1, "BULLISH": 0.7, "OVERSOLD": 0.5,
            "SELL": -1, "BEARISH": -0.7, "OVERBOUGHT": -0.5,
            "NEUTRAL": 0, "SQUEEZE": 0,
        }
        return mapping.get(signal, 0) * weight * 100

    score = (
        to_score(supertrend_signal, 0.40) +
        to_score(macd_signal, 0.25) +
        to_score(rsi_signal, 0.20) +
        to_score(pcr_signal, 0.15)
    )
    score = round(max(-100, min(100, score)), 1)

    abs_score = abs(score)
    if abs_score >= 70:
        confidence = "High"
    elif abs_score >= 40:
        confidence = "Medium"
    else:
        confidence = "Low"

    return {
        "rsi": {"value": round(rsi_val, 1), "signal": rsi_signal},
        "macd": {"value": round(macd_val, 2), "signal": macd_signal},
        "supertrend": {"signal": supertrend_signal},
        "bollinger": {
            "upper": round(bb_upper, 2),
            "lower": round(bb_lower, 2),
            "width": round(bb_width, 4),
            "signal": bb_signal,
        },
        "pcr": {"value": pcr, "signal": pcr_signal},
        "iv": {"value": iv},
        "combined_score": score,
        "confidence": confidence,
    }
