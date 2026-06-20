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
