"""
Phase 3 — Risk Management Engine tests.

Covers all 5 TDD criteria from MASTER_PLAN.md:
  3.1 Per-trade SL/TP + trailing stop — replay / exact exit level
  3.2 Daily cutoff — 3 losing trades hit limit → 4th blocked
  3.3 Position sizing — capital 1L, risk 2%, SL 5 pts → qty = 400
  3.4 Kill switch — POST /api/kill-switch halts all open trades; subsequent enter blocked
  3.5 Max positions — open N+1 → rejection with clear error
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

from main import app
from risk.engine import (
    RiskParams, TrailState,
    initial_trail_state, check_sl_tp, trailing_sl_exit_price,
    check_daily_cutoff,
    size_position_risk_pct, size_position_fixed_inr, size_position_kelly,
    check_max_positions,
    TradeAction,
)
import api.routes as routes_module


# ===========================================================================
# 3.1 — Per-trade SL / TP + trailing stop
# ===========================================================================

class TestSlTp:
    def _params(self, direction="BUY_CE", sl_pct=0.015, tp_pct=0.03, trail_pct=0.01):
        return RiskParams(entry_price=100.0, direction=direction,
                          sl_pct=sl_pct, tp_pct=tp_pct, trailing_sl_pct=trail_pct)

    def test_hold_while_price_in_range(self):
        p = self._params()
        trail = initial_trail_state(p)
        action, _ = check_sl_tp(p, 101.0, trail)
        assert action == TradeAction.HOLD

    def test_fixed_sl_triggers_below_threshold(self):
        p = self._params(sl_pct=0.015)  # SL at 100 * 0.985 = 98.5
        trail = initial_trail_state(p)
        action, _ = check_sl_tp(p, 98.4, trail)
        assert action == TradeAction.EXIT_SL

    def test_fixed_tp_triggers_above_threshold(self):
        p = self._params(tp_pct=0.03)  # TP at 100 * 1.03 = 103
        trail = initial_trail_state(p)
        action, _ = check_sl_tp(p, 103.5, trail)
        assert action == TradeAction.EXIT_TP

    def test_trailing_sl_ratchets_on_new_high(self):
        """Price up 2% → trail ratchets → exit at exact expected level (TDD 3.1)."""
        p = self._params(sl_pct=0.10, tp_pct=0.20, trail_pct=0.01)  # wide fixed stops
        trail = initial_trail_state(p)  # peak=100, trail_sl=99.0

        # Price moves up 2% — peak should ratchet
        action, trail = check_sl_tp(p, 102.0, trail)
        assert action == TradeAction.HOLD
        assert trail.peak == 102.0

        # Expected trail SL after peak of 102 with trail_pct=1%
        expected_sl = trailing_sl_exit_price(100.0, "BUY_CE", 102.0, 0.01)
        assert abs(trail.current_sl - expected_sl) < 1e-9  # 100.98

        # Price drops just below the trail SL → EXIT_TRAIL
        action, _ = check_sl_tp(p, expected_sl - 0.01, trail)
        assert action == TradeAction.EXIT_TRAIL

    def test_trailing_exit_price_formula(self):
        """trailing_sl_exit_price is deterministic and matches ratcheted state."""
        exit_price = trailing_sl_exit_price(100.0, "BUY_CE", peak_price=102.0, trailing_sl_pct=0.01)
        assert abs(exit_price - 100.98) < 1e-9

    def test_buy_pe_sl_triggers_on_price_rise(self):
        """For BUY_PE (put): SL triggers when price rises above entry."""
        p = self._params(direction="BUY_PE", sl_pct=0.015)
        trail = initial_trail_state(p)
        action, _ = check_sl_tp(p, 101.6, trail)   # > 100 * 1.015
        assert action == TradeAction.EXIT_SL

    def test_buy_pe_tp_triggers_on_price_fall(self):
        """For BUY_PE (put): TP triggers when price falls below entry."""
        p = self._params(direction="BUY_PE", tp_pct=0.03)
        trail = initial_trail_state(p)
        action, _ = check_sl_tp(p, 96.9, trail)    # < 100 * (1-0.03)
        assert action == TradeAction.EXIT_TP


# ===========================================================================
# 3.2 — Daily SL / TP cutoff
# ===========================================================================

class TestDailyCutoff:
    def test_no_cutoff_when_pnl_within_limits(self):
        halt, _ = check_daily_cutoff(500, 100_000, 0.02, 0.05)
        assert halt is False

    def test_daily_loss_limit_triggers(self):
        """Daily loss = -2000 on 100k capital (2%) → halt."""
        halt, reason = check_daily_cutoff(-2000, 100_000, 0.02, 0.05)
        assert halt is True
        assert "loss limit" in reason.lower()

    def test_daily_profit_target_triggers(self):
        """Daily profit = 5001 on 100k capital → halt (profit target 5%)."""
        halt, reason = check_daily_cutoff(5001, 100_000, 0.02, 0.05)
        assert halt is True
        assert "profit" in reason.lower()

    def test_boundary_exactly_at_loss_limit(self):
        """Exactly at the loss limit → halt."""
        halt, _ = check_daily_cutoff(-2000, 100_000, 0.02, 0.05)
        assert halt is True

    def test_just_inside_loss_limit(self):
        halt, _ = check_daily_cutoff(-1999, 100_000, 0.02, 0.05)
        assert halt is False


# ===========================================================================
# 3.3 — Position sizing
# ===========================================================================

class TestPositionSizing:
    def test_risk_pct_tdd_boundary(self):
        """TDD 3.3: capital=1L, risk 2%, SL 5 pts → qty = 400 exactly."""
        qty = size_position_risk_pct(capital=100_000, risk_pct=0.02, sl_pts=5)
        assert qty == 400

    def test_risk_pct_zero_sl_returns_zero(self):
        assert size_position_risk_pct(100_000, 0.02, 0) == 0

    def test_risk_pct_rounds_down(self):
        """Fractional units are floored (never over-risk)."""
        qty = size_position_risk_pct(100_000, 0.02, 7)
        assert qty == 285   # floor(2000/7)

    def test_fixed_inr_sizing(self):
        qty = size_position_fixed_inr(budget_inr=50_000, price_per_unit=250)
        assert qty == 200

    def test_fixed_inr_zero_price_returns_zero(self):
        assert size_position_fixed_inr(50_000, 0) == 0

    def test_kelly_positive_edge(self):
        """Positive edge → positive ₹ amount."""
        amount = size_position_kelly(100_000, win_rate=0.55, avg_win=200, avg_loss=100)
        assert amount > 0

    def test_kelly_negative_edge_returns_zero(self):
        """Win rate 30%, avg_win 50, avg_loss 200 → negative edge → ₹0."""
        amount = size_position_kelly(100_000, win_rate=0.30, avg_win=50, avg_loss=200)
        assert amount == 0.0


# ===========================================================================
# 3.5 — Max positions cap (pure function)
# ===========================================================================

class TestMaxPositions:
    def test_allowed_when_below_cap(self):
        allowed, _ = check_max_positions(open_count=2, max_allowed=5)
        assert allowed is True

    def test_blocked_when_at_cap(self):
        allowed, reason = check_max_positions(open_count=5, max_allowed=5)
        assert allowed is False
        assert "5" in reason

    def test_blocked_when_above_cap(self):
        allowed, _ = check_max_positions(open_count=6, max_allowed=5)
        assert allowed is False

    def test_reason_mentions_current_count(self):
        _, reason = check_max_positions(open_count=7, max_allowed=5)
        assert "7" in reason


# ===========================================================================
# 3.4 — Kill switch API (integration)
# ===========================================================================

@pytest.mark.asyncio
async def test_kill_switch_returns_halted_status():
    """POST /api/kill-switch → status=halted, trades_halted ≥ 0."""
    # Reset kill switch before test
    routes_module._kill_switch_active = False

    with patch("paper_trading.simulator.halt_all_open", return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/kill-switch")

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "halted"
    assert "trades_halted" in data
    assert routes_module._kill_switch_active is True


@pytest.mark.asyncio
async def test_kill_switch_blocks_subsequent_paper_enter():
    """After kill switch: POST /api/paper-trade/enter → 403."""
    routes_module._kill_switch_active = True  # simulate already activated

    payload = {
        "ticker": "NIFTY", "strike": 22000, "direction": "BUY_CE",
        "entry_price": 150.0, "lots": 1, "lot_size": 25, "signal": {},
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/paper-trade/enter", json=payload)

    assert res.status_code == 403
    assert "kill switch" in res.json()["detail"].lower()

    # Restore for other tests
    routes_module._kill_switch_active = False


@pytest.mark.asyncio
async def test_kill_switch_status_endpoint():
    """GET /api/kill-switch/status reflects current state."""
    routes_module._kill_switch_active = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/kill-switch/status")
    assert res.status_code == 200
    assert res.json()["active"] is False


@pytest.mark.asyncio
async def test_kill_switch_halts_open_trades():
    """Kill switch calls halt_all_open and returns their count."""
    routes_module._kill_switch_active = False
    fake_trades = [
        {"trade_id": 1, "ticker": "NIFTY",    "direction": "BUY_CE"},
        {"trade_id": 2, "ticker": "BANKNIFTY", "direction": "BUY_PE"},
    ]
    with patch("paper_trading.simulator.halt_all_open", return_value=fake_trades):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/kill-switch")

    data = res.json()
    assert data["trades_halted"] == 2
    assert len(data["halted_trades"]) == 2

    routes_module._kill_switch_active = False


# ===========================================================================
# 3.2 + 3.5 — daily cutoff and position cap gate in paper_enter (API)
# ===========================================================================

@pytest.mark.asyncio
async def test_paper_enter_blocked_by_daily_loss_limit():
    """Daily P&L = -2000 on 100k capital (2% loss) → enter blocked with 403."""
    routes_module._kill_switch_active = False

    payload = {
        "ticker": "NIFTY", "strike": 22000, "direction": "BUY_CE",
        "entry_price": 150.0, "lots": 1, "lot_size": 25, "signal": {},
    }
    with patch("paper_trading.simulator.get_daily_pnl", return_value=-2000.0), \
         patch("paper_trading.simulator.get_open_count", return_value=0):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/paper-trade/enter", json=payload)

    assert res.status_code == 403
    assert "daily cutoff" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_paper_enter_blocked_when_positions_full():
    """Open positions = max_open_positions → enter blocked with 403 (TDD 3.5)."""
    routes_module._kill_switch_active = False

    payload = {
        "ticker": "NIFTY", "strike": 22000, "direction": "BUY_CE",
        "entry_price": 150.0, "lots": 1, "lot_size": 25, "signal": {},
    }
    # Patch daily_pnl safe, open_count at max (default max=5)
    with patch("paper_trading.simulator.get_daily_pnl", return_value=0.0), \
         patch("paper_trading.simulator.get_open_count", return_value=5):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/paper-trade/enter", json=payload)

    assert res.status_code == 403
    assert "position cap" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_paper_enter_succeeds_when_all_checks_pass():
    """When all risk checks pass, trade is entered normally."""
    routes_module._kill_switch_active = False

    payload = {
        "ticker": "NIFTY", "strike": 22000, "direction": "BUY_CE",
        "entry_price": 150.0, "lots": 1, "lot_size": 25, "signal": {},
    }
    with patch("paper_trading.simulator.get_daily_pnl", return_value=0.0), \
         patch("paper_trading.simulator.get_open_count", return_value=0), \
         patch("paper_trading.simulator.enter_trade", return_value={"trade_id": 99, "status": "OPEN"}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/paper-trade/enter", json=payload)

    assert res.status_code == 200
    assert res.json()["status"] == "OPEN"
