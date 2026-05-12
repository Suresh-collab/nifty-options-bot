"""
OI Buildup classifier for index option chains.

Compares two consecutive option-chain snapshots and classifies the dominant
flow regime over near-ATM strikes, producing a directional bias score.

Regimes (combination of spot move + which side of the chain is building/unwinding):

    PUT_WRITING               +2.0  Spot up, put writers aggressive  -> strong bullish
    CALL_SHORT_COVERING       +1.5  Spot up, call shorts exiting     -> bullish accelerant
    BULLISH_DRIFT             +0.5  Spot up, no clear OI bias
    CALL_WRITING_AGAINST_TREND -0.5 Spot up, but call writers active -> caution
    NEUTRAL                    0.0
    PUT_WRITING_AGAINST_TREND +0.5  Spot down, but put writers active-> potential floor
    BEARISH_DRIFT             -0.5  Spot down, no clear OI bias
    PUT_SHORT_COVERING        -1.5  Spot down, put shorts exiting    -> bearish accelerant
    CALL_WRITING              -2.0  Spot down, call writers aggressive -> strong bearish

Inputs
------
Two snapshots produced by data.options_chain.fetch_option_chain(). Each must
have a `strikes` list of dicts with: strike, ce_oi, pe_oi, ce_chg_oi, pe_chg_oi.

Important: this only works when the chain is REAL (chain["fallback"] != True).
The synthetic fallback chain has all-zero OI and will produce NEUTRAL.

Usage
-----
    from indicators.oi_flow import classify_oi_flow

    result = classify_oi_flow(prev_chain, current_chain, atm_window=5)
    # result["regime"], result["bias_score"], result["details"]
"""

from __future__ import annotations

from typing import TypedDict


class OIFlowResult(TypedDict):
    regime:        str
    bias_score:    float
    spot_change:   float
    ce_oi_change:  int
    pe_oi_change:  int
    atm_strike:    float
    strikes_used:  int
    is_reliable:   bool
    details:       str


def _near_atm_strikes(chain: dict, atm_window: int) -> list[dict]:
    """Return the `atm_window` strikes nearest to spot on either side of ATM."""
    spot = float(chain.get("spot", 0) or 0)
    strikes = chain.get("strikes", []) or []
    if not strikes or spot <= 0:
        return []
    sorted_by_dist = sorted(strikes, key=lambda s: abs(s["strike"] - spot))
    return sorted_by_dist[: max(1, atm_window * 2 + 1)]


def _is_reliable(chain: dict) -> bool:
    """Reject synthetic-fallback chains; they have all-zero OI."""
    if chain.get("fallback") is True:
        return False
    total = (chain.get("total_ce_oi") or 0) + (chain.get("total_pe_oi") or 0)
    return total > 0


def classify_oi_flow(
    prev_chain: dict,
    curr_chain: dict,
    atm_window: int = 5,
) -> OIFlowResult:
    """
    Classify the OI flow regime between two consecutive snapshots.

    Parameters
    ----------
    prev_chain  : earlier snapshot
    curr_chain  : current snapshot
    atm_window  : how many strikes on each side of ATM to aggregate (default 5)

    Returns
    -------
    OIFlowResult with regime + bias_score in [-2, +2].
    """
    if not _is_reliable(prev_chain) or not _is_reliable(curr_chain):
        return _empty_result(curr_chain, reason="unreliable chain (fallback or zero OI)")

    prev_spot = float(prev_chain.get("spot", 0) or 0)
    curr_spot = float(curr_chain.get("spot", 0) or 0)
    if prev_spot <= 0 or curr_spot <= 0:
        return _empty_result(curr_chain, reason="missing spot price")

    spot_change = curr_spot - prev_spot

    near = _near_atm_strikes(curr_chain, atm_window)
    if not near:
        return _empty_result(curr_chain, reason="no near-ATM strikes")

    ce_oi_change = sum(int(s.get("ce_chg_oi") or 0) for s in near)
    pe_oi_change = sum(int(s.get("pe_chg_oi") or 0) for s in near)

    # Treat tiny OI moves as noise — threshold based on total OI of the strikes
    total_oi = sum(int(s.get("ce_oi") or 0) + int(s.get("pe_oi") or 0) for s in near)
    noise_floor = max(1_000, int(total_oi * 0.001))  # 0.1% of total or 1k contracts

    ce_dir = _sign(ce_oi_change, noise_floor)
    pe_dir = _sign(pe_oi_change, noise_floor)
    spot_dir = _sign(spot_change, 0.0)

    regime, bias_score = _classify(spot_dir, ce_dir, pe_dir, ce_oi_change, pe_oi_change)

    return {
        "regime":       regime,
        "bias_score":   bias_score,
        "spot_change":  round(spot_change, 2),
        "ce_oi_change": int(ce_oi_change),
        "pe_oi_change": int(pe_oi_change),
        "atm_strike":   float(near[0]["strike"]),
        "strikes_used": len(near),
        "is_reliable":  True,
        "details":      _explain(regime, ce_oi_change, pe_oi_change, spot_change),
    }


def _sign(x: float, threshold: float) -> int:
    if x > threshold:
        return 1
    if x < -threshold:
        return -1
    return 0


def _classify(
    spot_dir: int, ce_dir: int, pe_dir: int,
    ce_chg: int, pe_chg: int,
) -> tuple[str, float]:
    """
    Return (regime_name, bias_score).

    Reading guide for OI direction on each side of the chain:
      CE OI ↑  = call writers selling / new call longs (writers dominate at index level)
      CE OI ↓  = call writers covering / call longs exiting
      PE OI ↑  = put writers selling / new put longs
      PE OI ↓  = put writers covering / put longs exiting

    For an index, the dominant flow comes from WRITERS (selling premium), so:
      PE OI ↑ during spot ↑  ->  put writers confident in support  -> bullish
      CE OI ↑ during spot ↓  ->  call writers confident in resistance -> bearish
      CE OI ↓ during spot ↑  ->  call shorts covering -> bullish accelerant
      PE OI ↓ during spot ↓  ->  put shorts covering -> bearish accelerant
    """
    # Spot UP
    if spot_dir > 0:
        if pe_dir > 0 and pe_chg > abs(ce_chg):
            return "PUT_WRITING", +2.0
        if ce_dir < 0 and abs(ce_chg) > abs(pe_chg):
            return "CALL_SHORT_COVERING", +1.5
        if ce_dir > 0 and ce_chg > pe_chg:
            return "CALL_WRITING_AGAINST_TREND", -0.5
        return "BULLISH_DRIFT", +0.5

    # Spot DOWN
    if spot_dir < 0:
        if ce_dir > 0 and ce_chg > abs(pe_chg):
            return "CALL_WRITING", -2.0
        if pe_dir < 0 and abs(pe_chg) > abs(ce_chg):
            return "PUT_SHORT_COVERING", -1.5
        if pe_dir > 0 and pe_chg > ce_chg:
            return "PUT_WRITING_AGAINST_TREND", +0.5
        return "BEARISH_DRIFT", -0.5

    # Spot FLAT
    if pe_dir > 0 and pe_chg > abs(ce_chg):
        return "PUT_WRITING", +1.0
    if ce_dir > 0 and ce_chg > abs(pe_chg):
        return "CALL_WRITING", -1.0
    return "NEUTRAL", 0.0


def _explain(regime: str, ce_chg: int, pe_chg: int, spot_chg: float) -> str:
    direction = "+" if spot_chg > 0 else "-" if spot_chg < 0 else "flat"
    return (
        f"{regime}: spot {direction}{abs(spot_chg):.2f}, "
        f"CE OI Δ={ce_chg:+,}, PE OI Δ={pe_chg:+,}"
    )


def _empty_result(chain: dict, reason: str) -> OIFlowResult:
    return {
        "regime":       "NEUTRAL",
        "bias_score":   0.0,
        "spot_change":  0.0,
        "ce_oi_change": 0,
        "pe_oi_change": 0,
        "atm_strike":   float(chain.get("spot", 0) or 0),
        "strikes_used": 0,
        "is_reliable":  False,
        "details":      f"insufficient data: {reason}",
    }
