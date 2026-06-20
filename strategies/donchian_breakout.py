"""
Donchian/Turtle Channel Breakout (DONCHIAN_BRK)
------------------------------------------------
The original Turtle Traders system (Richard Dennis, 1983) — one of the most
battle-tested trend-following systems that exists, decades of real track
record. Asymmetric channel: a longer entry channel, a shorter exit channel
(the real Turtle System 1 used 20-day entry / 10-day exit — same defaults
here).

Entry: close breaks above the highest high of the entry_period bars before
       it, and wasn't already above that channel the bar before (a fresh
       breakout, not re-triggering every bar while already in a clean trend).
Exit:  close drops below the lowest low of the exit_period bars before it —
       the trailing channel itself is the stop, classic Turtle exit — or a
       fixed ATR-based stop set at entry, whichever comes first.

Reacts faster to fresh breakouts than TREND_EMA's slower 50/200 EMA cross —
complementary rather than redundant; weak in the same choppy-range
conditions TREND_EMA struggles with. Long-only, matching every other KAIROS
strategy (no short-side trading implemented anywhere yet).
"""
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy

DEFAULT_PARAMS = {
    "entry_period": 20,
    "exit_period": 10,
    "atr_period": 14,
    "atr_stop_multiplier": 2.0,
    "atr_target_multiplier": 4.0,  # nominal 2:1 R:R for logging purposes
}


class DonchianBreakoutStrategy(BaseStrategy):
    strategy_id = "DONCHIAN_BRK"
    name = "Donchian/Turtle Channel Breakout"

    def __init__(self, params: dict | None = None, market: str = "INDIA"):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged, market)

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        entry_n = self.params["entry_period"]
        atr_col = f"atr_{self.params['atr_period']}"
        upper_col = f"donchian_upper_{entry_n}"

        if df is None or len(df) < entry_n + 2:
            return None

        last, prev = df.iloc[-1], df.iloc[-2]
        close = self._get(last, "close")
        prev_close = self._get(prev, "close")
        atr = self._get(last, atr_col)
        upper_channel = self._get(last, upper_col)
        prev_upper_channel = self._get(prev, upper_col)

        if any(v is None for v in [close, prev_close, atr, upper_channel, prev_upper_channel]):
            return None

        fresh_breakout = close > upper_channel and prev_close <= prev_upper_channel
        if not fresh_breakout:
            return None

        entry_price = float(close)
        stop_price = round(entry_price - self.params["atr_stop_multiplier"] * atr, 4)
        target_price = round(entry_price + self.params["atr_target_multiplier"] * atr, 4)
        risk = entry_price - stop_price
        planned_rr = round((target_price - entry_price) / risk, 2) if risk > 0 else None

        reason = (
            f"close={entry_price:.2f} broke above {entry_n}-bar high={upper_channel:.2f} "
            f"(fresh breakout)"
        )
        logger.info(f"[DONCHIAN_BRK] BUY signal: {symbol} | {reason}")

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
                "donchian_upper": round(float(upper_channel), 2),
                "atr": round(float(atr), 2),
                "close": round(entry_price, 2),
            },
        }

    def should_exit(self, trade: dict, current_bar: dict) -> tuple[bool, str]:
        exit_n = self.params["exit_period"]
        current_price = current_bar.get("close", trade["entry_price"])

        lower_channel = current_bar.get(f"donchian_lower_{exit_n}")
        if lower_channel is not None and current_price < lower_channel:
            return True, "TRAILING_CHANNEL"

        stop_price = trade.get("stop_loss_price")
        if stop_price and current_price <= stop_price:
            return True, "STOP"

        return False, ""
