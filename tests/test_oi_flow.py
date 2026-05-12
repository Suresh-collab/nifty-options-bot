"""
Tests for indicators.oi_flow — OI Buildup regime classifier.

Test cases:
  TC-1  Fallback / synthetic chains return NEUTRAL with is_reliable=False
  TC-2  Missing spot price returns NEUTRAL
  TC-3  Spot ↑ + PE OI ↑ dominant  ->  PUT_WRITING (strongly bullish, +2.0)
  TC-4  Spot ↑ + CE OI ↓ dominant  ->  CALL_SHORT_COVERING (+1.5)
  TC-5  Spot ↓ + CE OI ↑ dominant  ->  CALL_WRITING (strongly bearish, -2.0)
  TC-6  Spot ↓ + PE OI ↓ dominant  ->  PUT_SHORT_COVERING (-1.5)
  TC-7  Spot ↑ + CE OI ↑ dominant  ->  CALL_WRITING_AGAINST_TREND (-0.5)
  TC-8  Tiny OI changes below noise floor produce drift, not strong regime
  TC-9  atm_window picks only the closest strikes around spot
"""

from indicators.oi_flow import classify_oi_flow, _near_atm_strikes


def _make_strike(strike: int, ce_oi: int, pe_oi: int,
                 ce_chg: int = 0, pe_chg: int = 0) -> dict:
    return {
        "strike":    strike,
        "ce_oi":     ce_oi,
        "ce_iv":     15.0,
        "ce_ltp":    0.0,
        "ce_chg_oi": ce_chg,
        "pe_oi":     pe_oi,
        "pe_iv":     15.0,
        "pe_ltp":    0.0,
        "pe_chg_oi": pe_chg,
    }


def _make_chain(spot: float, strikes: list[dict],
                fallback: bool = False) -> dict:
    return {
        "ticker":      "NIFTY",
        "spot":        spot,
        "expiry":      "16-May-2026",
        "pcr":         1.0,
        "max_pain":    int(spot),
        "total_ce_oi": sum(s["ce_oi"] for s in strikes),
        "total_pe_oi": sum(s["pe_oi"] for s in strikes),
        "strikes":     strikes,
        "fallback":    fallback,
    }


def _atm_grid(spot: float, ce_oi: int = 1_000_000, pe_oi: int = 1_000_000,
              ce_chg: int = 0, pe_chg: int = 0) -> list[dict]:
    """11 strikes centered on round(spot/50)*50."""
    atm = int(round(spot / 50) * 50)
    out = []
    for i in range(-5, 6):
        s = atm + i * 50
        out.append(_make_strike(s, ce_oi, pe_oi, ce_chg, pe_chg))
    return out


# ── TC-1: synthetic chain ─────────────────────────────────────────────────
def test_tc1_fallback_chain_returns_neutral():
    prev = _make_chain(23500, _atm_grid(23500), fallback=True)
    curr = _make_chain(23520, _atm_grid(23520), fallback=True)
    res = classify_oi_flow(prev, curr)
    assert res["regime"] == "NEUTRAL"
    assert res["is_reliable"] is False


# ── TC-2: missing spot ────────────────────────────────────────────────────
def test_tc2_missing_spot_returns_neutral():
    prev = _make_chain(0, _atm_grid(23500))
    curr = _make_chain(23520, _atm_grid(23520))
    res = classify_oi_flow(prev, curr)
    assert res["regime"] == "NEUTRAL"


# ── TC-3: PUT_WRITING (strong bullish) ────────────────────────────────────
def test_tc3_put_writing_strong_bullish():
    prev = _make_chain(23500, _atm_grid(23500))
    # spot up 30 pts, PE OI strongly up (+500k), CE OI barely moves (+5k)
    curr = _make_chain(23530, _atm_grid(23530, ce_chg=5_000, pe_chg=500_000))
    res = classify_oi_flow(prev, curr)
    assert res["regime"] == "PUT_WRITING"
    assert res["bias_score"] == 2.0
    assert res["is_reliable"] is True


# ── TC-4: CALL_SHORT_COVERING (+1.5) ──────────────────────────────────────
def test_tc4_call_short_covering():
    prev = _make_chain(23500, _atm_grid(23500))
    # spot up, CE OI strongly DOWN (call shorts exiting), PE flat
    curr = _make_chain(23540, _atm_grid(23540, ce_chg=-400_000, pe_chg=5_000))
    res = classify_oi_flow(prev, curr)
    assert res["regime"] == "CALL_SHORT_COVERING"
    assert res["bias_score"] == 1.5


# ── TC-5: CALL_WRITING (strong bearish) ───────────────────────────────────
def test_tc5_call_writing_strong_bearish():
    prev = _make_chain(23500, _atm_grid(23500))
    # spot down, CE OI strongly UP (call writers selling), PE flat
    curr = _make_chain(23470, _atm_grid(23470, ce_chg=600_000, pe_chg=5_000))
    res = classify_oi_flow(prev, curr)
    assert res["regime"] == "CALL_WRITING"
    assert res["bias_score"] == -2.0


# ── TC-6: PUT_SHORT_COVERING (-1.5) ───────────────────────────────────────
def test_tc6_put_short_covering():
    prev = _make_chain(23500, _atm_grid(23500))
    # spot down, PE OI strongly DOWN (put shorts exiting), CE flat
    curr = _make_chain(23460, _atm_grid(23460, ce_chg=5_000, pe_chg=-400_000))
    res = classify_oi_flow(prev, curr)
    assert res["regime"] == "PUT_SHORT_COVERING"
    assert res["bias_score"] == -1.5


# ── TC-7: CALL_WRITING_AGAINST_TREND (-0.5) ───────────────────────────────
def test_tc7_call_writing_against_trend():
    prev = _make_chain(23500, _atm_grid(23500))
    # spot up, but CE OI rising more than PE OI -> resistance forming
    curr = _make_chain(23520, _atm_grid(23520, ce_chg=400_000, pe_chg=50_000))
    res = classify_oi_flow(prev, curr)
    assert res["regime"] == "CALL_WRITING_AGAINST_TREND"
    assert res["bias_score"] == -0.5


# ── TC-8: noise floor ─────────────────────────────────────────────────────
def test_tc8_tiny_changes_yield_drift():
    """OI changes below the noise floor should NOT trigger strong regimes."""
    prev = _make_chain(23500, _atm_grid(23500, ce_oi=1_000_000, pe_oi=1_000_000))
    # Total OI of near-ATM = ~22M; noise floor = 0.1% = ~22k. Use 500 each.
    curr = _make_chain(23510, _atm_grid(23510, ce_oi=1_000_000, pe_oi=1_000_000,
                                        ce_chg=500, pe_chg=500))
    res = classify_oi_flow(prev, curr)
    assert res["regime"] in ("BULLISH_DRIFT", "NEUTRAL")
    assert abs(res["bias_score"]) <= 0.5


# ── TC-9: atm_window selects closest strikes ──────────────────────────────
def test_tc9_atm_window_truncates():
    spot = 23500
    strikes = _atm_grid(spot)
    chain = _make_chain(spot, strikes)

    near3 = _near_atm_strikes(chain, atm_window=3)
    assert len(near3) == 7        # 3 below + ATM + 3 above

    near1 = _near_atm_strikes(chain, atm_window=1)
    assert len(near1) == 3        # ATM ± 1
