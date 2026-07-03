"""
Intraday Bollinger Mean Reversion (BB_MEANREV)
-------------------------------------------------
Adapted from a 15-min std-dev fade strategy: when price overextends below its
20-period Bollinger lower band, fade the move expecting reversion to the mean.
Long-only (fading downside extremes only) — matching every other KAIROS
strategy's convention; the short side (fading upside extremes) is deliberately
not implemented to stay consistent with the rest of the codebase.

Entry:  close < lower Bollinger band (20-period, configurable std-dev width).
Exit:   price reverts to the middle band (SMA20), a tight stop, a time stop
        (mean-reversion that hasn't worked within N candles probably won't),
        or EOD — matching ORB_BRK/MOM_CONT's intraday discipline.
"""
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy

DEFAULT_PARAMS = {
    "bb_period": 20,
    "entry_std": 2.0,           # tightened from 1.6σ; standard 2σ is more selective
    "stop_loss_pct": 0.015,     # tighter than the daily strategies — intraday
    "max_hold_candles": 8,      # ~2 hours on 15-min bars
    "market_filter": False,     # mean reversion doesn't need a green/red market
    "rsi14_max_entry": 35,      # only fade when RSI14 also confirms oversold conditions
}


class BBMeanReversionStrategy(BaseStrategy):
    strategy_id = "BB_MEANREV"
    name = "Intraday Bollinger Mean Reversion"

    def __init__(self, params: dict | None = None, market: str = "INDIA"):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged, market)

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """df: intraday bars (15-min) for today, with Bollinger and RSI columns already added."""
        if df is None or df.empty:
            return None

        last = df.iloc[-1]
        close = self._get(last, "close")
        bb_lower = self._get(last, "bb_lower")
        bb_mid = self._get(last, "bb_mid")
        rsi14 = self._get(last, "rsi_14")

        if any(v is None for v in [close, bb_lower, bb_mid]):
            return None

        if close >= bb_lower:
            return None

        # RSI14 gate — only fade oversold conditions, not price drops with momentum still intact
        if rsi14 is not None and rsi14 > self.params["rsi14_max_entry"]:
            return None

        entry_price = float(close)
        stop_price = round(entry_price * (1 - self.params["stop_loss_pct"]), 4)
        target_price = round(float(bb_mid), 4)

        if target_price <= entry_price:
            return None

        planned_rr = round((target_price - entry_price) / (entry_price - stop_price), 2)
        reason = (
            f"Close={entry_price:.2f} below lower Bollinger band={bb_lower:.2f} "
            f"({self.params['entry_std']}σ, 20-period), targeting mean reversion to SMA20={bb_mid:.2f}"
        )
        logger.info(f"[BB_MEANREV] BUY signal: {symbol} | {reason}")

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
                "bb_lower": round(float(bb_lower), 2),
                "bb_mid": round(float(bb_mid), 2),
                "close": round(entry_price, 2),
            },
        }

    def should_exit(self, trade: dict, current_bar: dict) -> tuple[bool, str]:
        entry_price = trade["entry_price"]
        current_price = current_bar.get("close", entry_price)
        bb_mid = current_bar.get("bb_mid")
        hold_candles = trade.get("hold_candles", 0)

        # 1. Reverted to the mean — target hit
        if bb_mid is not None and current_price >= bb_mid:
            return True, "TARGET"

        # 2. Stop loss
        if self._pnl_pct(entry_price, current_price) <= -self.params["stop_loss_pct"]:
            return True, "STOP"

        # 3. Time stop — hasn't worked, don't keep waiting
        if hold_candles >= self.params["max_hold_candles"]:
            return True, "TIME_STOP"

        # 4. EOD — always flatten intraday positions
        if current_bar.get("is_eod", False):
            return True, "EOD"

        return False, ""
