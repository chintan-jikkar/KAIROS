"""
Supertrend (SUPERTREND)
------------------------
ATR-based trend-following band. Less academically rigorous than Donchian but
has an enormous practical track record specifically among NSE/India intraday
and swing traders — it's the single most-used indicator in Indian retail
algo trading.

Entry: close crosses above the Supertrend line (trend direction flips from
       down to up — uses pandas-ta's own direction flag rather than
       re-deriving the flip from price-vs-line comparisons).
Exit:  trend direction flips back down — the line itself is a trailing stop
       by construction, that's the whole point of the indicator, so no
       separate fixed-stop logic is needed once an initial stop is set at
       entry (the line's own value at entry).

Faster/more reactive than TREND_EMA's 50/200 EMA cross — complementary for
shorter-timeframe trend signals on the same kind of names. Long-only,
matching every other KAIROS strategy.
"""
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy

DEFAULT_PARAMS = {
    "supertrend_period": 10,
    "supertrend_multiplier": 3.0,
    "atr_period": 14,
    "atr_target_multiplier": 4.0,  # nominal 2:1 R:R for logging; initial stop is the line itself
}


class SupertrendStrategy(BaseStrategy):
    strategy_id = "SUPERTREND"
    name = "Supertrend"

    def __init__(self, params: dict | None = None, market: str = "INDIA"):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged, market)

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        atr_col = f"atr_{self.params['atr_period']}"

        if df is None or len(df) < self.params["supertrend_period"] + 2:
            return None

        last, prev = df.iloc[-1], df.iloc[-2]
        close = self._get(last, "close")
        supertrend = self._get(last, "supertrend")
        direction = self._get(last, "supertrend_direction")
        prev_direction = self._get(prev, "supertrend_direction")
        atr = self._get(last, atr_col)

        if any(v is None for v in [close, supertrend, direction, prev_direction, atr]):
            return None

        flipped_bullish = prev_direction < 0 and direction > 0
        if not flipped_bullish:
            return None

        entry_price = float(close)
        stop_price = round(float(supertrend), 4)  # the line itself, at the moment of entry
        target_price = round(entry_price + self.params["atr_target_multiplier"] * atr, 4)
        risk = entry_price - stop_price
        planned_rr = round((target_price - entry_price) / risk, 2) if risk > 0 else None

        reason = f"close={entry_price:.2f} — Supertrend flipped bullish (line={supertrend:.2f})"
        logger.info(f"[SUPERTREND] BUY signal: {symbol} | {reason}")

        return {
            "action": "BUY",
            "symbol": symbol,
            "strategy_id": self.strategy_id,
            "strategy_name": self.name,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "planned_rr_ratio": planned_rr,
            "signal_reason": reason,
            "indicators": {
                "supertrend": round(float(supertrend), 2),
                "atr": round(float(atr), 2),
                "close": round(entry_price, 2),
            },
        }

    def should_exit(self, trade: dict, current_bar: dict) -> tuple[bool, str]:
        current_price = current_bar.get("close", trade["entry_price"])
        direction = current_bar.get("supertrend_direction")

        if direction is not None and direction < 0:
            return True, "TREND_REVERSAL"

        stop_price = trade.get("stop_loss_price")
        if stop_price and current_price <= stop_price:
            return True, "STOP"

        return False, ""
