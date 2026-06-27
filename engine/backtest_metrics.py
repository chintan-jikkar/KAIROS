"""
Pure stat functions over backtest results — no DB, no I/O. Every function takes a
list of trade dicts (each with at least `net_pnl`, optionally `actual_rr_achieved`)
and/or an equity curve (list of floats), and returns a plain number or dict.
"""
import math


def win_rate(trades: list[dict]) -> float:
    closed = [t for t in trades if t.get("net_pnl") is not None]
    if not closed:
        return 0.0
    wins = [t for t in closed if t["net_pnl"] > 0]
    return len(wins) / len(closed)


def profit_factor(trades: list[dict]) -> float:
    gross_profit = sum(t["net_pnl"] for t in trades if t.get("net_pnl", 0) > 0)
    gross_loss = abs(sum(t["net_pnl"] for t in trades if t.get("net_pnl", 0) < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def sharpe_ratio(equity_curve: list[float], periods_per_year: int = 252) -> float:
    """Annualized Sharpe from bar-over-bar equity returns. Risk-free rate assumed 0
    (consistent with KAIROS having no cash-yield modeling anywhere else)."""
    if len(equity_curve) < 2:
        return 0.0
    returns = [
        (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1] != 0
    ]
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    std_r = math.sqrt(variance)
    if std_r < 1e-12:
        return 0.0
    return (mean_r / std_r) * math.sqrt(periods_per_year)


def max_drawdown(equity_curve: list[float]) -> float:
    """Most negative (peak-to-trough)/peak seen, as a fraction (e.g. -0.20 = -20%)."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        dd = (value - peak) / peak if peak else 0.0
        max_dd = min(max_dd, dd)
    return max_dd


MIN_VAR_SAMPLE_SIZE = 20  # below this, a percentile-based tail estimate is too noisy to trust


def historical_var(equity_curve: list[float], confidence: float = 0.95) -> float | None:
    """Historical-simulation VaR: the (1-confidence) percentile of daily returns,
    as a negative fraction (e.g. -0.032 = "expect to lose ~3.2%"), matching
    max_drawdown's sign convention. Returns None (not 0.0) below
    MIN_VAR_SAMPLE_SIZE observations — a fabricated 0.0 would read as "zero risk."
    """
    returns = [
        (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1] != 0
    ]
    if len(returns) < MIN_VAR_SAMPLE_SIZE:
        return None
    returns.sort()
    index = max(0, math.ceil(len(returns) * (1 - confidence) - 1e-9) - 1)
    return returns[index]


def conditional_var(equity_curve: list[float], confidence: float = 0.95) -> float | None:
    """Conditional VaR / Expected Shortfall: mean of all returns at or below the
    historical_var cutoff. Same sign convention and minimum-sample-size rule as
    historical_var."""
    returns = [
        (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1] != 0
    ]
    if len(returns) < MIN_VAR_SAMPLE_SIZE:
        return None
    returns.sort()
    index = max(0, math.ceil(len(returns) * (1 - confidence) - 1e-9) - 1)
    tail = returns[: index + 1]
    return sum(tail) / len(tail)


def avg_rr_achieved(trades: list[dict]) -> float:
    rrs = [t["actual_rr_achieved"] for t in trades if t.get("actual_rr_achieved") is not None]
    return sum(rrs) / len(rrs) if rrs else 0.0


def compute_all_metrics(trades: list[dict], equity_curve: list[float]) -> dict:
    closed = [t for t in trades if t.get("net_pnl") is not None]
    return {
        "total_trades": len(closed),
        "win_rate": win_rate(closed),
        "profit_factor": profit_factor(closed),
        "sharpe_ratio": sharpe_ratio(equity_curve),
        "max_drawdown_pct": max_drawdown(equity_curve),
        "avg_rr_achieved": avg_rr_achieved(closed),
        "total_net_pnl": sum(t["net_pnl"] for t in closed) if closed else 0.0,
        "total_costs": sum(t.get("total_costs", 0) or 0 for t in closed),
    }
