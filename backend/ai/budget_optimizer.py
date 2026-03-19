import math

LOT_SIZES = {"NIFTY": 25, "SENSEX": 20}

def optimize(budget: float, ticker: str, signal: dict, chain: dict) -> dict:
    """
    Given a budget (INR) and a trade signal, find the best strike and lot count.
    Returns a full trade plan with risk/reward breakdown.
    """
    lot_size    = LOT_SIZES.get(ticker.upper(), 25)
    direction   = signal.get("direction", "AVOID")
    best_strike = signal.get("best_strike", 0)
    spot        = signal.get("spot", 0)

    if direction == "AVOID":
        return {
            "recommendation": "AVOID",
            "reason": "Signal confidence too low. No trade recommended.",
        }

    strikes = chain.get("strikes", [])
    if not strikes:
        return {"recommendation": "AVOID", "reason": "No option chain data."}

    # Determine which side (CE or PE) and gather candidate strikes
    ltp_key = "ce_ltp" if direction == "BUY_CE" else "pe_ltp"
    strike_key = "strike"

    # Filter strikes around ±500 of best_strike (for Nifty) or ±1000 (Sensex)
    band = 500 if ticker.upper() == "NIFTY" else 1000
    candidates = [
        s for s in strikes
        if abs(s[strike_key] - best_strike) <= band and s[ltp_key] > 0
    ]
    if not candidates:
        candidates = [s for s in strikes if s[ltp_key] > 0]

    results = []
    for s in candidates:
        ltp = s[ltp_key]
        if ltp <= 0:
            continue
        lots       = math.floor(budget / (ltp * lot_size))
        if lots < 1:
            continue
        total_cost = lots * ltp * lot_size
        risk_pct   = total_cost / budget * 100

        # Target and SL based on signal
        target_ltp = ltp * 1.5   # 50% gain target
        sl_ltp     = ltp * 0.5   # 50% loss stop
        target_pnl = (target_ltp - ltp) * lots * lot_size
        max_loss   = total_cost   # max loss = premium paid

        results.append({
            "strike":      s[strike_key],
            "ltp":         round(ltp, 2),
            "lots":        lots,
            "total_cost":  round(total_cost, 2),
            "max_loss":    round(max_loss, 2),
            "target_pnl":  round(target_pnl, 2),
            "risk_pct":    round(risk_pct, 1),
            "target_ltp":  round(target_ltp, 2),
            "sl_ltp":      round(sl_ltp, 2),
        })

    if not results:
        return {"recommendation": "AVOID", "reason": "Budget too low for any lot."}

    # Best = closest to recommended strike, risk_pct <= 50%
    affordable = [r for r in results if r["risk_pct"] <= 50]
    pool = affordable if affordable else results

    best = min(pool, key=lambda x: abs(x["strike"] - best_strike))

    # Build alternatives list (other viable strikes, excluding the best)
    alternatives = [
        r for r in pool
        if r["strike"] != best["strike"]
    ]
    # Sort alternatives by distance from best strike
    alternatives.sort(key=lambda x: abs(x["strike"] - best_strike))
    alternatives = alternatives[:3]  # Top 3 alternatives

    return {
        "recommendation":  "TRADE",
        "direction":       direction,
        "ticker":          ticker,
        "strike":          best["strike"],
        "ltp":             best["ltp"],
        "lots":            best["lots"],
        "lot_size":        lot_size,
        "total_cost":      best["total_cost"],
        "max_loss":        best["max_loss"],
        "target_pnl":      best["target_pnl"],
        "risk_pct":        best["risk_pct"],
        "target_ltp":      best["target_ltp"],
        "sl_ltp":          best["sl_ltp"],
        "expiry":          signal.get("expiry", ""),
        "budget_used":     best["total_cost"],
        "budget_remaining": round(budget - best["total_cost"], 2),
        "alternatives":    alternatives,
    }
