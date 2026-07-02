"""
Stock universe lists and screener criteria.
All constants defined here — screener.py reads from this module.
"""

INDIA_MASTER_POOL = {
    "large_cap_momentum": [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "AXISBANK", "KOTAKBANK", "SBIN", "WIPRO", "TECHM",
    ],
    "high_atr_volatile": [
        "TATAMOTORS", "TATASTEEL", "JSWSTEEL", "HINDALCO",
        "ADANIPORTS", "BAJFINANCE", "ZOMATO", "PAYTM",
    ],
    "defensive_reversal": [
        "HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "COLPAL",
    ],
    "nifty_etf": [
        "NIFTYBEES", "JUNIORBEES", "BANKBEES",
    ],
}

US_MASTER_POOL = {
    "large_cap_momentum": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
    "high_atr_volatile":  ["NVDA", "TSLA", "AMD", "COIN", "PLTR"],
    "defensive_reversal": ["JNJ", "PG", "KO", "PEP", "WMT"],
    "broad_etf":          ["SPY", "QQQ", "DIA", "IWM"],
}

INDIA_SCREEN_CRITERIA = {
    "min_avg_daily_volume": 500_000,
    "min_atr_pct_14d": 1.5,
    "min_price_inr": 50,
    "max_price_inr": 5_000,
    "rsi14_range": (30, 70),
    "no_earnings_within_days": 7,
    "min_market_cap_cr": 5_000,
}

US_SCREEN_CRITERIA = {
    "min_avg_daily_volume": 2_000_000,
    "min_atr_pct_14d": 2.5,
    "price_range_usd": (20, 750),   # raised from 500 — META (~$616) and AMD (~$546) were blocked
    "rsi14_range": (35, 65),
    "no_earnings_within_days": 10,
}

# Strategy assignment rules — used by screener to auto-assign each stock.
# Priority cascade (see engine/screener.py::_assign_strategy): MOM_CONT > ORB_BRK >
# SUPERTREND > TREND_EMA > DONCHIAN_BRK > BB_MEANREV > RSI2_OVN (catch-all default).
# SUPERTREND and DONCHIAN_BRK added 2026-06-20 (docs/strategy-library.md) — both
# slotted into ADX/ATR bands that don't overlap the 5 original strategies:
# SUPERTREND takes the high-ADX+high-ATR names TREND_EMA's atr_max excludes;
# DONCHIAN_BRK takes the ADX 20-25 gap between BB_MEANREV's and TREND_EMA's bands.
STRATEGY_ASSIGNMENT_RULES = {
    "RSI2_OVN":     {"beta_max": 1.3, "atr_max": 3.0},
    "ORB_BRK":      {"atr_min": 2.5, "beta_min": 0.95},  # beta is a 1.0 placeholder until live
                                                           # Kite beta is wired up (Phase 6) — 0.95
                                                           # keeps this reachable until then, was 1.1
    "MOM_CONT":     {"atr_min": 3.0, "volume_ratio_min": 1.5},
    "SUPERTREND":   {"adx_min": 25, "atr_min": 2.5},
    "TREND_EMA":    {"adx_min": 25, "atr_max": 2.5},
    "DONCHIAN_BRK": {"adx_min": 20, "adx_max": 25},
    "BB_MEANREV":   {"adx_max": 20, "atr_min": 1.5},
}

# Initial thresholds — calibrated in Task 8 after a real run against live yfinance data.
# Structure mirrors STRATEGY_ASSIGNMENT_RULES; same cascade priority order.
US_STRATEGY_ASSIGNMENT_RULES = {
    "RSI2_OVN":     {"beta_max": 1.3,  "atr_max": 3.0},
    "ORB_BRK":      {"atr_min": 2.5,   "beta_min": 1.5},  # calibrated 2026-07-01: COIN/TSLA/NVDA all beta≥1.9; 1.1 let AMZN (beta=1.26, ADX=27.6) jump the queue ahead of SUPERTREND
    "MOM_CONT":     {"atr_min": 3.0,   "volume_ratio_min": 1.5},
    "SUPERTREND":   {"adx_min": 25,    "atr_min": 2.5},
    "TREND_EMA":    {"adx_min": 25,    "atr_max": 2.5},
    "DONCHIAN_BRK": {"adx_min": 20,    "adx_max": 25},
    "BB_MEANREV":   {"adx_max": 20,    "atr_min": 2.0},  # raised from India's 1.5; US baseline vol is higher
}


def get_india_all_symbols() -> list[str]:
    symbols = []
    for group in INDIA_MASTER_POOL.values():
        symbols.extend(group)
    return list(dict.fromkeys(symbols))  # deduplicate, preserve order


def get_us_all_symbols() -> list[str]:
    symbols = []
    for group in US_MASTER_POOL.values():
        symbols.extend(group)
    return list(dict.fromkeys(symbols))  # deduplicate, preserve order
