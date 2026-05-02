from typing import List, Dict, Any


def build_equity_curve(trades: List[Dict[str, Any]]) -> List[Dict]:
    closed = [t for t in trades if t.get("status") == "CLOSED" and t.get("exit_time")]
    closed.sort(key=lambda t: t["exit_time"])
    cumulative = 0.0
    curve = []
    for trade in closed:
        pnl = float(trade.get("pnl") or 0)
        cumulative += pnl
        curve.append({
            "time": trade["exit_time"],
            "pnl": round(pnl, 2),
            "cumulative_pnl": round(cumulative, 2),
            "trade_id": trade["id"],
            "ticker": trade.get("ticker", ""),
            "direction": trade.get("direction", ""),
        })
    return curve


def build_drawdown_series(equity_curve: List[Dict]) -> List[Dict]:
    if not equity_curve:
        return []
    peak = 0.0
    result = []
    for point in equity_curve:
        cum = point["cumulative_pnl"]
        peak = max(peak, cum)
        drawdown = round((peak - cum) / peak * 100, 2) if peak > 0 else 0.0
        result.append({
            "time": point["time"],
            "cumulative_pnl": cum,
            "peak": round(peak, 2),
            "drawdown_pct": drawdown,
        })
    return result


def _max_streak(pnls: List[float], win: bool) -> int:
    max_s = cur_s = 0
    for p in pnls:
        if (p > 0) == win:
            cur_s += 1
            max_s = max(max_s, cur_s)
        else:
            cur_s = 0
    return max_s


def compute_analytics(trades: List[Dict[str, Any]]) -> Dict:
    closed = [t for t in trades if t.get("status") == "CLOSED"]
    if not closed:
        return {
            "total_trades": 0,
            "equity_curve": [],
            "drawdown_series": [],
            "max_drawdown_pct": 0.0,
            "current_drawdown_pct": 0.0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "best_streak": 0,
            "worst_streak": 0,
        }

    curve = build_equity_curve(trades)
    dd = build_drawdown_series(curve)
    pnls = [p["pnl"] for p in curve]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    max_dd = max((d["drawdown_pct"] for d in dd), default=0.0)
    cur_dd = dd[-1]["drawdown_pct"] if dd else 0.0
    loss_sum = sum(losses)

    return {
        "total_trades": len(closed),
        "equity_curve": curve,
        "drawdown_series": dd,
        "max_drawdown_pct": round(max_dd, 2),
        "current_drawdown_pct": round(cur_dd, 2),
        "total_pnl": round(sum(pnls), 2),
        "win_rate": round(len(wins) / len(pnls) * 100, 1),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(loss_sum / len(losses), 2) if losses else 0.0,
        "profit_factor": round(sum(wins) / abs(loss_sum), 2) if loss_sum != 0 else 0.0,
        "best_streak": _max_streak(pnls, win=True),
        "worst_streak": _max_streak(pnls, win=False),
    }
