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


def test_historical_var_and_conditional_var_hand_computed_fixture():
    from engine.backtest_metrics import historical_var, conditional_var

    # 100 evenly-spaced returns from -0.050 to +0.049, already sorted ascending —
    # easy to hand-verify both the 95% (worst 5) and 99% (worst 1) tail cutoffs.
    returns = [-0.050 + i * 0.001 for i in range(100)]
    equity_curve = [100_000.0]
    for r in returns:
        equity_curve.append(equity_curve[-1] * (1 + r))

    # 95%: ceil(100*0.05)=5 -> index 4 -> returns_sorted[4] = -0.046
    assert historical_var(equity_curve, confidence=0.95) == pytest.approx(-0.046, abs=1e-9)
    # 99%: ceil(100*0.01)=1 -> index 0 -> returns_sorted[0] = -0.050
    assert historical_var(equity_curve, confidence=0.99) == pytest.approx(-0.050, abs=1e-9)
    # CVaR 95%: mean of the worst 5 = mean(-0.050..-0.046) = -0.048
    assert conditional_var(equity_curve, confidence=0.95) == pytest.approx(-0.048, abs=1e-9)
    # CVaR 99%: mean of the worst 1 = -0.050
    assert conditional_var(equity_curve, confidence=0.99) == pytest.approx(-0.050, abs=1e-9)
    # Sign convention matches max_drawdown's: negative fraction, not flipped-positive.
    assert historical_var(equity_curve, confidence=0.95) < 0


def test_historical_var_and_conditional_var_require_minimum_sample_size():
    from engine.backtest_metrics import historical_var, conditional_var, MIN_VAR_SAMPLE_SIZE

    below_floor = [100_000.0 + i * 100 for i in range(MIN_VAR_SAMPLE_SIZE)]  # 19 returns, one short
    assert historical_var(below_floor) is None
    assert conditional_var(below_floor) is None

    at_floor = [100_000.0 + i * 100 for i in range(MIN_VAR_SAMPLE_SIZE + 1)]  # exactly 20 returns
    assert historical_var(at_floor) is not None
    assert conditional_var(at_floor) is not None


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


def test_simulate_mom_cont_same_day_roundtrip(monkeypatch):
    """Engine-orchestration test for MOM_CONT's two-step entry, using a stubbed
    strategy class injected into STRATEGY_REGISTRY — isolates the *engine's*
    same-day round-trip handling from the *real* strategy's signal-generation
    conditions (which are fiddly to trigger from a synthetic fixture). Confirms
    a MOM_CONT position can never survive past the bar it was confirmed on."""
    import engine.backtest as backtest_module
    from strategies.base import BaseStrategy

    class StubMomCont(BaseStrategy):
        strategy_id = "MOM_CONT"
        name = "Stub MOM_CONT"

        def __init__(self, params=None, market="INDIA"):
            super().__init__({"exit_timing": "eod"}, market)

        def generate_signal(self, symbol, df):
            if len(df) - 1 == 5:  # flag on bar index 5 only
                return {
                    "action": "BUY", "symbol": symbol, "strategy_id": "MOM_CONT",
                    "strategy_name": "Stub MOM_CONT", "entry_price": 999.0,
                    "stop_price": 900.0, "target_price": 1100.0,
                    "planned_rr_ratio": 2.0, "signal_reason": "stub flag",
                    "deferred": True, "indicators": {},
                }
            return None

        def check_gap_and_confirm(self, signal, open_price):
            return {
                **signal, "entry_price": open_price,
                "stop_price": open_price * 0.98, "target_price": open_price * 1.05,
                "deferred": False,
            }

        def should_exit(self, trade, current_bar):
            if current_bar.get("is_eod"):
                return True, "EOD"
            return False, ""

    rows = [{"open": 100.0 + i, "high": 106.0 + i, "low": 99.0 + i, "close": 105.0 + i, "volume": 100000.0}
            for i in range(10)]
    dates = pd.bdate_range("2023-01-02", periods=10)
    df = pd.DataFrame(rows, index=dates)
    df.index.name = "Date"
    df["symbol"] = "TESTSYM"

    monkeypatch.setitem(backtest_module.STRATEGY_REGISTRY, "MOM_CONT", StubMomCont)
    result = backtest_module._simulate_trades(
        df, "TESTSYM", "MOM_CONT", dates[0].strftime("%Y-%m-%d"), dates[9].strftime("%Y-%m-%d"),
        params=None, starting_capital=100000.0, market="INDIA", segment="equity_intraday",
    )

    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    # signal flagged on bar 5 -> confirmed at bar 6's open -> must exit same bar (bar 6's close)
    bar6_open = float(df.iloc[6]["open"])
    bar6_close = float(df.iloc[6]["close"])
    assert trade["entry_price"] == bar6_open
    assert trade["exit_price"] == bar6_close
    assert trade["exit_reason"] == "EOD"
    assert trade["entry_date"] == trade["exit_date"]  # same bar -> zero hold time


def test_simulate_rsi2_ovn_eod_fills_at_open(monkeypatch):
    """Engine-orchestration test for RSI2_OVN's exit_timing='next_open' contract —
    confirms that when should_exit returns the 'EOD' reason, the fill happens at
    that bar's OPEN (per OPEN_FILL_EXIT_REASONS), not its close, unlike every other
    exit reason for every other strategy in this engine."""
    import engine.backtest as backtest_module
    from strategies.base import BaseStrategy

    class StubRSI2Ovn(BaseStrategy):
        strategy_id = "RSI2_OVN"
        name = "Stub RSI2_OVN"

        def __init__(self, params=None, market="INDIA"):
            super().__init__({"exit_timing": "next_open"}, market)

        def generate_signal(self, symbol, df):
            if len(df) - 1 == 5:
                return {
                    "action": "BUY", "symbol": symbol, "strategy_id": "RSI2_OVN",
                    "strategy_name": "Stub RSI2_OVN", "entry_price": float(df.iloc[-1]["close"]),
                    "stop_price": float(df.iloc[-1]["close"]) * 0.96,
                    "target_price": float(df.iloc[-1]["close"]) * 1.08,
                    "planned_rr_ratio": 2.0, "signal_reason": "stub signal", "indicators": {},
                }
            return None

        def should_exit(self, trade, current_bar):
            return True, "EOD"

    rows = [{"open": 100.0 + i, "high": 106.0 + i, "low": 99.0 + i, "close": 105.0 + i, "volume": 100000.0}
            for i in range(10)]
    dates = pd.bdate_range("2023-01-02", periods=10)
    df = pd.DataFrame(rows, index=dates)
    df.index.name = "Date"
    df["symbol"] = "TESTSYM"

    monkeypatch.setitem(backtest_module.STRATEGY_REGISTRY, "RSI2_OVN", StubRSI2Ovn)
    result = backtest_module._simulate_trades(
        df, "TESTSYM", "RSI2_OVN", dates[0].strftime("%Y-%m-%d"), dates[9].strftime("%Y-%m-%d"),
        params=None, starting_capital=100000.0, market="INDIA", segment="equity_intraday",
    )

    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    bar5_close = float(df.iloc[5]["close"])  # entry fills at signal bar's close
    bar6_open = float(df.iloc[6]["open"])    # exit fills at the NEXT bar's OPEN, not close
    assert trade["entry_price"] == bar5_close
    assert trade["exit_reason"] == "EOD"
    assert trade["exit_price"] == bar6_open
    assert trade["exit_price"] != float(df.iloc[6]["close"])  # explicitly NOT close


def test_run_sweep_covers_cartesian_product_and_shares_label():
    from engine import backtest

    captured = []

    def fake_run_backtest(symbol, strategy_id, start, end, **kwargs):
        captured.append(kwargs)
        return {"metrics": {"profit_factor": 1.0}, "trades": [], "equity_curve": []}

    with patch.object(backtest, "run_backtest", side_effect=fake_run_backtest):
        results = backtest.run_sweep(
            "RELIANCE", "DONCHIAN_BRK", "2022-01-01", "2023-01-01",
            param_grid={"entry_period": [10, 20], "atr_stop_multiplier": [1.5, 2.0]},
        )

    assert len(results) == 4  # 2 x 2 cartesian product
    labels = {kw["sweep_label"] for kw in captured}
    assert len(labels) == 1  # all 4 runs share one label
    seen_params = [kw["params"] for kw in captured]
    assert {"entry_period": 10, "atr_stop_multiplier": 1.5} in seen_params
    assert {"entry_period": 20, "atr_stop_multiplier": 2.0} in seen_params


def test_run_backtest_universe_skips_symbols_that_raise():
    from engine import backtest

    def fake_run_backtest(symbol, strategy_id, start, end, **kwargs):
        if symbol == "BADSYMBOL":
            raise ValueError("No data returned")
        return {"metrics": {"profit_factor": 1.0}, "trades": [], "equity_curve": []}

    with patch.object(backtest, "run_backtest", side_effect=fake_run_backtest):
        results = backtest.run_backtest_universe(
            ["RELIANCE", "BADSYMBOL", "TCS"], "DONCHIAN_BRK", "2022-01-01", "2023-01-01",
        )

    assert len(results) == 2  # BADSYMBOL skipped, the other 2 succeeded


def test_run_backtest_universe_skips_symbols_on_non_value_error_too():
    """The reviewer's own scenario: a transient yfinance/network failure (anything
    that isn't a ValueError) must also be skipped, not just the two deliberate
    ValueError cases run_backtest raises itself — this is the realistic failure
    mode for a multi-symbol scan making many sequential network calls."""
    from engine import backtest

    def fake_run_backtest(symbol, strategy_id, start, end, **kwargs):
        if symbol == "FLAKYSYMBOL":
            raise ConnectionError("simulated network failure")
        return {"metrics": {"profit_factor": 1.0}, "trades": [], "equity_curve": []}

    with patch.object(backtest, "run_backtest", side_effect=fake_run_backtest):
        results = backtest.run_backtest_universe(
            ["RELIANCE", "FLAKYSYMBOL", "TCS"], "DONCHIAN_BRK", "2022-01-01", "2023-01-01",
        )

    assert len(results) == 2  # FLAKYSYMBOL skipped, the other 2 succeeded


def test_cli_parses_args_and_invokes_run_backtest(monkeypatch, tmp_path):
    from engine import backtest
    import config.settings as settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))

    captured = {}

    def fake_run_backtest(symbol, strategy_id, start, end, **kwargs):
        captured["symbol"] = symbol
        captured["strategy_id"] = strategy_id
        captured["start"] = start
        captured["end"] = end
        captured["kwargs"] = kwargs
        return {"starting_capital": 100000.0, "ending_capital": 105000.0,
                "metrics": {"total_trades": 0, "win_rate": 0.0}}

    monkeypatch.setattr(backtest, "run_backtest", fake_run_backtest)
    monkeypatch.setattr(
        "sys.argv",
        ["backtest.py", "--symbol", "RELIANCE", "--strategy", "DONCHIAN_BRK",
         "--start", "2022-01-01", "--end", "2023-01-01"],
    )
    backtest._cli()

    assert captured["symbol"] == "RELIANCE"
    assert captured["strategy_id"] == "DONCHIAN_BRK"
    assert captured["start"] == "2022-01-01"
    assert captured["kwargs"]["starting_capital"] == 100000.0
    assert captured["kwargs"]["market"] == "INDIA"


def test_cli_prints_clean_error_on_failure_instead_of_raw_traceback(monkeypatch, tmp_path, capsys):
    """A malformed date or any other run_backtest failure should print one clean
    line and exit(1), not dump a multi-frame traceback on a user running this from
    a terminal — this matters because Task 7 runs this exact CLI for real."""
    from engine import backtest
    import config.settings as settings

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "test.db"))

    def fake_run_backtest(symbol, strategy_id, start, end, **kwargs):
        raise ValueError("No data returned for RELIANCE between 2023-01-01 and 2022-01-01")

    monkeypatch.setattr(backtest, "run_backtest", fake_run_backtest)
    monkeypatch.setattr(
        "sys.argv",
        ["backtest.py", "--symbol", "RELIANCE", "--strategy", "DONCHIAN_BRK",
         "--start", "2023-01-01", "--end", "2022-01-01"],
    )

    with pytest.raises(SystemExit) as exc_info:
        backtest._cli()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.out
    assert "No data returned" in captured.out
    assert "Traceback" not in captured.out


def test_persist_run_writes_run_and_trades_with_correct_linkage(tmp_path):
    """Integration-level test for _persist_run itself, against a real SQLAlchemy
    session — the exact gap that let a real bug ship past every other test (they
    either test the models directly with a manual commit+refresh before reading
    run.run_id, which masks the issue, or mock run_backtest/_simulate_trades
    entirely, bypassing _persist_run altogether). Without db.flush() after db.add(run),
    BacktestRun.run_id is still None (SQLAlchemy only fires the UUID default at
    flush/insert time) when each BacktestTrade is constructed, causing every real
    run with db= passed in to fail with a NOT NULL constraint violation."""
    from datetime import datetime
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database.models import Base, BacktestRun, BacktestTrade
    from engine.backtest import _persist_run

    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    result = {
        "symbol": "RELIANCE", "strategy_id": "DONCHIAN_BRK", "market": "INDIA",
        "start": "2023-01-01", "end": "2024-01-01",
        "starting_capital": 100000.0, "ending_capital": 102456.93,
        "sweep_label": None,
        "metrics": {
            "total_trades": 1, "win_rate": 1.0, "profit_factor": float("inf"),
            "sharpe_ratio": 1.2, "max_drawdown_pct": -0.05, "avg_rr_achieved": 2.0,
            "total_net_pnl": 2456.93, "total_costs": 12.07,
        },
        "trades": [{
            "symbol": "RELIANCE", "strategy_id": "DONCHIAN_BRK",
            "entry_date": datetime(2023, 3, 1), "exit_date": datetime(2023, 3, 15),
            "entry_price": 1109.20, "exit_price": 1219.47,
            "stop_loss_price": 1050.0, "target_price": 1250.0, "quantity": 22.54,
            "gross_pnl": 2469.0, "total_costs": 12.07, "net_pnl": 2456.93,
            "net_pnl_pct": 0.0988, "actual_rr_achieved": 1.86,
            "outcome": "WIN", "exit_reason": "TRAILING_CHANNEL", "signal_reason": "test signal",
        }],
    }

    _persist_run(db, result, params={"entry_period": 20})

    saved_run = db.query(BacktestRun).filter(BacktestRun.symbol == "RELIANCE").first()
    assert saved_run is not None
    assert saved_run.run_id is not None
    saved_trades = db.query(BacktestTrade).filter(BacktestTrade.run_id == saved_run.run_id).all()
    assert len(saved_trades) == 1
    assert saved_trades[0].net_pnl == 2456.93
    assert saved_trades[0].entry_date == datetime(2023, 3, 1).isoformat()
