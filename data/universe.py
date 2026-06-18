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

US_MASTER_POOL = [
    "NVDA", "TSLA", "AMD", "META", "AAPL",
    "SPY", "QQQ", "MSFT", "AMZN", "GOOGL",
]

INDIA_SCREEN_CRITERIA = {
    "min_avg_daily_volume": 500_000,
    "min_atr_pct_14d": 1.5,
    "min_price_inr": 50,
    "max_price_inr": 5_000,
    "min_beta": 0.9,
    "rsi14_range": (30, 70),
    "no_earnings_within_days": 7,
    "min_market_cap_cr": 5_000,
}

US_SCREEN_CRITERIA = {
    "min_avg_daily_volume": 2_000_000,
    "min_atr_pct_14d": 2.5,
    "price_range_usd": (20, 500),
    "min_beta": 1.1,
    "rsi14_range": (35, 65),
    "no_earnings_within_days": 10,
}

# Strategy assignment rules — used by screener to auto-assign each stock
STRATEGY_ASSIGNMENT_RULES = {
    "RSI2_OVN":  {"beta_max": 1.3, "atr_max": 3.0},
    "ORB_BRK":   {"atr_min": 2.5, "beta_min": 1.1},
    "MOM_CONT":  {"atr_min": 3.0, "volume_ratio_min": 1.5},
}

# Flat list of all India symbols for convenience
def get_india_all_symbols() -> list[str]:
    symbols = []
    for group in INDIA_MASTER_POOL.values():
        symbols.extend(group)
    return list(dict.fromkeys(symbols))  # deduplicate, preserve order
