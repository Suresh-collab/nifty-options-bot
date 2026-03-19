import math


def generate_signal(ticker: str, spot: float, expiry: str,
                    indicators: dict, chain: dict) -> dict:
    """
    Rule-based signal generator using technical indicators.
    No external API calls needed.

    v2 improvements:
    - Uses confluence data to require stronger agreement before signaling
    - Better reasoning with plain-language explanations
    - Adds market condition context to reasoning
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
    confluence = indicators.get("confluence", {})
    vol_trend  = indicators.get("volume_trend", "NEUTRAL")

    # --- Direction (v2: use confluence for stronger filtering) ---
    confluence_count = confluence.get("count", 0)
    confluence_dir = confluence.get("direction", "NEUTRAL")
    strength = confluence.get("strength", "WEAK")

    if confidence == "Low" or abs(score) < 20:
        direction = "AVOID"
    elif strength == "WEAK" and abs(score) < 40:
        # v2: Even if score shows a direction, weak confluence = AVOID
        direction = "AVOID"
    elif score > 0:
        direction = "BUY_CE"
    else:
        direction = "BUY_PE"

    # v2: Cross-check confluence direction with score direction
    # If they disagree, downgrade to AVOID (conflicting signals = danger)
    if direction == "BUY_CE" and confluence_dir == "SELL" and confluence_count >= 3:
        direction = "AVOID"
    if direction == "BUY_PE" and confluence_dir == "BUY" and confluence_count >= 3:
        direction = "AVOID"

    # --- Best strike (round to nearest 50 for NIFTY, 100 for SENSEX) ---
    step = 50 if ticker == "NIFTY" else 100
    if direction == "BUY_CE":
        best_strike = math.ceil(spot / step) * step
        strike_type = "ATM" if abs(best_strike - spot) < step else "OTM_1"
    elif direction == "BUY_PE":
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

    # --- Reasoning (v2: more detailed, includes trend context) ---
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

    # v2: Add confluence and volume context
    if confluence_count >= 4:
        reasons.append(f"{confluence_count}/5 indicators agree ({strength} signal)")
    elif confluence_count <= 2:
        reasons.append(f"Only {confluence_count}/5 indicators agree (weak, risky)")

    if vol_trend == "HIGH":
        reasons.append("Volume is above average (confirms the move)")
    elif vol_trend == "LOW":
        reasons.append("Volume is low (move may lack conviction)")

    if not reasons:
        reasoning = "Mixed signals across indicators — no clear edge. Stay on the sidelines."
    else:
        reasoning = ". ".join(reasons[:4]) + "."

    # v2: Add plain-language market condition
    if direction == "AVOID":
        if abs(score) < 10:
            reasoning += " Market is undecided — wait for clarity."
        elif score < -20:
            reasoning += " Bearish pressure exists but not strong enough for a confident trade."
        elif score > 20:
            reasoning += " Mild bullish tilt but indicators don't agree enough to trade safely."

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
