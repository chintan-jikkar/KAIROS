"""Shared strategy id -> human-readable name mapping for dashboard UI.

Lives here instead of being read from engine.signals.STRATEGY_REGISTRY because
the dashboard runs on a bare interpreter without pandas-ta — importing
engine.signals would transitively import data.indicators, which imports
pandas_ta at module level, crashing the dashboard process. See the two-
interpreter split in the project memory / dashboard/components/engine_bridge.py.
"""

STRATEGY_NAMES = {
    "RSI2_OVN": "RSI-2 overnight mean reversion",
    "ORB_BRK": "Opening range breakout",
    "MOM_CONT": "Momentum continuation",
    "TREND_EMA": "Trend following (50/200 EMA cross)",
    "BB_MEANREV": "Intraday Bollinger mean reversion",
    "DONCHIAN_BRK": "Donchian/Turtle channel breakout",
    "MACD_CROSS": "MACD momentum crossover",
    "SUPERTREND": "Supertrend",
}
