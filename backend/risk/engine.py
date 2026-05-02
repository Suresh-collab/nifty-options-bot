"""
Phase 3 — Risk Management Engine (pure functions, no DB / IO dependencies).

All functions are stateless and unit-testable without a running server.
The routes layer is responsible for reading simulator state and calling
these helpers before allowing any paper-trade operation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class TradeAction(str, Enum):
    HOLD     = "HOLD"
    EXIT_SL  = "EXIT_SL"
    EXIT_TP  = "EXIT_TP"
    EXIT_TRAIL = "EXIT_TRAIL"


@dataclass
class RiskParams:
    entry_price:      float
    direction:        str    # "BUY_CE" or "BUY_PE"
    sl_pct:           float = 0.015   # 1.5 % fixed stop-loss
    tp_pct:           float = 0.03    # 3 % take-profit
    trailing_sl_pct:  float = 0.01    # 1 % trailing distance behind peak


@dataclass
class TrailState:
    """Mutable per-trade state that tracks the trailing stop level."""
    peak:       float          # highest (CE) / lowest (PE) price seen after entry
    current_sl: float          # current trailing stop price


# ---------------------------------------------------------------------------
# 3.1 — Per-trade SL / TP + trailing stop
# ---------------------------------------------------------------------------

def initial_trail_state(params: RiskParams) -> TrailState:
    """Compute initial SL / trail state right after entry."""
    e = params.entry_price
    if params.direction == "BUY_PE":
        return TrailState(peak=e, current_sl=e * (1 + params.trailing_sl_pct))
    return TrailState(peak=e, current_sl=e * (1 - params.trailing_sl_pct))


def check_sl_tp(
    params: RiskParams,
    current_price: float,
    trail: TrailState,
) -> tuple[TradeAction, TrailState]:
    """
    Given the latest market price, decide whether to hold, exit fixed SL/TP,
    or exit trailing stop.  Returns (action, updated_trail_state).

    BUY_CE logic (long call):
      - Fixed SL  : current < entry * (1 - sl_pct)
      - Fixed TP  : current > entry * (1 + tp_pct)
      - Trail ratchet : new peak when current > old peak;
                        new trail_sl = peak * (1 - trailing_sl_pct)
      - Trail exit    : current < current_sl

    BUY_PE logic (long put — profitable when underlying falls):
      - Fixed SL  : current > entry * (1 + sl_pct)
      - Fixed TP  : current < entry * (1 - tp_pct)
      - Trail ratchet : new peak (lowest) when current < old peak;
                        new trail_sl = peak * (1 + trailing_sl_pct)
      - Trail exit    : current > current_sl
    """
    e = params.entry_price

    if params.direction == "BUY_PE":
        # Fixed stops
        if current_price >= e * (1 + params.sl_pct):
            return TradeAction.EXIT_SL, trail
        if current_price <= e * (1 - params.tp_pct):
            return TradeAction.EXIT_TP, trail
        # Trailing: track the minimum price (new lows = profit)
        new_peak = min(trail.peak, current_price)
        new_sl   = new_peak * (1 + params.trailing_sl_pct)
        updated  = TrailState(peak=new_peak, current_sl=new_sl)
        if current_price >= updated.current_sl and current_price < e:
            return TradeAction.EXIT_TRAIL, updated
        return TradeAction.HOLD, updated

    # Default: BUY_CE
    if current_price <= e * (1 - params.sl_pct):
        return TradeAction.EXIT_SL, trail
    if current_price >= e * (1 + params.tp_pct):
        return TradeAction.EXIT_TP, trail
    # Trailing: track the maximum price (new highs = profit)
    new_peak = max(trail.peak, current_price)
    new_sl   = new_peak * (1 - params.trailing_sl_pct)
    updated  = TrailState(peak=new_peak, current_sl=new_sl)
    if current_price <= updated.current_sl and current_price > e:
        return TradeAction.EXIT_TRAIL, updated
    return TradeAction.HOLD, updated


def trailing_sl_exit_price(entry: float, direction: str, peak_price: float, trailing_sl_pct: float) -> float:
    """Compute the exact trailing stop-loss price given a peak price."""
    if direction == "BUY_PE":
        return peak_price * (1 + trailing_sl_pct)
    return peak_price * (1 - trailing_sl_pct)


# ---------------------------------------------------------------------------
# 3.2 — Daily loss / profit cutoff
# ---------------------------------------------------------------------------

def check_daily_cutoff(
    daily_pnl: float,
    capital: float,
    daily_loss_limit_pct: float = 0.02,
    daily_profit_target_pct: float = 0.05,
) -> tuple[bool, str]:
    """
    Returns (should_halt, reason).
    Halt when:
      - daily_pnl <= -(capital * daily_loss_limit_pct)   [loss limit hit]
      - daily_pnl >=  (capital * daily_profit_target_pct) [profit target hit]
    """
    loss_limit   = -(abs(capital * daily_loss_limit_pct))
    profit_limit =   abs(capital * daily_profit_target_pct)

    if daily_pnl <= loss_limit:
        return True, f"Daily loss limit hit: ₹{daily_pnl:.0f} ≤ ₹{loss_limit:.0f}"
    if daily_pnl >= profit_limit:
        return True, f"Daily profit target hit: ₹{daily_pnl:.0f} ≥ ₹{profit_limit:.0f}"
    return False, ""


# ---------------------------------------------------------------------------
# 3.3 — Position sizing
# ---------------------------------------------------------------------------

def size_position_fixed_units(units: int) -> int:
    """Fixed quantity — return as-is (clamped to ≥ 0)."""
    return max(0, units)


def size_position_fixed_inr(budget_inr: float, price_per_unit: float) -> int:
    """How many units can we buy with a fixed ₹ budget?"""
    if price_per_unit <= 0:
        return 0
    return int(budget_inr / price_per_unit)


def size_position_risk_pct(
    capital: float,
    risk_pct: float,
    sl_pts: float,
) -> int:
    """
    Risk-percentage sizing: risk at most (capital × risk_pct) on this trade.

    qty = floor((capital × risk_pct) / sl_pts)

    Example (TDD criterion 3.3):
      capital=100_000, risk_pct=0.02, sl_pts=5
      → qty = floor(100_000 × 0.02 / 5) = floor(400) = 400
    """
    if sl_pts <= 0:
        return 0
    return math.floor((capital * risk_pct) / sl_pts)


def size_position_kelly(
    capital: float,
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    fraction: float = 0.25,
) -> float:
    """
    Fractional Kelly criterion.
    Full Kelly: f = (win_rate/avg_loss) - ((1-win_rate)/avg_win)
    Returns the ₹ amount to risk (fraction of full Kelly to limit variance).
    Returns 0 when Kelly is negative (edge is negative — do not trade).
    """
    if avg_loss <= 0 or avg_win <= 0:
        return 0.0
    b = avg_win / avg_loss          # win/loss ratio
    p = win_rate
    q = 1.0 - win_rate
    kelly_f = p - (q / b)          # full Kelly fraction
    if kelly_f <= 0:
        return 0.0
    return capital * kelly_f * fraction


# ---------------------------------------------------------------------------
# 3.5 — Max open positions cap
# ---------------------------------------------------------------------------

def check_max_positions(open_count: int, max_allowed: int) -> tuple[bool, str]:
    """
    Returns (allowed, reason).
    Blocks when open_count >= max_allowed.
    """
    if open_count >= max_allowed:
        return False, f"Max open positions ({max_allowed}) reached; currently {open_count} open"
    return True, ""
