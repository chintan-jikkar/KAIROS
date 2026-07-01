"""Tests for screener helpers — synthetic fixtures only, no network calls."""


def test_beta_identical_series_is_one():
    """A returns series identical to SPY → beta == 1.0."""
    from engine.screener import _compute_beta_vs_spy
    spy = [0.01, -0.02, 0.015, -0.005, 0.008, 0.012, -0.003, 0.006, -0.01, 0.004]
    assert abs(_compute_beta_vs_spy(spy, spy) - 1.0) < 1e-6


def test_beta_zero_correlated_series():
    """A flat returns series (all zeros) vs any SPY → beta == 0.0."""
    from engine.screener import _compute_beta_vs_spy
    spy = [0.01, -0.02, 0.015, -0.005, 0.008]
    flat = [0.0] * len(spy)
    assert _compute_beta_vs_spy(flat, spy) == 0.0


def test_beta_double_leveraged_series():
    """A 2x-leveraged series (2 * SPY returns) → beta ≈ 2.0."""
    from engine.screener import _compute_beta_vs_spy
    spy = [0.01, -0.02, 0.015, -0.005, 0.008, 0.012, -0.003, 0.006, -0.01, 0.004]
    doubled = [r * 2 for r in spy]
    assert abs(_compute_beta_vs_spy(doubled, spy) - 2.0) < 1e-6


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
