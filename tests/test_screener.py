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
    """COIN-like: ATR=6.95%, beta=2.08 → ORB_BRK (high-beta volatile, beta≥1.5 threshold)."""
    from engine.screener import _assign_strategy
    from data.universe import US_STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=6.95, beta=2.08, vol_ratio=0.97, adx=21.6,
                              rules=US_STRATEGY_ASSIGNMENT_RULES)
    assert result == "ORB_BRK"


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
    """MSFT-like: ATR=3.48%, beta=0.52, ADX=23.2 → DONCHIAN_BRK.
    Low beta misses ORB_BRK; ADX 20–25 slots into DONCHIAN band."""
    from engine.screener import _assign_strategy
    from data.universe import US_STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=3.48, beta=0.52, vol_ratio=0.71, adx=23.2,
                              rules=US_STRATEGY_ASSIGNMENT_RULES)
    assert result == "DONCHIAN_BRK"


def test_assign_strategy_us_bb_meanrev_below_orb_beta():
    """beta=1.49 (just below ORB_BRK threshold of 1.5), ADX=18 → BB_MEANREV.
    Verifies the calibrated beta_min=1.5 boundary: 1.49 misses ORB_BRK, falls
    to BB_MEANREV (ADX≤20, ATR≥2.0)."""
    from engine.screener import _assign_strategy
    from data.universe import US_STRATEGY_ASSIGNMENT_RULES
    result = _assign_strategy(atr_pct=3.0, beta=1.49, vol_ratio=0.7, adx=18.0,
                              rules=US_STRATEGY_ASSIGNMENT_RULES)
    assert result == "BB_MEANREV"
