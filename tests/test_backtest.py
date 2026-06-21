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


def _build_synthetic_ohlcv(n_bars: int = 60, overrides: dict | None = None) -> pd.DataFrame:
    """Deterministic OHLCV fixture: 40 flat consolidation bars (close=100), a clean
    breakout on bar 40 (close=110, comfortably above the 20-bar high), 3 bars holding
    above, then a hard crash on bars 44-46 (close 90 -> 70 -> 50), then flat at the
    bottom through bar 59. Engineered so DONCHIAN_BRK fires a fresh-breakout BUY on
    bar 40 and an exit within the next several bars. `overrides` replaces specific
    bar dicts by index — used to make two fixtures diverge only after a given bar,
    for the no-lookahead test."""
    rows = []
    for _ in range(40):
        rows.append({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 100000.0})
    rows.append({"open": 104.0, "high": 112.0, "low": 104.0, "close": 110.0, "volume": 150000.0})
    for _ in range(3):
        rows.append({"open": 110.0, "high": 113.0, "low": 108.0, "close": 111.0, "volume": 100000.0})
    for close in (90.0, 70.0, 50.0):
        rows.append({"open": close + 5, "high": close + 6, "low": close - 5, "close": close, "volume": 200000.0})
    while len(rows) < n_bars:
        rows.append({"open": 50.0, "high": 51.0, "low": 49.0, "close": 50.0, "volume": 100000.0})
    rows = rows[:n_bars]

    if overrides:
        for idx, row in overrides.items():
            rows[idx] = row

    dates = pd.bdate_range("2023-01-02", periods=n_bars)
    df = pd.DataFrame(rows, index=dates)
    df.index.name = "Date"
    df["symbol"] = "TESTSYM"
    return df


def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    from data.indicators import add_all_strategy_indicators
    return add_all_strategy_indicators(df.copy())


def test_simulate_no_lookahead():
    """Two fixtures, identical through bar 50, differing wildly only on bars 51-59.
    Simulating both with end=bar 50's date must give byte-identical results — if it
    doesn't, the loop peeked at data past `end`."""
    from engine.backtest import _simulate_trades

    df_a = _add_indicators(_build_synthetic_ohlcv(60))
    wild_tail = {
        i: {"open": 9999.0, "high": 9999.0, "low": 1.0, "close": 9999.0, "volume": 999999.0}
        for i in range(51, 60)
    }
    df_b = _add_indicators(_build_synthetic_ohlcv(60, overrides=wild_tail))

    start = df_a.index[35].strftime("%Y-%m-%d")
    end = df_a.index[50].strftime("%Y-%m-%d")

    kwargs = dict(symbol="TESTSYM", strategy_id="DONCHIAN_BRK", start=start, end=end,
                  params=None, starting_capital=100000.0, market="INDIA", segment="equity_intraday")
    result_a = _simulate_trades(df_a, **kwargs)
    result_b = _simulate_trades(df_b, **kwargs)

    assert result_a["trades"] == result_b["trades"]
    assert result_a["equity_curve"] == result_b["equity_curve"]


def test_simulate_position_sizing_matches_calculate_position_size():
    from engine.backtest import _simulate_trades
    from engine.risk import calculate_position_size

    df = _add_indicators(_build_synthetic_ohlcv(60))
    start = df.index[35].strftime("%Y-%m-%d")
    end = df.index[43].strftime("%Y-%m-%d")

    result = _simulate_trades(df, "TESTSYM", "DONCHIAN_BRK", start, end,
                              params=None, starting_capital=100000.0,
                              market="INDIA", segment="equity_intraday")

    assert len(result["trades"]) >= 1
    trade = result["trades"][0]
    expected_qty = calculate_position_size(
        portfolio_value=100000.0,
        entry_price=trade["entry_price"],
        stop_price=trade["stop_loss_price"],
    )
    assert trade["quantity"] == expected_qty


def test_simulate_cost_matches_calculate_costs():
    from engine.backtest import _simulate_trades
    from engine.costs import calculate_costs

    df = _add_indicators(_build_synthetic_ohlcv(60))
    start = df.index[35].strftime("%Y-%m-%d")
    end = df.index[46].strftime("%Y-%m-%d")

    result = _simulate_trades(df, "TESTSYM", "DONCHIAN_BRK", start, end,
                              params=None, starting_capital=100000.0,
                              market="INDIA", segment="equity_intraday")

    closed = [t for t in result["trades"] if t.get("exit_price") is not None]
    assert len(closed) >= 1
    trade = closed[0]
    expected_costs = calculate_costs(
        "INDIA", buy_price=trade["entry_price"], sell_price=trade["exit_price"],
        quantity=trade["quantity"], segment="equity_intraday",
    )
    assert abs(trade["total_costs"] - expected_costs["total_cost"]) < 1e-6


def test_simulate_exit_reason_is_valid_for_strategy():
    from engine.backtest import _simulate_trades

    df = _add_indicators(_build_synthetic_ohlcv(60))
    start = df.index[35].strftime("%Y-%m-%d")
    end = df.index[46].strftime("%Y-%m-%d")

    result = _simulate_trades(df, "TESTSYM", "DONCHIAN_BRK", start, end,
                              params=None, starting_capital=100000.0,
                              market="INDIA", segment="equity_intraday")

    closed = [t for t in result["trades"] if t.get("exit_reason") is not None]
    assert len(closed) >= 1
    # strategies/donchian_breakout.py::should_exit only ever returns these two reasons
    # (or our own synthetic BACKTEST_END if the range ends mid-trade). Asserting
    # membership rather than the one exact reason keeps this test robust to harmless
    # ATR rolling-computation nuances rather than pinning a hand-derived decimal.
    assert closed[0]["exit_reason"] in {"STOP", "TRAILING_CHANNEL", "BACKTEST_END"}
    assert closed[0]["entry_price"] > 0
    assert closed[0]["exit_price"] > 0


def test_simulate_raises_on_unknown_strategy():
    from engine.backtest import _simulate_trades

    df = _add_indicators(_build_synthetic_ohlcv(60))
    with pytest.raises(ValueError):
        _simulate_trades(df, "TESTSYM", "NOT_A_REAL_STRATEGY", "2023-01-01", "2023-03-01")


def test_simulate_rejects_intraday_strategies_even_though_they_exist_in_registry():
    """ORB_BRK is a real strategy_id in engine.signals.STRATEGY_REGISTRY (used live),
    but it's intraday and explicitly out of scope for this daily-bar backtester."""
    from engine.backtest import _simulate_trades
    from engine.signals import STRATEGY_REGISTRY

    assert "ORB_BRK" in STRATEGY_REGISTRY  # sanity check the premise of this test
    df = _add_indicators(_build_synthetic_ohlcv(60))
    with pytest.raises(ValueError):
        _simulate_trades(df, "TESTSYM", "ORB_BRK", "2023-01-01", "2023-03-01")
