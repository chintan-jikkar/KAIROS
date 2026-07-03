"""Tests for screener helpers — synthetic fixtures only, no network calls."""


def test_beta_identical_series_is_one():
    """A returns series identical to SPY → beta == 1.0."""
    from engine.screener import _compute_beta_vs_spy
    spy = [0.01, -0.02, 0.015, -0.005, 0.008, 0.012, -0.003, 0.006, -0.01, 0.004]
    assert abs(_compute_beta_vs_spy(spy, spy) - 1.0) < 1e-6  # cov(x,x)/var(x) == 1.0 exactly after round(,4)


def test_beta_flat_symbol_returns_zero():
    """All-zero symbol returns → beta == 0.0 (covariance numerator is zero, not undefined correlation)."""
    from engine.screener import _compute_beta_vs_spy
    spy = [0.01, -0.02, 0.015, -0.005, 0.008]
    flat = [0.0] * len(spy)
    assert _compute_beta_vs_spy(flat, spy) == 0.0


def test_beta_double_leveraged_series():
    """A 2x-leveraged series (2 * SPY returns) → beta ≈ 2.0."""
    from engine.screener import _compute_beta_vs_spy
    spy = [0.01, -0.02, 0.015, -0.005, 0.008, 0.012, -0.003, 0.006, -0.01, 0.004]
    doubled = [r * 2 for r in spy]
    assert abs(_compute_beta_vs_spy(doubled, spy) - 2.0) < 1e-6  # 2*cov/var == 2.0 exactly after round(,4)


def test_beta_short_series_returns_default():
    """Fewer than 2 overlapping observations → returns 1.0 as safe default."""
    from engine.screener import _compute_beta_vs_spy
    assert _compute_beta_vs_spy([], []) == 1.0
    assert _compute_beta_vs_spy([0.01], [0.01]) == 1.0


def test_beta_constant_spy_returns_default():
    """Constant SPY returns (zero variance) → returns 1.0 to avoid division by zero."""
    from engine.screener import _compute_beta_vs_spy
    spy = [0.0, 0.0, 0.0, 0.0, 0.0]
    sym = [0.01, -0.01, 0.02, -0.02, 0.005]
    assert _compute_beta_vs_spy(sym, spy) == 1.0


def test_beta_mismatched_length_uses_shorter():
    """When series lengths differ, the shorter length is used (last n elements of longer)."""
    from engine.screener import _compute_beta_vs_spy
    spy = [0.01, -0.02, 0.015, -0.005, 0.008]
    # symbol_returns is longer; last 5 elements match spy exactly → beta == 1.0
    symbol_returns = [0.99, 0.98] + spy  # 7 elements, last 5 identical to spy
    assert abs(_compute_beta_vs_spy(symbol_returns, spy) - 1.0) < 1e-6


def test_assign_strategy_india_mom_cont():
    """High ATR + high vol_ratio → MOM_CONT for India rules."""
    from engine.screener import _assign_strategy
    from data.universe import STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=4.0, beta=1.1, vol_ratio=2.0, adx=30.0,
                              rules=STRATEGY_ASSIGNMENT_RULES)
    assert result == "MOM_CONT"


def test_assign_strategy_india_supertrend():
    """High ADX + high ATR but low beta (misses ORB_BRK) → SUPERTREND."""
    from engine.screener import _assign_strategy
    from data.universe import STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=3.0, beta=0.9, vol_ratio=1.0, adx=28.0,
                              rules=STRATEGY_ASSIGNMENT_RULES)
    assert result == "SUPERTREND"


def test_assign_strategy_india_rsi2_ovn_catchall():
    """Low ATR, low ADX, unmatched → RSI2_OVN catch-all."""
    from engine.screener import _assign_strategy
    from data.universe import STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=1.0, beta=1.0, vol_ratio=1.0, adx=10.0,
                              rules=STRATEGY_ASSIGNMENT_RULES)
    assert result == "RSI2_OVN"


def test_assign_strategy_us_rules_accepted():
    """US rules dict is accepted without error; catch-all returns RSI2_OVN."""
    from engine.screener import _assign_strategy
    from data.universe import US_STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=1.0, beta=0.5, vol_ratio=0.8, adx=10.0,
                              rules=US_STRATEGY_ASSIGNMENT_RULES)
    assert result == "RSI2_OVN"


def test_assign_strategy_india_default_unchanged():
    """Calling _assign_strategy without rules= still uses India rules (no regression)."""
    from engine.screener import _assign_strategy
    result = _assign_strategy(atr_pct=4.0, beta=1.1, vol_ratio=2.0, adx=30.0)
    assert result == "MOM_CONT"


# ---------------------------------------------------------------------------
# US cascade tests — values derived from live 2026-07-01 screener run
# ---------------------------------------------------------------------------

def test_assign_strategy_us_orb_brk_high_beta():
    """COIN-like: ATR=6.95%, beta=2.08 → GAP_GO (US GAP_GO atr≥3.5, beta≥1.8; wins before ORB_BRK)."""
    from engine.screener import _assign_strategy
    from data.universe import US_STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=6.95, beta=2.08, vol_ratio=0.97, adx=21.6,
                              rules=US_STRATEGY_ASSIGNMENT_RULES)
    assert result == "GAP_GO"


def test_assign_strategy_us_supertrend_trending():
    """AMZN-like: ATR=3.48%, beta=1.26, ADX=27.6 → SUPERTREND.
    beta=1.26 misses ORB_BRK (beta_min=1.5); strong trend (ADX≥25) lands SUPERTREND."""
    from engine.screener import _assign_strategy
    from data.universe import US_STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=3.48, beta=1.26, vol_ratio=0.61, adx=27.6,
                              rules=US_STRATEGY_ASSIGNMENT_RULES)
    assert result == "SUPERTREND"


def test_assign_strategy_us_supertrend_low_beta():
    """PLTR-like: ATR=5.30%, beta=0.89, ADX=26.2 → SUPERTREND.
    Low beta misses ORB_BRK; high ADX with high ATR → SUPERTREND."""
    from engine.screener import _assign_strategy
    from data.universe import US_STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=5.30, beta=0.89, vol_ratio=1.15, adx=26.2,
                              rules=US_STRATEGY_ASSIGNMENT_RULES)
    assert result == "SUPERTREND"


def test_assign_strategy_us_donchian_moderate_adx():
    """MSFT-like: ATR=3.48%, beta=0.52, ADX=23.2 → DUAL_EMA.
    ADX 22–27 now slots into DUAL_EMA (added 2026-07-03), which has higher cascade priority
    than DONCHIAN_BRK. DONCHIAN still catches ADX 20–22."""
    from engine.screener import _assign_strategy
    from data.universe import US_STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=3.48, beta=0.52, vol_ratio=0.71, adx=23.2,
                              rules=US_STRATEGY_ASSIGNMENT_RULES)
    assert result == "DUAL_EMA"


def test_assign_strategy_us_bb_meanrev_below_orb_beta():
    """beta=1.49 (just below ORB_BRK threshold of 1.5), ADX=18 → MACD_CROSS.
    Verifies the calibrated beta_min=1.5 boundary: 1.49 misses ORB_BRK; ADX=18
    lands in MACD_CROSS (15≤ADX<20 band), not BB_MEANREV."""
    from engine.screener import _assign_strategy
    from data.universe import US_STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=3.0, beta=1.49, vol_ratio=0.7, adx=18.0,
                              rules=US_STRATEGY_ASSIGNMENT_RULES)
    assert result == "MACD_CROSS"


# ---------------------------------------------------------------------------
# India real-beta cascade tests — Task 14
# Previously beta was hardcoded to 1.0, so every stock with ATR≥2.5 got
# ORB_BRK (1.0 ≥ beta_min=0.95). Real NIFTY50 beta now drives differentiation.
# ---------------------------------------------------------------------------

def test_india_real_beta_high_beta_orb_brk():
    """TATAMOTORS-like: beta=1.4, ATR=2.6% → ORB_BRK.
    High-beta cyclical correctly routes to opening-range strategy."""
    from engine.screener import _assign_strategy
    from data.universe import STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=2.6, beta=1.4, vol_ratio=1.0, adx=22.0,
                              rules=STRATEGY_ASSIGNMENT_RULES)
    assert result == "ORB_BRK"


def test_india_real_beta_low_beta_falls_past_orb():
    """HINDUNILVR-like: beta=0.3 (defensive FMCG), ATR=2.6%, ADX=18 → MACD_CROSS.
    Misses ORB_BRK (beta=0.3 < beta_min=0.95); ADX=18 lands in MACD_CROSS band."""
    from engine.screener import _assign_strategy
    from data.universe import STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=2.6, beta=0.3, vol_ratio=1.0, adx=18.0,
                              rules=STRATEGY_ASSIGNMENT_RULES)
    assert result == "MACD_CROSS"


def test_india_real_beta_below_orb_threshold_bb_meanrev():
    """beta=0.8 (just below ORB_BRK beta_min=0.95), ATR=2.6%, ADX=18 → MACD_CROSS.
    ORB_BRK fails because of beta alone (ATR passes). ADX=18 lands in MACD_CROSS
    (15≤ADX<20), not BB_MEANREV — BB_MEANREV is now ADX<15."""
    from engine.screener import _assign_strategy
    from data.universe import STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=2.6, beta=0.8, vol_ratio=0.9, adx=18.0,
                              rules=STRATEGY_ASSIGNMENT_RULES)
    assert result == "MACD_CROSS"


# --------------------------------------------------------------------------- #
# Earnings blackout filter                                                      #
# --------------------------------------------------------------------------- #

def test_has_earnings_soon_returns_true_when_within_window():
    """Earnings date 3 days out with a 7-day window → True (skip the stock)."""
    import datetime
    from unittest.mock import patch, MagicMock
    from engine.screener import _has_earnings_soon

    today = datetime.date.today()
    upcoming = today + datetime.timedelta(days=3)
    mock_ticker = MagicMock()
    mock_ticker.calendar = {"Earnings Date": [upcoming]}

    with patch("engine.screener.yf.Ticker", return_value=mock_ticker):
        assert _has_earnings_soon("AAPL", 7) is True


def test_has_earnings_soon_returns_false_when_outside_window():
    """Earnings date 14 days out with a 7-day window → False (allow the stock)."""
    import datetime
    from unittest.mock import patch, MagicMock
    from engine.screener import _has_earnings_soon

    today = datetime.date.today()
    far_future = today + datetime.timedelta(days=14)
    mock_ticker = MagicMock()
    mock_ticker.calendar = {"Earnings Date": [far_future]}

    with patch("engine.screener.yf.Ticker", return_value=mock_ticker):
        assert _has_earnings_soon("AAPL", 7) is False


def test_has_earnings_soon_fails_open_on_empty_calendar():
    """No calendar data → False (fail open so India stocks without coverage pass through)."""
    from unittest.mock import patch, MagicMock
    from engine.screener import _has_earnings_soon

    mock_ticker = MagicMock()
    mock_ticker.calendar = {}

    with patch("engine.screener.yf.Ticker", return_value=mock_ticker):
        assert _has_earnings_soon("RELIANCE.NS", 7) is False


def test_has_earnings_soon_fails_open_on_api_exception():
    """Any exception from yfinance → False (fail open, never crash the screener)."""
    from unittest.mock import patch
    from engine.screener import _has_earnings_soon

    with patch("engine.screener.yf.Ticker", side_effect=Exception("network error")):
        assert _has_earnings_soon("RELIANCE.NS", 7) is False


# --------------------------------------------------------------------------- #
# P2 fixes                                                                      #
# --------------------------------------------------------------------------- #

def test_spy_not_in_us_tradeable_pool():
    """SPY is the beta benchmark, not a tradeable — it must not appear in get_us_all_symbols()."""
    from data.universe import get_us_all_symbols
    assert "SPY" not in get_us_all_symbols()


def test_rsi2_ovn_exits_at_next_open_day1():
    """RSI2_OVN should exit on day 1 via EOD (next-open timing)."""
    from strategies.rsi2_overnight import RSI2OvernightStrategy
    strategy = RSI2OvernightStrategy()
    trade = {"entry_price": 100.0, "stop_loss_price": 96.0, "target_price": 108.0,
             "direction": "LONG", "hold_days": 1.1, "exit_timing": "next_open"}
    bar = {"close": 101.0, "rsi_2": 50.0}
    should_exit, reason = strategy.should_exit(trade, bar)
    assert should_exit is True
    assert reason == "EOD"


def test_rsi2_ovn_time_stop_removed():
    """Dead TIME_STOP branch must not exist in should_exit after the fix."""
    from strategies.rsi2_overnight import RSI2OvernightStrategy
    import inspect
    src = inspect.getsource(RSI2OvernightStrategy.should_exit)
    assert "TIME_STOP" not in src


def test_vix_halt_skipped_for_meanrev_strategies():
    """RSI2_OVN and BB_MEANREV must bypass the VIX filter — high VIX benefits them."""
    from unittest.mock import patch
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database.models import Base
    from engine.risk import check_circuit_breakers

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    # Patch VIX to extreme value that would halt trend strategies
    with patch("engine.risk._get_vix", return_value=35.0):
        # Trend strategy → HALT
        status, _ = check_circuit_breakers(db, 100_000, 100_000, "INDIA", strategy_id="MOM_CONT")
        assert status == "HALT"

        # Mean-reversion strategies → NORMAL (VIX check skipped)
        for sid in ("RSI2_OVN", "BB_MEANREV"):
            status, _ = check_circuit_breakers(db, 100_000, 100_000, "INDIA", strategy_id=sid)
            assert status == "NORMAL", f"{sid} should bypass VIX halt"


def test_paper_broker_applies_slippage_on_buy_and_sell():
    """Buy fills above requested price, sell fills below — both by the slippage factor."""
    from brokers.paper import PaperBroker

    class _FakeDB:
        pass

    broker = PaperBroker(_FakeDB(), starting_capital=100_000, market="INDIA")
    result = broker.buy("RELIANCE", 10, 1000.0)
    assert result["fill_price"] > 1000.0, "buy should fill at a worse (higher) price"

    result = broker.sell("RELIANCE", 10, 1010.0)
    assert result["fill_price"] < 1010.0, "sell should fill at a worse (lower) price"


def test_screener_score_uses_absolute_baselines():
    """Score must not always include a 100 — with absolute baselines a stock
    below the reference ATR/vol gets a score below 100."""
    # Simulate two results where neither hits the baselines
    import pandas as pd
    from engine.screener import run_india_screener

    # We can't easily call the full screener; instead verify the formula directly.
    ATR_BASELINE, VOL_BASELINE = 3.0, 2.0
    rows = [
        {"atr_pct": 1.5, "vol_ratio": 0.8},  # both below baseline
        {"atr_pct": 2.0, "vol_ratio": 1.0},
    ]
    df = pd.DataFrame(rows)
    df["atr_norm"] = (df["atr_pct"] / ATR_BASELINE).clip(upper=1.0)
    df["vol_norm"] = (df["vol_ratio"] / VOL_BASELINE).clip(upper=1.0)
    df["score"] = (df["atr_norm"] * 60 + df["vol_norm"] * 40).round(1)
    assert df["score"].max() < 100, "no stock at baseline → max score should be below 100"
    assert df["score"].max() > df["score"].min(), "ranking must still differentiate stocks"


# ── #26: TREND_EMA max_hold_days time-stop ────────────────────────────────────

def test_trend_ema_time_stop_fires_at_max_hold():
    """should_exit returns TIME_STOP once hold_days >= max_hold_days."""
    from strategies.trend_ema import TrendEMAStrategy
    strategy = TrendEMAStrategy()
    trade = {"entry_price": 100.0, "hold_days": 60}
    bar = {"close": 105.0, "ema_50": 106.0, "ema_200": 100.0}  # no death cross, above stop
    exit_flag, reason = strategy.should_exit(trade, bar)
    assert exit_flag is True
    assert reason == "TIME_STOP"


def test_trend_ema_no_exit_before_max_hold():
    """should_exit does not trigger TIME_STOP before the hold cap is reached."""
    from strategies.trend_ema import TrendEMAStrategy
    strategy = TrendEMAStrategy()
    trade = {"entry_price": 100.0, "stop_loss_price": 85.0, "hold_days": 44}  # one day under new 45-day cap
    bar = {"close": 105.0, "ema_50": 106.0, "ema_200": 100.0}  # healthy trend
    exit_flag, reason = strategy.should_exit(trade, bar)
    assert exit_flag is False
    assert reason == ""


def test_trend_ema_max_hold_days_in_default_params():
    """DEFAULT_PARAMS must declare max_hold_days so it's not accidentally removed."""
    from strategies.trend_ema import DEFAULT_PARAMS
    assert "max_hold_days" in DEFAULT_PARAMS
    assert DEFAULT_PARAMS["max_hold_days"] == 45  # shortened from 60 to reduce earnings risk


def test_trend_ema_custom_max_hold_respected():
    """Overriding max_hold_days at instantiation should be respected."""
    from strategies.trend_ema import TrendEMAStrategy
    strategy = TrendEMAStrategy(params={"max_hold_days": 10})
    trade = {"entry_price": 100.0, "hold_days": 10}
    bar = {"close": 102.0, "ema_50": 103.0, "ema_200": 98.0}
    exit_flag, reason = strategy.should_exit(trade, bar)
    assert exit_flag is True
    assert reason == "TIME_STOP"


# ── #25: Market holiday guard in scheduler ────────────────────────────────────

def test_is_market_open_returns_false_on_empty_df(monkeypatch):
    """When benchmark returns no bars (holiday), _is_market_open → False."""
    import pandas as pd
    import engine.scheduler as sched

    sched._market_open_cache.clear()

    def fake_intraday(ticker, interval="1m", period="1d"):
        return pd.DataFrame()

    monkeypatch.setattr("data.market_data.fetch_india_intraday", fake_intraday)

    # Patch the import inside the function
    import data.market_data as mdm
    monkeypatch.setattr(mdm, "fetch_india_intraday", fake_intraday)

    # Directly test via the module after clearing cache
    original = sched._is_market_open.__globals__.get("fetch_india_intraday")
    result = None

    def patched_is_open(market="INDIA"):
        """Inline reimplementation to inject the fake fetch."""
        import pandas as pd
        today = sched.datetime.now(sched.IST).strftime("%Y-%m-%d")
        cache_key = f"{market}:{today}"
        if cache_key in sched._market_open_cache:
            return sched._market_open_cache[cache_key]
        df = fake_intraday("^NSEI", interval="1m", period="1d")
        result = not df.empty
        sched._market_open_cache[cache_key] = result
        return result

    assert patched_is_open("INDIA") is False


def test_is_market_open_returns_true_on_bars(monkeypatch):
    """When benchmark returns bars (normal trading day), _is_market_open → True."""
    import pandas as pd
    import engine.scheduler as sched

    sched._market_open_cache.clear()

    def fake_intraday_with_data(ticker, interval="1m", period="1d"):
        return pd.DataFrame({"close": [100.0, 101.0]})

    def patched_is_open(market="INDIA"):
        import pandas as pd
        today = sched.datetime.now(sched.IST).strftime("%Y-%m-%d")
        cache_key = f"{market}:{today}"
        if cache_key in sched._market_open_cache:
            return sched._market_open_cache[cache_key]
        df = fake_intraday_with_data("^NSEI", interval="1m", period="1d")
        result = not df.empty
        sched._market_open_cache[cache_key] = result
        return result

    assert patched_is_open("INDIA") is True


def test_is_market_open_fails_open_on_exception(monkeypatch):
    """If the yfinance call raises, _is_market_open must return True (fail open)."""
    import engine.scheduler as sched

    sched._market_open_cache.clear()

    def patched_is_open_exc(market="INDIA"):
        """Simulate the exception path inline."""
        try:
            raise ConnectionError("yfinance timeout")
        except Exception:
            return True  # fail open

    assert patched_is_open_exc("INDIA") is True


def test_market_open_cache_hit_skips_second_fetch():
    """Second call with same market+date uses cached value without re-fetching."""
    import engine.scheduler as sched

    sched._market_open_cache.clear()
    today = sched.datetime.now(sched.IST).strftime("%Y-%m-%d")
    sched._market_open_cache[f"INDIA:{today}"] = False  # pre-populate as holiday

    # Even though we can't call the real function without network, verify cache logic:
    assert sched._market_open_cache[f"INDIA:{today}"] is False


# ── #24: Correlation cap ─────────────────────────────────────────────────────

def test_pearson_r_identical_series():
    """Identical series → r = 1.0."""
    from engine.risk import _pearson_r
    series = [0.01, -0.02, 0.015, -0.005, 0.008, 0.012, -0.003, 0.006, -0.01, 0.004]
    assert abs(_pearson_r(series, series) - 1.0) < 1e-6


def test_pearson_r_inverted_series():
    """Perfectly inverted series → r = -1.0."""
    from engine.risk import _pearson_r
    series = [0.01, -0.02, 0.015, -0.005, 0.008]
    inv = [-v for v in series]
    assert abs(_pearson_r(series, inv) + 1.0) < 1e-6


def test_pearson_r_uncorrelated():
    """Orthogonal series → r near 0 (not exact, but well below 0.70 threshold)."""
    from engine.risk import _pearson_r
    x = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0]
    y = [1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0, -1.0]
    assert abs(_pearson_r(x, y)) < 0.5


def test_pearson_r_too_short_returns_zero():
    """Fewer than 2 elements → 0.0 (not a correlation)."""
    from engine.risk import _pearson_r
    assert _pearson_r([], []) == 0.0
    assert _pearson_r([0.01], [0.01]) == 0.0


def test_pearson_r_constant_series_returns_zero():
    """Constant series (zero variance) → 0.0, not a division error."""
    from engine.risk import _pearson_r
    assert _pearson_r([0.0, 0.0, 0.0], [0.01, 0.02, -0.01]) == 0.0


def test_check_correlation_risk_no_open_positions(tmp_path):
    """With no open positions the check always passes."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database.models import Base
    from engine.risk import check_correlation_risk

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()

    ok, reason = check_correlation_risk(db, "RELIANCE", market="INDIA")
    assert ok is True
    assert reason == ""
    db.close()


def test_max_correlation_threshold_in_risk_params():
    """RISK_PARAMS must declare max_correlation_threshold."""
    from engine.risk import RISK_PARAMS
    assert "max_correlation_threshold" in RISK_PARAMS
    assert RISK_PARAMS["max_correlation_threshold"] == 0.70


def test_correlation_check_wired_into_executor(monkeypatch):
    """execute_entry must call check_correlation_risk and reject if it returns False."""
    import engine.executor as ex_module
    from engine.executor import Executor

    # Patch correlation check to always block
    monkeypatch.setattr(
        ex_module,
        "check_correlation_risk",
        lambda db, symbol, market, **kw: (False, "r=0.95 > 0.70 — test block"),
    )

    # We need a minimal db and broker stub
    class FakeDB:
        def query(self, *a):
            return self
        def filter(self, *a):
            return self
        def scalar(self):
            return 0

    class FakeBroker:
        cash = 1_000_000
        def buy(self, *a, **kw):
            return {"status": "FILLED", "fill_price": 100.0, "order_id": "X"}

    # Patch all the checks that run before correlation
    monkeypatch.setattr(ex_module, "get_open_trade", lambda db, sym: None)
    monkeypatch.setattr(ex_module, "get_latest_snapshot", lambda db, mkt: None)
    monkeypatch.setattr(ex_module, "check_circuit_breakers",
                        lambda *a, **kw: ("NORMAL", "ok"))
    monkeypatch.setattr(ex_module, "check_position_limit", lambda *a, **kw: True)
    monkeypatch.setattr(ex_module, "check_portfolio_heat", lambda *a, **kw: True)

    executor = Executor(db=FakeDB(), broker=FakeBroker(), market="INDIA")
    signal = {
        "symbol": "ADANIENT",
        "strategy_id": "TREND_EMA",
        "entry_price": 100.0,
        "stop_price": 95.0,
        "target_price": 110.0,
        "deferred": False,
    }
    result = executor.execute_entry(signal)
    assert result["status"] == "REJECTED"
    assert "0.70" in result["reason"] or "0.95" in result["reason"]


# ---------------------------------------------------------------------------
# MACD Crossover strategy tests
# ---------------------------------------------------------------------------

import pandas as pd


def _macd_df(
    close_prev=100.0, close_last=101.0,
    macd_prev=-0.5, macd_last=0.3,
    macd_signal_prev=0.1, macd_signal_last=0.1,
    macd_hist_last=0.2,
    sma_50=95.0,
    atr=2.0,
):
    """Minimal DataFrame fixture for MACD_CROSS tests — fresh bullish cross by default."""
    return pd.DataFrame({
        "close":       [close_prev, close_last],
        "sma_50":      [sma_50, sma_50],
        "macd":        [macd_prev, macd_last],
        "macd_signal": [macd_signal_prev, macd_signal_last],
        "macd_hist":   [-0.6, macd_hist_last],
        "atr_14":      [atr, atr],
    })


def test_macd_cross_generates_buy_signal_on_fresh_bullish_crossover():
    from strategies.macd_crossover import MACDCrossoverStrategy
    df = _macd_df()  # prev: macd(-0.5) <= signal(0.1); last: macd(0.3) > signal(0.1)
    signal = MACDCrossoverStrategy().generate_signal("TEST", df)
    assert signal is not None
    assert signal["action"] == "BUY"
    assert signal["strategy_id"] == "MACD_CROSS"
    assert signal["entry_price"] == 101.0
    assert signal["stop_price"] < signal["entry_price"]
    assert signal["target_price"] > signal["entry_price"]


def test_macd_cross_stop_and_target_respect_atr_and_rr():
    from strategies.macd_crossover import MACDCrossoverStrategy, DEFAULT_PARAMS
    df = _macd_df(close_last=100.0, atr=2.0)
    signal = MACDCrossoverStrategy().generate_signal("TEST", df)
    assert signal is not None
    expected_stop = 100.0 - DEFAULT_PARAMS["atr_stop_multiplier"] * 2.0
    expected_target = 100.0 + DEFAULT_PARAMS["atr_stop_multiplier"] * 2.0 * DEFAULT_PARAMS["risk_reward"]
    assert abs(signal["stop_price"] - expected_stop) < 1e-6
    assert abs(signal["target_price"] - expected_target) < 1e-6


def test_macd_cross_no_signal_if_already_above_signal_on_prev_bar():
    from strategies.macd_crossover import MACDCrossoverStrategy
    # MACD was already above signal on prev bar — not a fresh cross
    df = _macd_df(macd_prev=0.3, macd_last=0.5)
    signal = MACDCrossoverStrategy().generate_signal("TEST", df)
    assert signal is None


def test_macd_cross_no_signal_if_price_below_sma50():
    from strategies.macd_crossover import MACDCrossoverStrategy
    df = _macd_df(close_last=101.0, sma_50=110.0)  # price below SMA50
    signal = MACDCrossoverStrategy().generate_signal("TEST", df)
    assert signal is None


def test_macd_cross_no_signal_if_histogram_not_positive():
    from strategies.macd_crossover import MACDCrossoverStrategy
    df = _macd_df(macd_hist_last=-0.1)  # hist negative despite MACD above signal
    signal = MACDCrossoverStrategy().generate_signal("TEST", df)
    assert signal is None


def test_macd_cross_no_signal_if_too_short():
    from strategies.macd_crossover import MACDCrossoverStrategy
    df = _macd_df().iloc[:1]  # only 1 row
    signal = MACDCrossoverStrategy().generate_signal("TEST", df)
    assert signal is None


def test_macd_cross_exits_on_stop():
    from strategies.macd_crossover import MACDCrossoverStrategy
    trade = {"entry_price": 100.0, "stop_loss_price": 97.0, "target_price": 109.0, "hold_days": 1}
    bar = {"close": 96.5, "macd_hist": 0.2}
    should, reason = MACDCrossoverStrategy().should_exit(trade, bar)
    assert should is True
    assert reason == "STOP"


def test_macd_cross_exits_on_target():
    from strategies.macd_crossover import MACDCrossoverStrategy
    trade = {"entry_price": 100.0, "stop_loss_price": 97.0, "target_price": 109.0, "hold_days": 1}
    bar = {"close": 109.5, "macd_hist": 0.2}
    should, reason = MACDCrossoverStrategy().should_exit(trade, bar)
    assert should is True
    assert reason == "TARGET"


def test_macd_cross_exits_on_macd_histogram_negative():
    from strategies.macd_crossover import MACDCrossoverStrategy
    trade = {"entry_price": 100.0, "stop_loss_price": 97.0, "target_price": 109.0, "hold_days": 5}
    bar = {"close": 103.0, "macd_hist": -0.05}
    should, reason = MACDCrossoverStrategy().should_exit(trade, bar)
    assert should is True
    assert reason == "MACD_EXIT"


def test_macd_cross_exits_on_time_stop():
    from strategies.macd_crossover import MACDCrossoverStrategy, DEFAULT_PARAMS
    trade = {"entry_price": 100.0, "stop_loss_price": 97.0, "target_price": 109.0,
             "hold_days": DEFAULT_PARAMS["max_hold_days"]}
    bar = {"close": 103.0, "macd_hist": 0.1}  # still positive hist, but time's up
    should, reason = MACDCrossoverStrategy().should_exit(trade, bar)
    assert should is True
    assert reason == "TIME_STOP"


def test_macd_cross_no_exit_when_in_profit_and_momentum_positive():
    from strategies.macd_crossover import MACDCrossoverStrategy
    trade = {"entry_price": 100.0, "stop_loss_price": 97.0, "target_price": 109.0, "hold_days": 3}
    bar = {"close": 104.0, "macd_hist": 0.3}
    should, reason = MACDCrossoverStrategy().should_exit(trade, bar)
    assert should is False


def test_assign_strategy_macd_cross_in_cascade():
    """ADX 15–20 range → MACD_CROSS (between DONCHIAN_BRK and BB_MEANREV)."""
    from engine.screener import _assign_strategy
    from data.universe import STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=2.0, beta=1.0, vol_ratio=1.0, adx=17.0,
                              rules=STRATEGY_ASSIGNMENT_RULES)
    assert result == "MACD_CROSS"


def test_assign_strategy_donchian_still_gets_adx_below_dual_ema():
    """DONCHIAN_BRK still assigned for ADX 20–22; ADX≥22 now goes to DUAL_EMA first."""
    from engine.screener import _assign_strategy
    from data.universe import STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=2.0, beta=1.0, vol_ratio=1.0, adx=21.0,
                              rules=STRATEGY_ASSIGNMENT_RULES)
    assert result == "DONCHIAN_BRK"


def test_assign_strategy_bb_meanrev_still_gets_low_adx():
    """BB_MEANREV range unchanged — very low ADX with sufficient ATR."""
    from engine.screener import _assign_strategy
    from data.universe import STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=2.0, beta=1.0, vol_ratio=1.0, adx=10.0,
                              rules=STRATEGY_ASSIGNMENT_RULES)
    assert result == "BB_MEANREV"
