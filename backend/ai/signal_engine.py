import math


def generate_signal(ticker: str, spot: float, expiry: str,
                    indicators: dict, chain: dict) -> dict:
    """
    Rule-based signal generator using technical indicators.
    No external API calls needed.
    """
    score      = indicators["combined_score"]
    confidence = indicators["confidence"]
    rsi        = indicators["rsi"]
    macd       = indicators["macd"]
    supertrend = indicators["supertrend"]
    bollinger  = indicators["bollinger"]
    pcr        = indicators["pcr"]
    iv         = indicators["iv"]["value"]
    max_pain   = chain.get("max_pain", spot)

    # --- Direction ---
    if confidence == "Low" or abs(score) < 20:
        direction = "AVOID"
    elif score > 0:
        direction = "BUY_CE"
    else:
        direction = "BUY_PE"

    # --- Best strike (round to nearest 50 for NIFTY, 100 for SENSEX) ---
    step = 50 if ticker == "NIFTY" else 100
    if direction == "BUY_CE":
        # ATM or slightly OTM call
        best_strike = math.ceil(spot / step) * step
        strike_type = "ATM" if abs(best_strike - spot) < step else "OTM_1"
    elif direction == "BUY_PE":
        # ATM or slightly OTM put
        best_strike = math.floor(spot / step) * step
        strike_type = "ATM" if abs(best_strike - spot) < step else "OTM_1"
    else:
        best_strike = round(spot / step) * step
        strike_type = "ATM"

    # --- Entry zone (±0.3% of spot) ---
    entry_low  = round(spot * 0.997, 2)
    entry_high = round(spot * 1.003, 2)

    # --- Target and stop loss based on direction and IV ---
    iv_factor = max(0.5, min(2.0, iv / 20))  # scale by IV
    if direction == "BUY_CE":
        target    = round(spot * (1 + 0.01 * iv_factor), 2)
        stop_loss = round(spot * (1 - 0.005 * iv_factor), 2)
    elif direction == "BUY_PE":
        target    = round(spot * (1 - 0.01 * iv_factor), 2)
        stop_loss = round(spot * (1 + 0.005 * iv_factor), 2)
    else:
        target    = round(spot, 2)
        stop_loss = round(spot, 2)

    # --- Risk/reward ---
    risk   = abs(spot - stop_loss) if direction != "AVOID" else 1
    reward = abs(target - spot) if direction != "AVOID" else 0
    risk_reward = round(reward / risk, 1) if risk > 0 else 0

    # --- Reasoning ---
    reasons = []
    if supertrend["signal"] in ("BUY", "SELL"):
        reasons.append(f"SuperTrend is {supertrend['signal']}")
    if macd["signal"] in ("BUY", "SELL", "BULLISH", "BEARISH"):
        reasons.append(f"MACD is {macd['signal']}")
    if rsi["signal"] in ("BUY", "SELL"):
        reasons.append(f"RSI at {rsi['value']} signals {rsi['signal']}")
    if pcr["signal"] != "NEUTRAL":
        reasons.append(f"PCR ({pcr['value']}) is {pcr['signal']}")
    if bollinger["signal"] not in ("NEUTRAL",):
        reasons.append(f"Bollinger shows {bollinger['signal']}")

    if not reasons:
        reasoning = "Mixed signals across indicators — no clear edge."
    else:
        reasoning = ". ".join(reasons[:3]) + "."

    return {
        "direction":    direction,
        "confidence":   confidence,
        "entry_zone":   [entry_low, entry_high],
        "target":       target,
        "stop_loss":    stop_loss,
        "reasoning":    reasoning,
        "best_strike":  best_strike,
        "strike_type":  strike_type,
        "expiry":       expiry,
        "risk_reward":  risk_reward,
        "spot":         spot,
        "ticker":       ticker,
    }
