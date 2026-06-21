"""Tests for the backtesting engine — synthetic/fixture data only, no network calls."""
from unittest.mock import patch

import pandas as pd
import pytest


def test_fetch_india_daily_passes_start_end_to_yfinance():
    from data.market_data import fetch_india_daily

    fake_df = pd.DataFrame({
        "Open": [100.0], "High": [101.0], "Low": [99.0],
        "Close": [100.5], "Volume": [1000],
    }, index=pd.DatetimeIndex(["2023-01-02"], name="Date"))

    with patch("data.market_data.yf.download", return_value=fake_df) as mock_dl:
        fetch_india_daily("RELIANCE", start="2023-01-01", end="2023-06-01")

    _, kwargs = mock_dl.call_args
    assert kwargs["start"] == "2023-01-01"
    assert kwargs["end"] == "2023-06-01"
    assert "period" not in kwargs


def test_fetch_india_daily_still_defaults_to_period_when_no_window_given():
    from data.market_data import fetch_india_daily

    fake_df = pd.DataFrame({
        "Open": [100.0], "High": [101.0], "Low": [99.0],
        "Close": [100.5], "Volume": [1000],
    }, index=pd.DatetimeIndex(["2023-01-02"], name="Date"))

    with patch("data.market_data.yf.download", return_value=fake_df) as mock_dl:
        fetch_india_daily("RELIANCE", period="3mo")

    _, kwargs = mock_dl.call_args
    assert kwargs["period"] == "3mo"
    assert kwargs.get("start") is None
    assert kwargs.get("end") is None


def test_backtest_models_create_and_roundtrip(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database.models import Base, BacktestRun, BacktestTrade

    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    run = BacktestRun(
        symbol="RELIANCE", strategy_id="DONCHIAN_BRK", market="INDIA",
        params_json="{}", start_date="2023-01-01", end_date="2023-06-01",
        starting_capital=100000.0, ending_capital=105000.0, total_trades=1,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    trade = BacktestTrade(
        run_id=run.run_id, symbol="RELIANCE", strategy_id="DONCHIAN_BRK",
        entry_date="2023-02-01", exit_date="2023-02-10",
        entry_price=100.0, exit_price=110.0, quantity=10.0,
        net_pnl=95.0, outcome="WIN", exit_reason="TRAILING_CHANNEL",
    )
    db.add(trade)
    db.commit()

    fetched_run = db.query(BacktestRun).filter(BacktestRun.run_id == run.run_id).first()
    fetched_trades = db.query(BacktestTrade).filter(BacktestTrade.run_id == run.run_id).all()
    assert fetched_run.symbol == "RELIANCE"
    assert len(fetched_trades) == 1
    assert fetched_trades[0].outcome == "WIN"


def test_metrics_hand_computed_fixture():
    from engine.backtest_metrics import (
        win_rate, profit_factor, max_drawdown, avg_rr_achieved, compute_all_metrics,
    )

    trades = [
        {"net_pnl": 100.0, "actual_rr_achieved": 2.0},
        {"net_pnl": -50.0, "actual_rr_achieved": -1.0},
        {"net_pnl": 200.0, "actual_rr_achieved": 3.0},
        {"net_pnl": -50.0, "actual_rr_achieved": -1.0},
    ]
    # win_rate: 2 wins / 4 closed = 0.5
    assert win_rate(trades) == 0.5
    # profit_factor: gross_profit=300, gross_loss=100 -> 3.0
    assert profit_factor(trades) == 3.0
    # avg_rr_achieved: (2 - 1 + 3 - 1) / 4 = 0.75
    assert avg_rr_achieved(trades) == 0.75

    equity_curve = [100000, 105000, 103000, 110000, 99000, 108000]
    # peak before the dip is 110000, trough is 99000 -> (99000-110000)/110000
    expected_dd = (99000 - 110000) / 110000
    assert abs(max_drawdown(equity_curve) - expected_dd) < 1e-9

    all_metrics = compute_all_metrics(trades, equity_curve)
    assert all_metrics["total_trades"] == 4
    assert all_metrics["win_rate"] == 0.5
    assert all_metrics["total_net_pnl"] == 200.0


def test_metrics_empty_inputs_dont_crash():
    from engine.backtest_metrics import compute_all_metrics, win_rate, profit_factor, max_drawdown

    assert win_rate([]) == 0.0
    assert profit_factor([]) == 0.0
    assert max_drawdown([]) == 0.0
    metrics = compute_all_metrics([], [])
    assert metrics["total_trades"] == 0
    assert metrics["win_rate"] == 0.0


def test_sharpe_ratio_handles_near_zero_variance_from_float_noise():
    """A clean, steadily-compounding equity curve has returns that are mathematically
    identical (e.g. exactly 1% per bar) but differ at the 1e-16 level due to floating-
    point accumulation in repeated multiplication — exact `variance == 0` checks miss
    this, producing a division by a near-zero std_r and a meaningless astronomically
    large Sharpe instead of the intended 0.0 sentinel."""
    from engine.backtest_metrics import sharpe_ratio

    equity_curve = [100.0 * (1.01 ** i) for i in range(10)]
    result = sharpe_ratio(equity_curve)
    assert result == 0.0
