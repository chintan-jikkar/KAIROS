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
