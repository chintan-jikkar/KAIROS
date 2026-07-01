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
