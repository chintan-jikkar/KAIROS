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
    "broad_etf":          ["QQQ", "DIA", "IWM"],
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
# Priority cascade (see engine/screener.py::_assign_strategy):
#   MOM_CONT > GAP_GO > ORB_BRK > SUPERTREND > TREND_EMA > DUAL_EMA
#   > DONCHIAN_BRK > HIGH_52W > MACD_CROSS > BB_MEANREV > RSI2_OVN (catch-all)
# DUAL_EMA (ADX 22-27): faster EMA-cross trend strategy, slots between TREND_EMA
#   and DONCHIAN — catches momentum-building stocks before the 50/200 golden cross fires.
# HIGH_52W (ADX 15-22, vol_ratio≥1.3): 252-bar channel breakout with volume confirmation.
# GAP_GO (atr≥3.0, beta≥1.5): highest-beta names for intraday gap-up plays.
STRATEGY_ASSIGNMENT_RULES = {
    "RSI2_OVN":     {"beta_max": 1.3, "atr_max": 3.0},
    "GAP_GO":       {"atr_min": 3.0, "beta_min": 1.5},
    "ORB_BRK":      {"atr_min": 2.5, "beta_min": 0.95},
    "MOM_CONT":     {"atr_min": 3.0, "volume_ratio_min": 1.5},
    "SUPERTREND":   {"adx_min": 25, "atr_min": 2.5},
    "TREND_EMA":    {"adx_min": 25, "atr_max": 2.5},
    "DUAL_EMA":     {"adx_min": 22, "adx_max": 27},
    "DONCHIAN_BRK": {"adx_min": 20, "adx_max": 25},
    "HIGH_52W":     {"adx_min": 15, "adx_max": 22, "volume_ratio_min": 1.3},
    "MACD_CROSS":   {"adx_min": 15, "adx_max": 20},
    "BB_MEANREV":   {"adx_max": 20, "atr_min": 1.5},
}

# US rules — mirrors STRATEGY_ASSIGNMENT_RULES with US-specific calibrations.
US_STRATEGY_ASSIGNMENT_RULES = {
    "RSI2_OVN":     {"beta_max": 1.3,  "atr_max": 3.0},
    "GAP_GO":       {"atr_min": 3.5,   "beta_min": 1.8},  # US high-beta gap candidates: NVDA/TSLA/COIN
    "ORB_BRK":      {"atr_min": 2.5,   "beta_min": 1.5},  # calibrated 2026-07-01: raised from 1.1
    "MOM_CONT":     {"atr_min": 3.0,   "volume_ratio_min": 1.5},
    "SUPERTREND":   {"adx_min": 25,    "atr_min": 2.5},
    "TREND_EMA":    {"adx_min": 25,    "atr_max": 2.5},
    "DUAL_EMA":     {"adx_min": 22,    "adx_max": 27},
    "DONCHIAN_BRK": {"adx_min": 20,    "adx_max": 25},
    "HIGH_52W":     {"adx_min": 15,    "adx_max": 22, "volume_ratio_min": 1.3},
    "MACD_CROSS":   {"adx_min": 15,    "adx_max": 20},
    "BB_MEANREV":   {"adx_max": 20,    "atr_min": 2.0},  # raised from India's 1.5; US baseline vol is higher
}


FX_MASTER_POOL = {
    # Major pairs — highest liquidity, suitable for all trend/mean-rev strategies
    "majors": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "AUDUSD=X", "USDCAD=X"],
    # EM / commodity-linked
    "em_commodity": ["NZDUSD=X", "USDINR=X"],
}

# Human-readable display names for FX tickers shown in the dashboard table.
FX_DISPLAY_NAMES: dict[str, str] = {
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",
    "USDCHF=X": "USD/CHF",
    "AUDUSD=X": "AUD/USD",
    "USDCAD=X": "USD/CAD",
    "NZDUSD=X": "NZD/USD",
    "USDINR=X": "USD/INR",
}

FX_SCREEN_CRITERIA = {
    # FX daily ATR% is much smaller than equities (majors avg 0.4–0.8%).
    # 0.25% threshold excludes only truly stagnant periods; in practice all
    # major pairs qualify during normal market conditions.
    "min_atr_pct_14d": 0.25,
    # Wider RSI band — FX can trend for extended periods beyond equity norms.
    "rsi14_range": (20, 80),
}

# Session-dependent strategies (GAP_GO, ORB_BRK, MOM_CONT) require a single exchange
# opening event that FX doesn't have — excluded from the FX cascade.
FX_STRATEGY_ASSIGNMENT_RULES: dict[str, dict] = {
    "SUPERTREND":   {"adx_min": 25, "atr_min": 0.5},
    "TREND_EMA":    {"adx_min": 25, "atr_max": 0.6},
    "DUAL_EMA":     {"adx_min": 20, "adx_max": 27},
    "DONCHIAN_BRK": {"adx_min": 18, "adx_max": 25},
    "HIGH_52W":     {"adx_min": 15, "adx_max": 20, "volume_ratio_min": 1.2},
    "MACD_CROSS":   {"adx_min": 12, "adx_max": 18},
    "BB_MEANREV":   {"adx_max": 20, "atr_min": 0.25},
    "RSI2_OVN":     {"beta_max": 99, "atr_max": 99},   # catch-all
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


def get_fx_all_symbols() -> list[str]:
    symbols = []
    for group in FX_MASTER_POOL.values():
        symbols.extend(group)
    return list(dict.fromkeys(symbols))
