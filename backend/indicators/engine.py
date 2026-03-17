import pandas as pd
import pandas_ta as ta
import numpy as np

def compute_indicators(df: pd.DataFrame, pcr: float = 1.0, iv: float = 20.0) -> dict:
    """
    Compute all technical indicators from OHLCV DataFrame.
    Returns a structured dict with values, signals, and combined score.
    """
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]

    # --- RSI ---
    rsi_series = ta.rsi(close, length=14)
    rsi_val = float(rsi_series.iloc[-1]) if rsi_series is not None else 50.0
    if rsi_val < 35:
        rsi_signal = "BUY"
    elif rsi_val > 65:
        rsi_signal = "SELL"
    else:
        rsi_signal = "NEUTRAL"

    # --- MACD ---
    macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    if macd_df is not None and len(macd_df) >= 2:
        macd_val   = float(macd_df["MACD_12_26_9"].iloc[-1])
        signal_val = float(macd_df["MACDs_12_26_9"].iloc[-1])
        macd_prev  = float(macd_df["MACD_12_26_9"].iloc[-2])
        sig_prev   = float(macd_df["MACDs_12_26_9"].iloc[-2])
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
    st_df = ta.supertrend(high, low, close, length=7, multiplier=3)
    if st_df is not None:
        st_dir_col = [c for c in st_df.columns if "SUPERTd" in c]
        if st_dir_col:
            st_dir = int(st_df[st_dir_col[0]].iloc[-1])
            supertrend_signal = "BUY" if st_dir == 1 else "SELL"
        else:
            supertrend_signal = "NEUTRAL"
    else:
        supertrend_signal = "NEUTRAL"

    # --- Bollinger Bands ---
    bb_df = ta.bbands(close, length=20, std=2)
    if bb_df is not None:
        # Find columns dynamically (names vary across pandas-ta versions)
        bb_upper_col = [c for c in bb_df.columns if c.startswith("BBU_")][0]
        bb_lower_col = [c for c in bb_df.columns if c.startswith("BBL_")][0]
        bb_mid_col   = [c for c in bb_df.columns if c.startswith("BBM_")][0]
        bb_upper = float(bb_df[bb_upper_col].iloc[-1])
        bb_lower = float(bb_df[bb_lower_col].iloc[-1])
        bb_mid   = float(bb_df[bb_mid_col].iloc[-1])
        bb_width = (bb_upper - bb_lower) / bb_mid
        last_close = float(close.iloc[-1])
        if last_close > bb_upper:
            bb_signal = "OVERBOUGHT"
        elif last_close < bb_lower:
            bb_signal = "OVERSOLD"
        elif bb_width < 0.02:
            bb_signal = "SQUEEZE"
        else:
            bb_signal = "NEUTRAL"
    else:
        bb_upper = bb_lower = bb_mid = bb_width = 0
        bb_signal = "NEUTRAL"

    # --- PCR Sentiment ---
    if pcr > 1.2:
        pcr_signal = "BULLISH"
    elif pcr < 0.8:
        pcr_signal = "BEARISH"
    else:
        pcr_signal = "NEUTRAL"

    # --- Combined Score (-100 to +100) ---
    # Weights: SuperTrend 40%, MACD 25%, RSI 20%, PCR 15%
    def to_score(signal, weight):
        mapping = {
            "BUY": 1, "BULLISH": 0.7, "OVERSOLD": 0.5,
            "SELL": -1, "BEARISH": -0.7, "OVERBOUGHT": -0.5,
            "NEUTRAL": 0, "SQUEEZE": 0,
        }
        return mapping.get(signal, 0) * weight * 100

    score = (
        to_score(supertrend_signal, 0.40) +
        to_score(macd_signal,       0.25) +
        to_score(rsi_signal,        0.20) +
        to_score(pcr_signal,        0.15)
    )
    score = round(max(-100, min(100, score)), 1)

    # --- Confidence Level ---
    abs_score = abs(score)
    if abs_score >= 70:
        confidence = "High"
    elif abs_score >= 40:
        confidence = "Medium"
    else:
        confidence = "Low"

    return {
        "rsi":        {"value": round(rsi_val, 1), "signal": rsi_signal},
        "macd":       {"value": round(macd_val, 2), "signal": macd_signal},
        "supertrend": {"signal": supertrend_signal},
        "bollinger":  {
            "upper": round(bb_upper, 2),
            "lower": round(bb_lower, 2),
            "width": round(bb_width, 4),
            "signal": bb_signal,
        },
        "pcr":        {"value": pcr, "signal": pcr_signal},
        "iv":         {"value": iv},
        "combined_score": score,
        "confidence": confidence,
    }
