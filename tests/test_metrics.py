"""1.3 — metrics module unit tests."""
import math
import pytest

from backtesting.metrics import (
    win_rate, net_pnl, profit_factor, expectancy,
    max_drawdown, sharpe_ratio, compute_all,
)

_TRADES = [
    {"entry_ts": "2024-01-02T09:15:00+00:00", "exit_ts": "2024-01-02T10:00:00+00:00",
     "symbol": "NIFTY", "direction": "BUY_CE", "entry_price": 21800.0, "exit_price": 21900.0, "qty": 1, "pnl": 100.0},
    {"entry_ts": "2024-01-02T10:00:00+00:00", "exit_ts": "2024-01-02T11:00:00+00:00",
     "symbol": "NIFTY", "direction": "BUY_PE", "entry_price": 21900.0, "exit_price": 21950.0, "qty": 1, "pnl": -50.0},
    {"entry_ts": "2024-01-03T09:15:00+00:00", "exit_ts": "2024-01-03T10:30:00+00:00",
     "symbol": "NIFTY", "direction": "BUY_CE", "entry_price": 21950.0, "exit_price": 22100.0, "qty": 1, "pnl": 150.0},
    {"entry_ts": "2024-01-03T10:30:00+00:00", "exit_ts": "2024-01-03T11:30:00+00:00",
     "symbol": "NIFTY", "direction": "BUY_PE", "entry_price": 22100.0, "exit_price": 22130.0, "qty": 1, "pnl": -30.0},
    {"entry_ts": "2024-01-04T09:15:00+00:00", "exit_ts": "2024-01-04T10:00:00+00:00",
     "symbol": "NIFTY", "direction": "BUY_CE", "entry_price": 22130.0, "exit_price": 22210.0, "qty": 1, "pnl": 80.0},
]


def test_win_rate():
    assert win_rate(_TRADES) == pytest.approx(3 / 5)


def test_win_rate_empty():
    assert win_rate([]) == 0.0


def test_net_pnl():
    assert net_pnl(_TRADES) == pytest.approx(250.0)


def test_profit_factor():
    # gross profit = 100 + 150 + 80 = 330; gross loss = 50 + 30 = 80
    assert profit_factor(_TRADES) == pytest.approx(330 / 80)


def test_profit_factor_no_losses():
    winning = [{"pnl": 100.0}, {"pnl": 200.0}]
    assert profit_factor(winning) == float("inf")


def test_expectancy():
    assert expectancy(_TRADES) == pytest.approx(50.0)


def test_max_drawdown():
    # equity path: 100, 50, 200, 170, 250
    # peak=100 → drop to 50: dd=50; peak=200 → drop to 170: dd=30 → max=50
    assert max_drawdown(_TRADES) == pytest.approx(50.0)


def test_max_drawdown_empty():
    assert max_drawdown([]) == 0.0


def test_sharpe_ratio_matches_reference():
    """
    Known series [100, -50, 150, -30, 80]:
    mean=50, sample_std=86.3134..., daily_sharpe=0.5794..., annualised=9.1959
    (same formula scipy.stats would use with ddof=1 and sqrt(252) scaling)
    """
    assert sharpe_ratio(_TRADES) == pytest.approx(9.1959, abs=1e-4)


def test_sharpe_ratio_single_trade():
    assert sharpe_ratio([{"pnl": 100.0}]) == 0.0


def test_compute_all_keys():
    result = compute_all(_TRADES)
    expected_keys = {"total_trades", "win_rate", "net_pnl", "profit_factor",
                     "expectancy", "max_drawdown", "sharpe_ratio"}
    assert expected_keys.issubset(result.keys())
    assert result["total_trades"] == 5
